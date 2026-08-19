#!/usr/bin/env python3
"""metalog_validate — the conformance test SPEC.md §8 clause 1 declares.

SPEC.md §8 closes with "There is no central conformance authority. The schema is
the test." This is that test, shipped with the standard so an implementer can run
it without asking anyone: point it at a stream of MetaLog documents (or a
MetaLogDiff) and it reports, separately:

  * SCHEMA-INVALID     a closed object was violated -> §8 clause 1 fails. Exit 1.
  * LEGAL-BUT-UNDESCRIBED
                       a key an OPEN container permits and no schema describes.
                       Not a conformance failure; reported because a producer
                       emitting it is either extending outside `extensions` (§7)
                       or riding ahead of a schema that lags the prose.

The two are different defects with different owners, and a report that adds them
together misprices both. They are disjoint by construction: a key rejected by a
closed object is never counted as undescribed.

Exit codes are a contract:
  0  conformant against the schema
  1  findings: at least one document is schema-invalid
  2  the instrument could not run honestly (unparsable corpus, empty corpus,
     document count did not match a caller's expectation, unresolvable $ref,
     missing schema, self-test failure). Never a green, never a silent skip.

Licence: MIT, per this repository's LICENSE (executable code is MIT; prose is
CC BY 4.0 -- see LICENSE-SPEC). Requires `jsonschema` >= 4.18 (Draft 2020-12).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parent

SCHEMAS = {
    "metalog": "metalog.v0.schema.json",
    "diff": "metalog_diff.v0.schema.json",
}

# A `### name ###` line separates named JSONL bodies in the published determinism
# evidence. One document PER LINE -- reading a section as a single document
# validates only its first line and returns a smaller, entirely plausible number.
SECTION_RE = re.compile(r"^###\s(.+?)\s###$")

# Recursion bounds. `$defs/coordinate` is self-referential through `children`, so
# a hostile or corrupt document could otherwise walk forever. Exceeding either is
# an instrument failure (exit 2), never a truncated report.
MAX_INSTANCE_DEPTH = 64
MAX_APPLICATOR_DEPTH = 32

# Object-shaping keywords. A subschema carrying NONE of them constrains nothing
# about an object's members, which is a deliberate "anything goes" (SPEC §7
# extension payloads, §16.4 cube coordinates, sketch_params). Descending into one
# would report every key inside it as undescribed -- a false positive on a surface
# the schema opened on purpose.
OBJECT_KEYWORDS = ("properties", "patternProperties", "additionalProperties",
                   "unevaluatedProperties")


class InstrumentError(RuntimeError):
    """The validator cannot answer honestly. Always exit 2, never exit 0."""


# --------------------------------------------------------------------------
# Corpus loading. There is no path through this function that skips a line.
# --------------------------------------------------------------------------

def load_corpus(path: Path) -> tuple[list[tuple[str, object]], dict]:
    """Return ([(label, document)], accounting).

    Accepts three shapes: a single `.json` document, JSONL, and the sectioned
    `### name ###` + JSONL form the published determinism evidence uses.

    THE DESIGN RULE: every non-blank line is classified as exactly one of
    {section header, document}. A line that parses as neither is fatal. There is
    no third bucket, so a parser bug cannot express itself as a smaller document
    count -- it can only stop the run.
    """
    if not path.is_file():
        raise InstrumentError(f"corpus does not exist: {path}")
    text = path.read_text(encoding="utf-8")

    if path.suffix == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InstrumentError(f"{path}: not a JSON document — {exc}") from exc
        return [(path.name, doc)], {"lines": 1, "blank": 0, "sections": 0, "documents": 1}

    lines = text.splitlines()
    sectioned = any(SECTION_RE.match(ln.strip()) for ln in lines)
    docs: list[tuple[str, object]] = []
    section = path.stem
    ordinal = 0
    blank = 0
    sections = 0

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            blank += 1
            continue
        if sectioned:
            header = SECTION_RE.match(stripped)
            if header:
                section = header.group(1)
                sections += 1
                ordinal = 0
                continue
        try:
            doc = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InstrumentError(
                f"{path}:{lineno}: line is neither a section header nor a JSON "
                f"document — {exc}. An unreadable line is fatal, never skipped: "
                f"skipping it would shrink the document count silently."
            ) from exc
        ordinal += 1
        docs.append((f"{section}#{ordinal}", doc))

    if not docs:
        raise InstrumentError(
            f"{path}: zero documents parsed. An empty corpus is an instrument "
            f"failure, never a clean result — a gate with nothing to judge is green "
            f"for the one reason that matters: it never looked."
        )
    return docs, {"lines": len(lines), "blank": blank, "sections": sections,
                  "documents": len(docs)}


# --------------------------------------------------------------------------
# Schema plumbing shared by both species.
# --------------------------------------------------------------------------

def _resolve_pointer(ref: str, root: dict) -> dict:
    if not ref.startswith("#"):
        raise InstrumentError(
            f"non-local $ref {ref!r}: this validator resolves only in-document "
            f"pointers. A remote reference cannot be fetched deterministically."
        )
    node = root
    for token in ref[1:].lstrip("/").split("/"):
        if not token:
            continue
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise InstrumentError(f"$ref {ref!r} does not resolve inside the schema")
        node = node[token]
    if not isinstance(node, dict):
        raise InstrumentError(f"$ref {ref!r} resolves to a non-object subschema")
    return node


def applicable(node, root: dict) -> list[dict]:
    """Every subschema that applies AT THIS instance location.

    Follows `$ref` (which in 2020-12 applies alongside its siblings, not instead
    of them) and the in-place applicators. `anyOf`/`oneOf` branches are UNIONED
    rather than evaluated: that over-approximates what the schema "describes",
    which is the conservative direction — this instrument may miss an undescribed
    key, it may never invent one. A false positive here would send a lane to
    delete a field the schema does describe.

    `if` is deliberately not unioned (it is a condition, not a description);
    `then`/`else` are. `not` is skipped entirely.
    """
    out: list[dict] = []
    seen: set[int] = set()
    stack = [(node, 0)]
    while stack:
        current, depth = stack.pop()
        if not isinstance(current, dict):
            continue
        if depth > MAX_APPLICATOR_DEPTH:
            raise InstrumentError(
                f"applicator nesting exceeded {MAX_APPLICATOR_DEPTH} — the schema "
                f"is cyclic in place, which this walker cannot evaluate honestly"
            )
        if id(current) in seen:
            continue
        seen.add(id(current))
        out.append(current)
        if "$ref" in current:
            stack.append((_resolve_pointer(current["$ref"], root), depth + 1))
        for keyword in ("allOf", "anyOf", "oneOf"):
            for branch in current.get(keyword) or []:
                stack.append((branch, depth + 1))
        for keyword in ("then", "else"):
            if keyword in current:
                stack.append((current[keyword], depth + 1))
    return out


def _offending_keys(subschema: dict, instance: dict) -> list[str]:
    """The members a closed object rejected — recomputed from the schema and the
    instance, never scraped out of the validator's English error message."""
    named = set(subschema.get("properties", {}))
    patterns = [re.compile(p) for p in subschema.get("patternProperties", {})]
    return sorted(k for k in instance
                  if k not in named and not any(p.search(k) for p in patterns))


def normalise_path(parts) -> str:
    """`stats.top_k.3` -> `stats.top_k[]`: an array index is a location, not a
    finding. Two entries of one array carrying the same defect are one finding."""
    rendered = ".".join("[]" if isinstance(p, int) else str(p) for p in parts)
    return rendered.replace(".[]", "[]") or "<root>"


# --------------------------------------------------------------------------
# Species 1 — SCHEMA-INVALID.
# --------------------------------------------------------------------------

def collect_findings(docs, validator) -> tuple[list[dict], int]:
    """Group every schema violation by (path, keyword). Deterministic: sorted on
    the way out, so the report never depends on the validator's emission order."""
    errors = 0
    counts: Counter = Counter()
    doc_sets: dict[tuple[str, str], set] = defaultdict(set)
    props: dict[tuple[str, str], set] = defaultdict(set)
    first: dict[tuple[str, str], str] = {}

    for label, doc in docs:
        for err in validator.iter_errors(doc):
            errors += 1
            key = (normalise_path(err.absolute_path), err.validator)
            counts[key] += 1
            doc_sets[key].add(label)
            first.setdefault(key, label)
            if err.validator == "additionalProperties" and isinstance(err.instance, dict):
                props[key].update(_offending_keys(err.schema, err.instance))
            elif err.validator == "required" and isinstance(err.instance, dict):
                props[key].update(set(err.validator_value) - set(err.instance))

    findings = [{
        "path": path,
        "keyword": keyword,
        "properties": sorted(props[(path, keyword)]),
        "errors": counts[(path, keyword)],
        "documents": len(doc_sets[(path, keyword)]),
        "first_document": first[(path, keyword)],
    } for path, keyword in sorted(counts)]
    return findings, errors


# --------------------------------------------------------------------------
# Species 2 — LEGAL-BUT-UNDESCRIBED.
# --------------------------------------------------------------------------

def _walk_undescribed(instance, subschemas: list[dict], root: dict,
                      path: str, out: list[tuple[str, str]], depth: int) -> None:
    if depth > MAX_INSTANCE_DEPTH:
        raise InstrumentError(
            f"document nesting exceeded {MAX_INSTANCE_DEPTH} at {path or '<root>'}"
        )

    if isinstance(instance, dict):
        if not any(kw in s for s in subschemas for kw in OBJECT_KEYWORDS):
            return  # unconstrained by design — see OBJECT_KEYWORDS
        closed = any(s.get("additionalProperties") is False for s in subschemas)
        fallback: list[dict] = []
        for s in subschemas:
            extra = s.get("additionalProperties")
            if isinstance(extra, dict):
                fallback += applicable(extra, root)

        for key in sorted(instance):
            children: list[dict] = []
            for s in subschemas:
                declared = s.get("properties", {})
                if key in declared:
                    children += applicable(declared[key], root)
                for pattern, sub in (s.get("patternProperties") or {}).items():
                    if re.search(pattern, key):
                        children += applicable(sub, root)
            if children:
                child_path = f"{path}.{key}" if path else key
                _walk_undescribed(instance[key], children, root, child_path, out, depth + 1)
            elif fallback:
                child_path = f"{path}.{key}" if path else key
                _walk_undescribed(instance[key], fallback, root, child_path, out, depth + 1)
            elif closed:
                # Rejected by a closed object: species 1 already owns it. Counting
                # it here too would report one defect as two.
                continue
            else:
                out.append((path or "<root>", key))

    elif isinstance(instance, list):
        for index, item in enumerate(instance):
            children: list[dict] = []
            for s in subschemas:
                prefix = s.get("prefixItems")
                if isinstance(prefix, list) and index < len(prefix):
                    children += applicable(prefix[index], root)
                elif isinstance(s.get("items"), dict):
                    children += applicable(s["items"], root)
            if children:
                _walk_undescribed(item, children, root, f"{path}[]", out, depth + 1)


def collect_undescribed(docs, schema: dict) -> list[dict]:
    hits: Counter = Counter()
    first: dict[tuple[str, str], str] = {}
    for label, doc in docs:
        found: list[tuple[str, str]] = []
        _walk_undescribed(doc, applicable(schema, schema), schema, "", found, 0)
        for entry in set(found):
            hits[entry] += 1
            first.setdefault(entry, label)
    return [{"path": path, "key": key, "documents": hits[(path, key)],
             "first_document": first[(path, key)]}
            for path, key in sorted(hits)]


# --------------------------------------------------------------------------
# The spec-mention lead. A name in the prose but not in the schema is a SCHEMA
# LAG; a name in neither is a producer extending outside `extensions` (§7).
# This is a lead, not a verdict: a short common word ("component") matches prose
# that has nothing to do with the field. Reported as a column, never as a cause.
# --------------------------------------------------------------------------

def spec_mentions(names, spec_text: str) -> dict[str, bool]:
    """Does SPEC.md name this member AS A MEMBER — a Markdown code span or a
    quoted JSON key — rather than in passing as an English word?

    The code-span restriction is what keeps the lead usable: members called
    `count`, `level`, `total` or `source` match ordinary prose on every page, and
    an instrument that answers "yes" for all of them answers nothing. It does NOT
    make the lead a verdict: a name can be a code span for a DIFFERENT concept in
    a different section, which is measured and true of at least one member the
    published evidence carries today.
    """
    out = {}
    for name in sorted(set(names)):
        escaped = re.escape(name)
        out[name] = bool(re.search(rf"`{escaped}`|\"{escaped}\"", spec_text))
    return out


# --------------------------------------------------------------------------
# Reporting.
# --------------------------------------------------------------------------

def render(report: dict, stream) -> None:
    w = lambda s="": print(s, file=stream)
    env = report["environment"]
    w('metalog-conformance · SPEC §8 clause 1 — "The schema is the test."')
    for path in report["corpus"]:
        w(f"  corpus     : {path}")
    w(f"  kind       : {report['kind']}  (schema/{report['schema']})")
    acc = report["accounting"]
    plural = lambda n, word: f"{n} {word}" if n == 1 else f"{n} {word}s"
    w(f"  parsed     : {plural(acc['sections'], 'section')} · "
      f"{plural(acc['documents'], 'document')} · {plural(acc['lines'], 'line')} "
      f"({acc['blank']} blank). No line is skippable: an unreadable line is fatal.")
    w(f"  validator  : jsonschema {env['jsonschema']} · Draft 2020-12 · "
      f"format = {env['format_mode']}")
    w()

    lead = report["spec_mentions"]
    tag = lambda n: "in SPEC.md" if lead.get(n) else "nowhere"

    if report["findings"]:
        total = sum(f["errors"] for f in report["findings"])
        classes = len(report["findings"])
        w(f"SCHEMA-INVALID — a closed object was violated. §8 clause 1 FAILS. "
          f"{plural(total, 'error')} in {classes} "
          f"{'class' if classes == 1 else 'classes'}:")
        for f in report["findings"]:
            names = ", ".join(f"{n} [{tag(n)}]" for n in f["properties"]) or "—"
            w(f"  {f['path']}")
            w(f"      keyword  : {f['keyword']}")
            w(f"      members  : {names}")
            w(f"      seen     : {plural(f['errors'], 'error')} · {f['documents']}/"
              f"{acc['documents']} documents · first: {f['first_document']}")
    else:
        w("SCHEMA-INVALID — none. Every document validates against the schema.")
    w()

    if report["undescribed"]:
        w("LEGAL-BUT-UNDESCRIBED — permitted by an OPEN container, described by no "
          "schema. NOT a conformance failure:")
        for u in report["undescribed"]:
            w(f"  {u['path']}.{u['key']} — {u['documents']}/{acc['documents']} "
              f"documents · [{tag(u['key'])}] · first: {u['first_document']}")
    else:
        w("LEGAL-BUT-UNDESCRIBED — none. Every emitted member is described somewhere.")
    w()
    if lead:
        w("[in SPEC.md] / [nowhere] is a LEAD, not a verdict — it asks whether the "
          "prose names the member as a member (a code span or a quoted key). "
          "`in SPEC.md` on an INVALID member points at a schema that lags its own "
          "prose (GOVERNANCE §3); `nowhere` points at a producer extending outside "
          "§7 `extensions`. A member whose name is a code span for a DIFFERENT "
          "concept elsewhere reads `in SPEC.md` and is not a schema lag — open the "
          "section before acting on it.")
        w()
    # The declared limit travels to where the HUMAN reads, not only to where the
    # machine exits. A tool that lives in `conformance/` and prints a green is read
    # as "conformant"; it tests ONE of §8's four clauses, and saying so here is the
    # difference between an instrument and an instrument's reputation.
    w("SCOPE — this tests SPEC §8 clause 1 (schema validation) and nothing else.")
    w("  NOT checked: clause 2 (every required field populated per its definition —")
    w("  only the schema-expressible part of it is), clause 3 (template_id computed")
    w("  per §3.2 — no pinned cross-implementation vector exists yet), clause 4")
    w("  (top_k truthfully bounded at top_k_size). A green above says nothing about")
    w("  those three. See conformance/README.md § What this does not reach.")
    w()
    w(f"VERDICT: {report['verdict']}")


# --------------------------------------------------------------------------
# The run.
# --------------------------------------------------------------------------

def run(corpora, kind: str, schema_dir: Path, spec_text: str, check_formats: bool,
        expect_documents: int | None) -> dict:
    import jsonschema
    from importlib import metadata

    schema_name = SCHEMAS[kind]
    schema_path = schema_dir / schema_name
    if not schema_path.is_file():
        raise InstrumentError(f"schema not found: {schema_path} (pass --schema-dir)")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    fmt = jsonschema.FormatChecker() if check_formats else None
    validator = jsonschema.Draft202012Validator(schema, format_checker=fmt)

    docs: list[tuple[str, object]] = []
    accounting = {"lines": 0, "blank": 0, "sections": 0, "documents": 0}
    for path in corpora:
        part, acc = load_corpus(Path(path))
        docs += part
        for k in accounting:
            accounting[k] += acc[k]

    if expect_documents is not None and accounting["documents"] != expect_documents:
        raise InstrumentError(
            f"expected {expect_documents} documents, parsed {accounting['documents']}. "
            f"A count that does not reconcile means the corpus moved or the reader is "
            f"blind to part of it — either way the verdict below would be about a "
            f"different corpus than the caller believes."
        )

    findings, _ = collect_findings(docs, validator)
    undescribed = collect_undescribed(docs, schema)
    names = [n for f in findings for n in f["properties"]] + [u["key"] for u in undescribed]

    return {
        "corpus": [str(p) for p in corpora],
        "kind": kind,
        "schema": schema_name,
        "accounting": accounting,
        "findings": findings,
        "undescribed": undescribed,
        "spec_mentions": spec_mentions(names, spec_text),
        "verdict": "NONCONFORMANT" if findings else "CONFORMANT",
        "environment": {
            "jsonschema": metadata.version("jsonschema"),
            "python": ".".join(str(v) for v in sys.version_info[:3]),
            "format_mode": "assertion (--check-formats)" if check_formats
                           else "annotation (Draft 2020-12 default vocabulary)",
        },
    }


# --------------------------------------------------------------------------
# Self-test — the gate's teeth, and the reason a green here means anything.
# --------------------------------------------------------------------------

REQUIRED_CONTROLS = {
    "multi-document-section",       # forecloses green-BLIND on the sectioned form
    "undescribed-false-positive",   # forecloses a walker that invents findings
    "closed-object-violation",      # forecloses can't-FAIL on species 1
    "instrument-failure",           # forecloses a corrupt corpus reading as clean
}


def _tuples(findings):
    return [(f["path"], f["keyword"], tuple(f["properties"]), f["errors"], f["documents"])
            for f in findings]


def _undescribed_tuples(entries):
    return [(u["path"], u["key"], u["documents"]) for u in entries]


def selftest(schema_dir: Path, spec_text: str, stream) -> int:
    w = lambda s="": print(s, file=stream)
    manifest_path = TOOL_DIR / "fixtures" / "manifest.json"
    if not manifest_path.is_file():
        raise InstrumentError(f"fixture manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]

    present = {f.get("control") for f in fixtures} - {None}
    missing = REQUIRED_CONTROLS - present
    if missing:
        raise InstrumentError(
            f"the fixture set lost its teeth: no fixture carries control(s) "
            f"{sorted(missing)}. Each one forecloses a specific way this validator "
            f"could go green while blind; without it, a pass here proves nothing."
        )

    import jsonschema
    for kind, name in sorted(SCHEMAS.items()):
        path = schema_dir / name
        if not path.is_file():
            raise InstrumentError(f"shipped schema missing: {path}")
        jsonschema.Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8")))
        w(f"  schema {name}: valid Draft 2020-12")

    failures: list[str] = []
    for fx in fixtures:
        path = TOOL_DIR / "fixtures" / fx["path"]
        want = fx["expect"]
        try:
            report = run([path], fx["kind"], schema_dir, spec_text, False,
                         want.get("documents"))
            code = 1 if report["findings"] else 0
            got = {
                "exit": code,
                "documents": report["accounting"]["documents"],
                "findings": _tuples(report["findings"]),
                "undescribed": _undescribed_tuples(report["undescribed"]),
            }
        except InstrumentError as exc:
            got = {"exit": 2, "documents": None, "findings": None,
                   "undescribed": None, "why": str(exc)}

        expected = {
            "exit": want["exit"],
            "documents": want.get("documents") if want["exit"] != 2 else None,
            "findings": [tuple(t[:2]) + (tuple(t[2]), t[3], t[4])
                         for t in want.get("findings", [])] if want["exit"] != 2 else None,
            "undescribed": [tuple(t) for t in want.get("undescribed", [])]
                           if want["exit"] != 2 else None,
        }
        ok = all(got.get(k) == expected[k] for k in expected)
        w(f"  [{'PASS' if ok else 'FAIL'}] {fx['path']}  ({fx['why']})")
        if not ok:
            failures.append(fx["path"])
            for k in ("exit", "documents", "findings", "undescribed"):
                if got.get(k) != expected[k]:
                    w(f"        {k}: expected {expected[k]!r}")
                    w(f"        {k}: actual   {got.get(k)!r}")
            if "why" in got:
                w(f"        instrument said: {got['why']}")

    # The verdict is COMPUTED FROM the runs. A summary line that can disagree with
    # its own findings is not a check.
    if failures:
        w(f"SELFTEST FAILED: {len(failures)}/{len(fixtures)} fixtures — {failures}")
        return 2
    w(f"SELFTEST PASSED: {len(fixtures)}/{len(fixtures)} fixtures · controls armed: "
      f"{sorted(REQUIRED_CONTROLS)}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="metalog_validate",
        description="The conformance test SPEC.md §8 clause 1 declares.")
    parser.add_argument("corpus", nargs="*", type=Path,
                        help="MetaLog document stream: .json, .jsonl, or the "
                             "sectioned '### name ###' + JSONL evidence form.")
    parser.add_argument("--kind", choices=sorted(SCHEMAS), default="metalog",
                        help="which shipped schema to validate against (default: metalog)")
    parser.add_argument("--schema-dir", type=Path, default=REPO_ROOT / "schema")
    parser.add_argument("--spec", type=Path, default=REPO_ROOT / "SPEC.md",
                        help="SPEC.md, consulted only for the schema-lag lead")
    parser.add_argument("--expect-documents", type=int, default=None,
                        help="fail with exit 2 unless exactly N documents were parsed")
    parser.add_argument("--check-formats", action="store_true",
                        help="assert `format` (date-time, uri). OFF by default: "
                             "Draft 2020-12's default vocabulary makes format an "
                             "ANNOTATION, so asserting it is stricter than §8 clause 1.")
    parser.add_argument("--strict-undescribed", action="store_true",
                        help="also exit 1 on legal-but-undescribed members")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--selftest", action="store_true",
                        help="run the shipped fixtures and prove this validator can fail")
    args = parser.parse_args(argv)

    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("::error::jsonschema is not installed — `pip install -r "
              "conformance/requirements.txt`. Refusing to report a verdict without "
              "a validator.", file=sys.stderr)
        return 2

    try:
        if not args.spec.is_file():
            raise InstrumentError(
                f"SPEC.md not found at {args.spec}. The schema-lag lead reads it; "
                f"running without it would report 'named nowhere' for every member, "
                f"which is a fabricated finding. Pass --spec.")
        spec_text = args.spec.read_text(encoding="utf-8")

        if args.selftest:
            return selftest(args.schema_dir, spec_text, sys.stdout)

        if not args.corpus:
            parser.error("give at least one corpus path, or --selftest")

        report = run(args.corpus, args.kind, args.schema_dir, spec_text,
                     args.check_formats, args.expect_documents)
    except InstrumentError as exc:
        print(f"::error::instrument failure — {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        render(report, sys.stdout)

    if report["findings"]:
        return 1
    if args.strict_undescribed and report["undescribed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
