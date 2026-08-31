#!/usr/bin/env python3
"""metalog_validate — the conformance test SPEC.md §8 clause 1 declares.

SPEC.md §8 closes with "There is no central conformance authority. The schema is
the test." This is that test, shipped with the standard so an implementer can run
it without asking anyone: point it at a stream of MetaLog documents (or a
MetaLogDiff) and it reports, separately:

  * SCHEMA-INVALID     a closed object was violated -> §8 clause 1 fails. Exit 1.
  * CAP-EXCEEDED       an array is longer than the cap the SAME document declares
                       for it -> §8 clause 4 fails. Exit 1. JSON Schema cannot
                       express "maxItems equals the value of a sibling field", so
                       this clause is unreachable from the schema and is checked
                       here instead. An UNDECLARED cap is not a violation: a
                       producer that omits the field declares no cap (SPEC §4.2).
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
import tempfile
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

# The one token `--pointer` adds to RFC 6901, and the reason it is safe to add.
# RFC 6901 §4 gives `-` a single meaning in an ARRAY: "the element after the last".
# That element never exists, so in an EVALUATION context — which is all this tool
# does — a pointer containing `-` at an array position can never resolve. The token
# is therefore free: nothing that used to resolve can start resolving differently.
# Against an OBJECT it stays a literal member name, exactly as RFC 6901 says, so a
# document with a member spelled `-` is still addressable.
POINTER_EACH = "-"

# Annotation keywords assert nothing about an instance. `{"description": "..."}`
# and `true` are THE SAME SCHEMA in Draft 2020-12, and an instrument that reads
# them differently is reading its own formatting rather than the standard.
ANNOTATION_KEYWORDS = frozenset((
    "description", "title", "$comment", "examples", "default",
    "deprecated", "readOnly", "writeOnly",
))


def constrains(node) -> bool:
    """Does this subschema assert ANYTHING about an instance?

    `false` does (it rejects everything). `true`, `{}` and `{"description": ...}`
    do not, and they are interchangeable spellings of the same schema — which is
    exactly what this predicate exists to stop the walkers below from confusing
    with a constraint. Measured 2026-08-24 on the shipped v0.9.0 pair: spelling
    `attribution.sketch_params`'s openness as `additionalProperties: true` instead
    of leaving it absent made the undescribed walker report every sketch parameter
    of a fully conformant document, five invented findings on one document, while
    `additionalProperties: {}` — the same schema — reported none.
    """
    if node is True:
        return False
    if node is False:
        return True
    if isinstance(node, dict):
        return any(keyword not in ANNOTATION_KEYWORDS for keyword in node)
    return True


def member_silent(subschema: dict) -> bool:
    """True when this subschema says NOTHING about which members an object carries.

    A deliberate "anything goes" (SPEC §7 extension payloads, §16.4 cube
    coordinates, `attribution.sketch_params`). Descending into one would report
    every key inside it as undescribed — a false positive on a surface the schema
    opened on purpose. Silence is read from the MEANING of the declaration, never
    from whether a keyword is spelled out: an author who writes the openness down
    instead of leaving it absent must not thereby arm a walker against himself.
    """
    if subschema.get("properties") or subschema.get("patternProperties"):
        return False
    for keyword in ("additionalProperties", "unevaluatedProperties"):
        if keyword in subschema and constrains(subschema[keyword]):
            return False
    return True


class InstrumentError(RuntimeError):
    """The validator cannot answer honestly. Always exit 2, never exit 0."""


# --------------------------------------------------------------------------
# Corpus loading. There is no path through this function that skips a line.
# --------------------------------------------------------------------------

def _pointer_escape(token: str) -> str:
    """A member name as an RFC 6901 reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def resolve_pointer(document, pointer: str, where: str) -> tuple[bool, list[tuple[str, object]]]:
    """RFC 6901 applied to a DOCUMENT rather than a schema, plus ONE extension.

    A MetaLog or a MetaLogDiff is often carried inside a larger envelope -- a CI
    report that quotes the diffs it was built from, for instance. Pointing at them
    is better than teaching every producer to publish bare documents.

    THE EXTENSION, and why an envelope forces it. An envelope carries as many
    documents as its producer performed comparisons; the shape a CI report actually
    takes is a LIST of them, not one. A pointer that can only name `/raw/0/diff`
    judges the first and reports the same confident verdict over the rest -- which
    is not a smaller check, it is a green that covers a subject nobody chose. So
    `POINTER_EACH` in an array position selects EVERY element, and each selected
    element becomes a document of its own, judged and counted separately.

    Returns `(expanded, [(concrete_pointer, node), ...])`. `expanded` is False when
    no array was iterated, and the caller then keeps the labels it already used: a
    subject that was one document stays one document under the name it had.

    Two things are FATAL here, never a skip, and they are the same defect seen from
    two sides: a pointer that does not resolve, and a pointer that resolves onto an
    EMPTY array. Silently dropping the file, or judging zero of its documents, both
    shrink the corpus -- and a corpus that shrank on its own is the one thing this
    instrument must never do.
    """
    frontier: list[tuple[str, object]] = [("", document)]
    expanded = False

    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        reached: list[tuple[str, object]] = []
        for prefix, node in frontier:
            at = prefix or "<root>"
            if isinstance(node, list):
                if token == POINTER_EACH:
                    expanded = True
                    if not node:
                        raise InstrumentError(
                            f"{where}: pointer {pointer!r} selects every element of "
                            f"the array at {at} — and that array is EMPTY, so this "
                            f"file contributes nothing. Zero documents is not a "
                            f"clean subject: a corpus that shrank to nothing is "
                            f"green for the one reason that matters, that it never "
                            f"looked.")
                    reached += [(f"{prefix}/{index}", item)
                                for index, item in enumerate(node)]
                    continue
                if not token.isdigit() or int(token) >= len(node):
                    raise InstrumentError(
                        f"{where}: pointer {pointer!r} does not resolve — {token!r} "
                        f"is not an index into the {len(node)}-element array at "
                        f"{at}. {POINTER_EACH!r} there selects every element of it.")
                reached.append((f"{prefix}/{token}", node[int(token)]))
            elif isinstance(node, dict):
                if token not in node:
                    hint = ""
                    if token == POINTER_EACH:
                        hint = (f" {POINTER_EACH!r} selects every element of an "
                                f"ARRAY; what sits at {at} is an object, so RFC "
                                f"6901 reads it as a literal member name — which "
                                f"is what an envelope looks like when its wire "
                                f"shape moved out from under the pointer.")
                    raise InstrumentError(
                        f"{where}: pointer {pointer!r} does not resolve — no member "
                        f"{token!r} at {at}. A document the pointer cannot reach is "
                        f"a corpus this run cannot judge, not one it may skip."
                        f"{hint}")
                reached.append((f"{prefix}/{_pointer_escape(token)}", node[token]))
            else:
                raise InstrumentError(
                    f"{where}: pointer {pointer!r} descends into a scalar at "
                    f"{token!r}")
        frontier = reached

    return expanded, frontier


def _select(document, pointer: str | None, where: str,
            label: str) -> tuple[bool, list[tuple[str, object]]]:
    """One parsed corpus entry -> the documents a pointer selects inside it.

    The label rule is the whole compatibility story. An expanding pointer renames
    each document to the CONCRETE pointer of the element it selected, so a finding
    names the element rather than the file it came from — over forty documents from
    two files, `1/40 documents` with no name is a number nobody can act on. Every
    other case keeps the label the caller already had.
    """
    if not pointer:
        return False, [(label, document)]
    expanded, selected = resolve_pointer(document, pointer, where)
    if not expanded:
        return False, [(label, selected[0][1])]
    return True, [(f"{label}{concrete}", node) for concrete, node in selected]


def load_corpus(path: Path, pointer: str | None = None) -> tuple[list[tuple[str, object]], dict]:
    """Return ([(label, document)], accounting).

    Accepts three shapes: a single `.json` document, JSONL, and the sectioned
    `### name ###` + JSONL form the published determinism evidence uses.
    `pointer` selects the document -- or, with `POINTER_EACH`, every document --
    inside a larger envelope (see resolve_pointer).

    THE DESIGN RULE: every non-blank line is classified as exactly one of
    {section header, document}. A line that parses as neither is fatal. There is
    no third bucket, so a parser bug cannot express itself as a smaller document
    count -- it can only stop the run. An expanding pointer extends the rule
    rather than bending it: one entry may now yield MANY documents, never zero,
    and `accounting["documents"]` counts what was actually judged, so
    `--expect-documents` still reconciles against the whole subject.
    """
    if not path.is_file():
        raise InstrumentError(f"corpus does not exist: {path}")
    text = path.read_text(encoding="utf-8")

    if path.suffix == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InstrumentError(f"{path}: not a JSON document — {exc}") from exc
        expanded, selected = _select(doc, pointer, str(path), path.name)
        return selected, {"lines": 1, "blank": 0, "sections": 0,
                          "documents": len(selected), "expanded": expanded}

    lines = text.splitlines()
    sectioned = any(SECTION_RE.match(ln.strip()) for ln in lines)
    docs: list[tuple[str, object]] = []
    section = path.stem
    ordinal = 0
    blank = 0
    sections = 0
    expanded = False

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
        selected_here, selected = _select(doc, pointer, f"{path}:{lineno}",
                                          f"{section}#{ordinal}")
        expanded = expanded or selected_here
        docs += selected

    if not docs:
        raise InstrumentError(
            f"{path}: zero documents parsed. An empty corpus is an instrument "
            f"failure, never a clean result — a gate with nothing to judge is green "
            f"for the one reason that matters: it never looked."
        )
    return docs, {"lines": len(lines), "blank": blank, "sections": sections,
                  "documents": len(docs), "expanded": expanded}


# --------------------------------------------------------------------------
# Schema plumbing shared by both species.
# --------------------------------------------------------------------------

def _declared_formats(schema) -> set[str]:
    """Every `format` value the schema declares anywhere. Drives the
    --check-formats teeth check: the set is derived from the artifact, never
    enumerated, so it cannot lag a schema edit."""
    found: set[str] = set()
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            value = node.get("format")
            if isinstance(value, str):
                found.add(value)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


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
        if all(member_silent(s) for s in subschemas):
            return  # unconstrained by design — see member_silent
        closed = any(s.get("additionalProperties") is False for s in subschemas)
        # Only a CONSTRAINING value schema describes the extras. An open
        # declaration carrying nothing but its reason (`{"description": ...}`)
        # describes nothing, and treating it as a describer would silence the
        # undescribed species at exactly the two open roots.
        fallback: list[dict] = []
        for s in subschemas:
            extra = s.get("additionalProperties")
            if isinstance(extra, dict) and constrains(extra):
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

# --------------------------------------------------------------------------
# SPEC §8 clause 4 — an array is truthfully bounded by the cap its own document
# declares. The schema cannot reach this: `maxItems` takes a constant, and the
# bound here is the value of a sibling field, so a schema-only test is blind to
# it by construction. That is why the clause was declared unchecked until now.
# --------------------------------------------------------------------------

# The pair set is DERIVED FROM THE SCHEMA, never hand-kept: any integer property
# named `<x>_size` whose sibling `<x>` is an array is a cap and its array. A pair
# added to the schema tomorrow is checked on arrival; a hand-kept list would not
# be, and its rot would be silent. `behavior.ngram_size` is correctly excluded —
# it is the gram width, and no sibling array is named `ngram`.
#
# One pair cannot be derived and is declared: the cube's budget is named for
# §16.10's BUDGET object, not for the array it bounds.
DECLARED_CAP_PAIRS = {("cell_budget", "cells")}

# `extensions` is vendor space (SPEC §7). A vendor object that happens to carry
# `foo_size` beside `foo` is not making a claim this standard may adjudicate.
CAP_WALK_SKIP = {"extensions"}


def derive_cap_pairs(schema) -> set[tuple[str, str]]:
    """Every (cap field, array field) pair the schema declares."""
    pairs = set(DECLARED_CAP_PAIRS)

    def visit(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for name, sub in props.items():
                    if not name.endswith("_size") or not isinstance(sub, dict):
                        continue
                    if sub.get("type") != "integer":
                        continue
                    sibling = props.get(name[: -len("_size")])
                    if isinstance(sibling, dict) and sibling.get("type") == "array":
                        pairs.add((name, name[: -len("_size")]))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return pairs


def collect_cap_violations(docs, pairs: set[tuple[str, str]]) -> list[dict]:
    """Where a declared cap is present and the array it names overruns it."""
    by_class: dict[tuple[str, str, int, int], set[int]] = defaultdict(set)

    def walk(node, path: str, index: int, depth: int):
        if depth > MAX_INSTANCE_DEPTH:
            raise InstrumentError(
                f"instance depth exceeded {MAX_INSTANCE_DEPTH} at {path} — refusing "
                f"to report on a document this reader cannot have walked fully."
            )
        if isinstance(node, dict):
            for cap_key, array_key in pairs:
                cap = node.get(cap_key)
                array = node.get(array_key)
                if isinstance(cap, bool) or not isinstance(cap, int):
                    continue
                if not isinstance(array, list) or len(array) <= cap:
                    continue
                by_class[(path or "<root>", cap_key, cap, len(array))].add(index)
            for key, value in node.items():
                if key in CAP_WALK_SKIP:
                    continue
                walk(value, f"{path}.{key}" if path else key, index, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, f"{path}[]", index, depth + 1)

    for index, (_, doc) in enumerate(docs):
        walk(doc, "", index, 0)

    return sorted(
        ({"path": path, "cap": cap_key, "declared": declared, "actual": actual,
          "documents": len(indexes)}
         for (path, cap_key, declared, actual), indexes in by_class.items()),
        key=lambda v: (v["path"], v["cap"]),
    )


def render(report: dict, stream) -> None:
    w = lambda s="": print(s, file=stream)
    env = report["environment"]
    acc = report["accounting"]
    plural = lambda n, word: f"{n} {word}" if n == 1 else f"{n} {word}s"
    w('metalog-conformance · SPEC §8 clauses 1 and 4')
    for entry in report["corpus"]:
        w(f"  corpus     : {entry['path']}  "
          f"({plural(entry['documents'], 'document')} judged)")
    if report.get("pointer"):
        note = "the document inside the envelope"
        if report.get("pointer_expanded"):
            note = (f"{POINTER_EACH!r} selects EVERY element of the array it "
                    f"addresses — {plural(acc['documents'], 'document')} judged "
                    f"across {plural(len(report['corpus']), 'file')}, not the "
                    f"first of each")
        w(f"  pointer    : {report['pointer']}  ({note})")
    w(f"  kind       : {report['kind']}  (schema/{report['schema']})")
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

    if report["cap_violations"]:
        w("CAP-EXCEEDED — an array is longer than the cap its own document declares. "
          "§8 clause 4 FAILS:")
        for v in report["cap_violations"]:
            w(f"  {v['path']} — {v['cap']} declares {v['declared']}, "
              f"array holds {v['actual']} "
              f"({v['documents']}/{acc['documents']} documents)")
    else:
        w("CAP-EXCEEDED — none. Every DECLARED cap bounds its array. A cap a "
          "producer does not declare is not checked and is not a violation.")
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
    w("SCOPE — this tests SPEC §8 clause 1 (schema validation) and clause 4 (an")
    w("  array is truthfully bounded by the cap the same document declares).")
    w("  NOT checked: clause 2 (every required field populated per its definition —")
    w("  only the schema-expressible part of it is), clause 3 (template_id computed")
    w("  per §3.2 — no pinned cross-implementation vector exists yet). A green above")
    w("  says nothing about those two.")
    w("  Clause 4's own limit: a cap that is not DECLARED cannot be checked. A")
    w("  producer that omits `behavior.branching_size` declares no cap (§4.2), and")
    w("  this tool reads that as a posture, never as a pass.")
    w("  See conformance/README.md § What this does not reach.")
    w()
    w(f"VERDICT: {report['verdict']}")


# --------------------------------------------------------------------------
# The run.
# --------------------------------------------------------------------------

def run(corpora, kind: str, schema_dir: Path, spec_text: str, check_formats: bool,
        expect_documents: int | None, pointer: str | None = None) -> dict:
    import jsonschema
    from importlib import metadata

    schema_name = SCHEMAS[kind]
    schema_path = schema_dir / schema_name
    if not schema_path.is_file():
        raise InstrumentError(f"schema not found: {schema_path} (pass --schema-dir)")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    fmt = None
    if check_formats:
        # jsonschema registers a format checker only when the matching optional
        # validator is importable (rfc3339-validator for date-time,
        # rfc3986-validator for uri — see requirements.txt). A bare FormatChecker
        # silently SKIPS every format it has no checker for, so in a partial
        # environment this flag would assert nothing while claiming to assert —
        # measured 2026-08-19: an empty-string date-time read CONFORMANT. The set
        # to demand is derived from the schema itself, never hand-kept, so a
        # format added to the schema tomorrow demands its checker on arrival.
        fmt = jsonschema.FormatChecker()
        declared = _declared_formats(schema)
        unenforceable = sorted(declared - set(fmt.checkers))
        if unenforceable:
            raise InstrumentError(
                f"--check-formats was requested but this environment has no "
                f"checker for format(s) {unenforceable} that the schema declares "
                f"— `pip install -r conformance/requirements.txt`. An assertion "
                f"the instrument cannot perform must refuse, never pass silently."
            )
    validator = jsonschema.Draft202012Validator(schema, format_checker=fmt)

    docs: list[tuple[str, object]] = []
    accounting = {"lines": 0, "blank": 0, "sections": 0, "documents": 0}
    # ONE entry per corpus, carrying its own document count rather than only the
    # total. A caller pinning the total with --expect-documents already reds on any
    # shrink; a HUMAN reading the output needs to know WHICH file stopped carrying
    # what it used to, and under an expanding pointer the per-file number is the
    # only place that is visible.
    corpus: list[dict] = []
    for path in corpora:
        part, acc = load_corpus(Path(path), pointer)
        docs += part
        for k in accounting:
            accounting[k] += acc[k]
        corpus.append({"path": str(path), "documents": acc["documents"],
                       "expanded": acc["expanded"]})

    if expect_documents is not None and accounting["documents"] != expect_documents:
        raise InstrumentError(
            f"expected {expect_documents} documents, parsed {accounting['documents']}. "
            f"A count that does not reconcile means the corpus moved or the reader is "
            f"blind to part of it — either way the verdict below would be about a "
            f"different corpus than the caller believes."
        )

    findings, _ = collect_findings(docs, validator)
    undescribed = collect_undescribed(docs, schema)
    cap_violations = collect_cap_violations(docs, derive_cap_pairs(schema))
    names = [n for f in findings for n in f["properties"]] + [u["key"] for u in undescribed]

    return {
        "corpus": corpus,
        "pointer": pointer,
        "pointer_expanded": any(entry["expanded"] for entry in corpus),
        "kind": kind,
        "schema": schema_name,
        "accounting": accounting,
        "findings": findings,
        "cap_violations": cap_violations,
        "undescribed": undescribed,
        "spec_mentions": spec_mentions(names, spec_text),
        "verdict": "NONCONFORMANT" if (findings or cap_violations) else "CONFORMANT",
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

MANIFEST_NAME = "manifest.json"

# Files under `fixtures/` that are documentation ABOUT the corpus rather than
# members of it. Kept to a suffix so a new corpus file in an unforeseen encoding
# (`.ndjson`, say) is still censused: an extension allowlist would silently
# narrow the sweep, which is the same defect one level down from the one the
# census closes.
NON_CORPUS_SUFFIXES = {".md"}


def census_fixture_files(fixtures_dir: Path, listed: set[str],
                         unadjudicated: set[str]
                         ) -> tuple[list[str], list[str], dict[str, int], int]:
    """Join the fixture files ON DISK against the paths `manifest.json` lists.

    Returns `(unlisted, absent, shadowed, considered)`:
      * `unlisted`   files present in the corpus that no manifest entry names —
                     the defect this exists for. Such a file is judged by
                     nothing, forever, while the self-test's closing count
                     ("22/22 fixtures") reads as coverage OF THE CORPUS when it
                     is only coverage of the list.
      * `absent`     manifest entries naming a file that is not there — the
                     reverse leg. It already failed later, in the corpus reader,
                     as an unreadable-file error; named here it is a manifest
                     defect rather than a mystery mid-run.
      * `shadowed`   per declared unadjudicated directory, how many files it
                     holds. Printed every run: an exemption that grows is then
                     visible, which is the only thing that keeps it honest.
      * `considered` how many files the join actually judged.

    Pure: it takes a directory and two sets and touches nothing else, so the
    control below can exercise every branch on a synthetic tree.
    """
    unlisted: list[str] = []
    shadowed: dict[str, int] = {d: 0 for d in sorted(unadjudicated)}
    considered = 0
    for path in sorted(fixtures_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(fixtures_dir).as_posix()
        if rel == MANIFEST_NAME:
            continue
        top = rel.split("/", 1)[0]
        # The shadow is tested BEFORE the suffix rule on purpose: the count
        # printed for a declared directory is the size of the whole directory,
        # not the size of the part that happens to look like a corpus.
        if top in shadowed:
            shadowed[top] += 1
            continue
        if path.suffix in NON_CORPUS_SUFFIXES:
            continue
        considered += 1
        if rel not in listed:
            unlisted.append(rel)
    absent = sorted(rel for rel in listed if not (fixtures_dir / rel).is_file())
    return unlisted, absent, shadowed, considered


def census_control() -> None:
    """Prove the census arm can fire, and that a declared shadow survives it.

    A structural refusal nobody has watched fail is the same evidence as a gate
    nobody has watched fail: none. This runs on a synthetic tree every self-test,
    so the arm is proven on the same invocation it judges with, and it exercises
    all four returns — the stowaway is caught, the shadowed file is not, the
    manifest and a `.md` are out of subject, and a listed-but-missing path is
    reported from the other side.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "valid").mkdir()
        (root / "shadow").mkdir()
        for rel in (MANIFEST_NAME, "README.md", "valid/listed.metalog.jsonl",
                    "valid/stowaway.metalog.jsonl", "shadow/unlisted.diff.json"):
            (root / rel).write_text("", encoding="utf-8")
        listed = {"valid/listed.metalog.jsonl"}

        unlisted, absent, shadowed, considered = census_fixture_files(
            root, listed, {"shadow"})
        if unlisted != ["valid/stowaway.metalog.jsonl"]:
            raise InstrumentError(
                f"census control: an unlisted fixture was NOT caught — expected "
                f"['valid/stowaway.metalog.jsonl'], got {unlisted!r}. The arm is "
                f"dead, so its silence over the real corpus means nothing.")
        if shadowed != {"shadow": 1}:
            raise InstrumentError(
                f"census control: the declared unadjudicated directory did not "
                f"survive — expected {{'shadow': 1}}, got {shadowed!r}. Either the "
                f"shadow stopped shadowing (its files would now red) or it stopped "
                f"counting (its growth would be invisible).")
        if considered != 2 or absent:
            raise InstrumentError(
                f"census control: the join judged {considered} file(s) and reported "
                f"absent={absent!r}; expected 2 and none. `{MANIFEST_NAME}` and "
                f"`.md` must be out of subject, and nothing listed was missing.")

        _, absent, _, _ = census_fixture_files(
            root, listed | {"valid/ghost.metalog.jsonl"}, {"shadow"})
        if absent != ["valid/ghost.metalog.jsonl"]:
            raise InstrumentError(
                f"census control: a manifest entry naming a file that is not there "
                f"was NOT caught — expected ['valid/ghost.metalog.jsonl'], got "
                f"{absent!r}.")


REQUIRED_CONTROLS = {
    "multi-document-section",       # forecloses green-BLIND on the sectioned form
    "undescribed-false-positive",   # forecloses a walker that invents findings
    "closed-object-violation",      # forecloses can't-FAIL on species 1
    "instrument-failure",           # forecloses a corrupt corpus reading as clean
    "declared-cap-violation",       # forecloses can't-FAIL on §8 clause 4
    "pointer-array-every-element",  # forecloses judging element 0 of an N-element
                                    # envelope and printing the verdict of all N
    "pointer-empty-selection",      # forecloses an array that shrank to zero
                                    # reading as a clean, truthful pass
    "pointer-token-literal-in-object",  # forecloses an extension that quietly
                                    # redefines the base standard it extends
}


def _grammar(node):
    """A subschema with its prose stripped — what two mirrored `$defs` must share.

    `description` is the only exclusion, and it is deliberate: a copy has to be able
    to say that it IS one, and the sentence naming its source is what keeps the
    duplication maintainable.
    """
    if isinstance(node, dict):
        return {k: _grammar(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_grammar(item) for item in node]
    return node


def _drift_detail(key: str, left: str, right: str, loaded: dict) -> str:
    """A lead a reader can act on, not just the word `differ`."""
    left_props = set(loaded[left]["$defs"][key].get("properties", {}))
    right_props = set(loaded[right]["$defs"][key].get("properties", {}))
    only_left, only_right = sorted(left_props - right_props), sorted(right_props - left_props)
    if only_left or only_right:
        return (f"$defs/{key}: properties only in {left}: {only_left or '[]'} · "
                f"only in {right}: {only_right or '[]'}")
    return f"$defs/{key}: same property names, different grammar ({left} vs {right})"


def mirrored_defs(loaded: dict[str, dict]) -> list[str]:
    """A `$defs` name defined in more than one shipped schema must define the SAME
    grammar in each. Exit 2 when it does not.

    The schema files are independently consumable published artifacts — SPEC §8
    invites downloading one alone — and this validator resolves only in-document
    pointers, so a grammar both files need is DUPLICATED rather than
    cross-referenced. A duplicate that can drift is worse than no duplicate: it
    publishes one name with two meanings, and whoever downloaded a single file has
    no way to notice. Measured once already: `band_floor` joined `$defs/cube_axis`
    in one file in v0.8.0 and not in the other, and a diff of two collapsed cubes
    was rejected by the diff schema while both of its inputs validated.

    Derived from the artifacts, never enumerated: a mirror added tomorrow is checked
    on arrival, and one deleted stops being checked with no list left to prune.
    """
    homes: dict[str, list[str]] = defaultdict(list)
    for name, schema in loaded.items():
        for key in schema.get("$defs", {}):
            homes[key].append(name)

    checked: list[str] = []
    drifted: list[str] = []
    for key, names in sorted(homes.items()):
        if len(names) < 2:
            continue
        checked.append(key)
        first = names[0]
        for other in names[1:]:
            if _grammar(loaded[first]["$defs"][key]) != _grammar(loaded[other]["$defs"][key]):
                drifted.append(_drift_detail(key, first, other, loaded))
    if drifted:
        raise InstrumentError(
            "the shipped schemas define one name two ways — mirrored $defs have "
            "drifted: " + " · ".join(drifted) + ". A file downloaded on its own "
            "cannot notice this, so the copies must agree in every keyword but "
            "`description`."
        )
    return checked


# In-place applicators constrain the position they sit in; they are not positions
# of their own. `additionalProperties: false` inside an `if` changes the CONDITION,
# and inside a `then` it closes the object — so demanding a declaration on one of
# these fragments would order an author to break his own schema. Measured on the
# shipped v0.9.0 pair: seven such fragments carry `required`/`properties` and no
# `type` (`$defs/coordinate`'s two `oneOf` branches and their three `not`s,
# `$defs/cube_axis`'s `if` and `then`, in each file).
IN_PLACE_APPLICATORS = ("allOf", "anyOf", "oneOf", "if", "then", "else", "not",
                        "dependentSchemas")

# The keywords that carry a subschema to a DOCUMENT LOCATION — a place an instance
# value actually sits. Walking only these is what keeps the census honest in both
# directions: it reaches every position, and it invents none.
LOCATION_SUBSCHEMA = ("additionalProperties", "items", "contains",
                      "unevaluatedProperties")
LOCATION_MAP = ("properties", "patternProperties", "$defs")
LOCATION_LIST = ("prefixItems",)


def _is_object_position(node: dict) -> bool:
    """Can an OBJECT sit here?

    Two arms, and the second is the one that closes the hole the first leaves.
    A subschema declaring `type: object` is a position. So is a subschema that
    declares NO type at all while naming members — that is an object position
    whose author forgot to say so, and a census keyed on `type` alone would skip
    exactly the sloppiest node in the file.
    """
    declared = node.get("type")
    if declared == "object" or (isinstance(declared, list) and "object" in declared):
        return True
    if declared is not None:
        return False
    return bool(node.get("properties") or node.get("patternProperties")
                or node.get("required"))


def object_positions(schema: dict) -> list[tuple[str, dict]]:
    """Every object position in one shipped schema, as (JSON Pointer, subschema).

    Derived from the artifact, never enumerated. A position added tomorrow is
    checked on arrival and one deleted stops being checked with no list to prune —
    which is the whole reason this exists rather than a census somebody re-derives.
    """
    found: list[tuple[str, dict]] = []
    seen: set[int] = set()

    def visit(node, pointer: str, in_place: bool) -> None:
        if not isinstance(node, dict) or id(node) in seen:
            return
        seen.add(id(node))
        if not in_place and _is_object_position(node):
            found.append((pointer, node))
        for keyword in LOCATION_SUBSCHEMA:
            if isinstance(node.get(keyword), dict):
                visit(node[keyword], f"{pointer}/{keyword}", False)
        for keyword in LOCATION_MAP:
            for name, sub in (node.get(keyword) or {}).items():
                visit(sub, f"{pointer}/{keyword}/{_pointer_escape(name)}", False)
        for keyword in LOCATION_LIST:
            for index, sub in enumerate(node.get(keyword) or []):
                visit(sub, f"{pointer}/{keyword}/{index}", False)
        # An in-place applicator's subschema shares its parent's location, so we
        # keep walking (a `then` can carry `properties` whose values are real
        # positions) while refusing to CENSUS the fragment itself.
        for keyword in IN_PLACE_APPLICATORS:
            branch = node.get(keyword)
            if isinstance(branch, dict):
                visit(branch, f"{pointer}/{keyword}", True)
            elif isinstance(branch, list):
                for index, sub in enumerate(branch):
                    visit(sub, f"{pointer}/{keyword}/{index}", True)

    visit(schema, "#", False)
    return found


def declared_closure(loaded: dict[str, dict]) -> int:
    """Every object position in every shipped schema must DECLARE its closure.

    Three legal dispositions, and no fourth:

      `additionalProperties: false`               closed — the members are named
      a CONSTRAINING value schema                 a map: closed over its VALUES,
                                                  never over its key set
      `{"description": "<why it is open>"}`       open, with its reason attached

    An **absent** `additionalProperties` is the defect this exists to catch,
    because absence is not a disposition — it is the lack of one. Two positions in
    the shipped v0.9.0 metalog schema are byte-identical `{"type": "object"}` and
    mean opposite things: `provenance[].source` is a standard object whose members
    §12.4 names, and `attribution.sketch_params` is a map whose keys are data. No
    property of the schema text separates them; only the prose does. So the census
    of what is open cannot be maintained by reading the schema, and a hand-kept
    list of exemptions beside it would rot on the next release — which is how a
    literal execution of "close every open object" nearly shipped
    `additionalProperties: false` onto a REQUIRED map, invalidating every document
    carrying `attribution`.

    **A bare `true` is refused, and the reason is measured, not stylistic.** `true`
    is the one spelling with nowhere to put the why. Accepting it against a
    node-level `description` would have passed both document roots vacuously on
    sentences that describe the DOCUMENT TYPE ("Pair-wise difference between two
    MetaLog documents") and say nothing about why the root admits unknown members —
    a check that goes green on the two positions it exists to interrogate.
    `{"description": ...}` is the same schema as `true` in Draft 2020-12, so this
    costs no document its validity; it costs an author one sentence, at the only
    place a reader will look for it.

    Exit 2, like a `$defs` drift: this is the standard's own artifacts failing to
    say what they mean, and no verdict about anyone's documents is honest
    underneath it.
    """
    defects: list[str] = []
    counted = 0
    for name, schema in sorted(loaded.items()):
        for pointer, node in object_positions(schema):
            counted += 1
            if "additionalProperties" not in node:
                defects.append(
                    f"{name} {pointer}: no `additionalProperties` — absence is not a "
                    f"disposition. Declare `false`, a value schema, or "
                    f'`{{"description": "<why it is open>"}}`.')
                continue
            extra = node["additionalProperties"]
            if constrains(extra):
                continue
            if extra is True or "description" not in extra:
                defects.append(
                    f"{name} {pointer}: open, with no reason attached. An open "
                    f'position declares `{{"description": "<why>"}}`; bare `true` '
                    f"leaves the reason nowhere, and a description on the node "
                    f"itself describes the node, not its openness.")
    if defects:
        raise InstrumentError(
            f"the shipped schemas do not declare their own closure at "
            f"{len(defects)} of {counted} object position(s): "
            + " · ".join(defects))
    return counted


def _tuples(findings):
    return [(f["path"], f["keyword"], tuple(f["properties"]), f["errors"], f["documents"])
            for f in findings]


def _undescribed_tuples(entries):
    return [(u["path"], u["key"], u["documents"]) for u in entries]


def _cap_tuples(entries):
    return [(v["path"], v["cap"], v["declared"], v["actual"], v["documents"])
            for v in entries]


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

    # ── THE CORPUS CENSUS. Until 2026-08-31 this self-test iterated `fixtures`
    # from the manifest and never the filesystem, so a fixture FILE that was
    # never listed was judged by nothing, forever — and the closing count read
    # as coverage of the corpus when it was only coverage of the list. The join
    # below is the one arm that closes it, and its own control runs first.
    census_control()

    # The shadow is DECLARED DATA, in the oracle, with a reason per entry — never
    # a set hard-coded here. A directory deliberately outside the adjudicated
    # corpus is a decision (`fixtures/unarmed/` holds fixtures authored against a
    # rule the schemas cannot yet express: wiring them would assert a verdict
    # against a schema that cannot answer the question). A reason nobody wrote
    # down is a defect that looks like a decision, so an empty one refuses here.
    shadow = manifest.get("unadjudicated_directories", {})
    if not isinstance(shadow, dict):
        raise InstrumentError(
            f"`unadjudicated_directories` in {manifest_path.name} must be an object "
            f"mapping a directory name to the reason it is outside the adjudicated "
            f"corpus; got {type(shadow).__name__}.")
    for name, reason in sorted(shadow.items()):
        if not isinstance(reason, str) or not reason.strip():
            raise InstrumentError(
                f"`unadjudicated_directories['{name}']` carries no reason. A "
                f"directory this self-test agrees not to judge must say why it is "
                f"exempt, or the exemption is indistinguishable from an oversight.")

    fixtures_dir = TOOL_DIR / "fixtures"
    listed = {fx["path"] for fx in fixtures}
    unlisted, absent, shadowed, considered = census_fixture_files(
        fixtures_dir, listed, set(shadow))
    if unlisted:
        raise InstrumentError(
            f"{len(unlisted)} fixture file(s) under {fixtures_dir.name}/ are named by "
            f"NO entry in {manifest_path.name}: {unlisted}. Such a file is judged by "
            f"nothing and this self-test would still print a full count, which reads "
            f"as coverage it never had. List it with its expectation, or declare its "
            f"directory in `unadjudicated_directories` with the reason.")
    if absent:
        raise InstrumentError(
            f"{len(absent)} entry/entries in {manifest_path.name} name a file that is "
            f"not there: {absent}. The oracle outlived its subject.")
    w(f"  fixture census: {considered} corpus file(s) on disk, all named by "
      f"{manifest_path.name} ({len(fixtures)} entries over {len(listed)} distinct path(s))")
    for name, reason in sorted(shadow.items()):
        held = shadowed.get(name, 0)
        state = f"{held} file(s) skipped" if held else "no file at this ref"
        w(f"    unadjudicated by declaration: {name}/ — {state} — {reason}")

    import jsonschema
    loaded: dict[str, dict] = {}
    for kind, name in sorted(SCHEMAS.items()):
        path = schema_dir / name
        if not path.is_file():
            raise InstrumentError(f"shipped schema missing: {path}")
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        loaded[name] = schema
        w(f"  schema {name}: valid Draft 2020-12")

    mirrors = mirrored_defs(loaded)
    w(f"  mirrored $defs agree across the shipped schemas: "
      f"{', '.join(mirrors) if mirrors else 'no name is defined twice'}")

    positions = declared_closure(loaded)
    w(f"  every object position declares its closure: {positions} position(s) walked")

    failures: list[str] = []
    for fx in fixtures:
        path = TOOL_DIR / "fixtures" / fx["path"]
        want = fx["expect"]
        # An EXPANDING pointer must pin which element each finding came from. The
        # demand is derived from the fixture's own pointer, never from a list kept
        # beside it: `1 of 40 documents` with no element named is a count a reader
        # cannot act on, and a fixture that asserted only the count would pass
        # against a walker that mislabels every finding. `want["exit"] != 2` is not
        # an escape hatch — an exit-2 fixture has no findings to name.
        if (want["exit"] != 2 and fx.get("pointer")
                and POINTER_EACH in fx["pointer"].lstrip("/").split("/")
                and "first_documents" not in want):
            raise InstrumentError(
                f"fixture {fx['path']} points with {fx['pointer']!r}, which selects "
                f"every element of an array, and declares no `first_documents`. A "
                f"fixture over an expanded corpus must say WHICH element each "
                f"finding came from; asserting the count alone passes against a "
                f"validator that judges all of them and names the wrong one.")
        # A REFUSAL must be pinned to its reason, not merely to its exit code, on
        # every fixture whose subject is the pointer. `exit: 2` alone cannot tell
        # "the envelope's wire shape moved out from under this pointer" apart from
        # "the pointer walked into a scalar" — and a resolver that quietly gave a
        # token a second meaning refuses BOTH ways, for different reasons, while
        # passing a fixture that reads only the number. Derived from the fixture's
        # own shape, so it cannot be forgotten on the next one.
        if want["exit"] == 2 and fx.get("pointer") and "refusal_mentions" not in want:
            raise InstrumentError(
                f"fixture {fx['path']} expects a refusal on pointer "
                f"{fx['pointer']!r} and declares no `refusal_mentions`. Exit 2 is a "
                f"class, not a reason: a fixture that asserts only the number passes "
                f"against an instrument refusing for a reason nobody intended.")
        try:
            report = run([path], fx["kind"], schema_dir, spec_text, False,
                         want.get("documents"), fx.get("pointer"))
            code = 1 if (report["findings"] or report["cap_violations"]) else 0
            got = {
                "exit": code,
                "documents": report["accounting"]["documents"],
                "findings": _tuples(report["findings"]),
                "cap_violations": _cap_tuples(report["cap_violations"]),
                "undescribed": _undescribed_tuples(report["undescribed"]),
                "first_documents": [f["first_document"] for f in report["findings"]],
            }
        except InstrumentError as exc:
            got = {"exit": 2, "documents": None, "findings": None,
                   "cap_violations": None, "undescribed": None,
                   "first_documents": None, "why": str(exc)}

        expected = {
            "exit": want["exit"],
            "documents": want.get("documents") if want["exit"] != 2 else None,
            "findings": [tuple(t[:2]) + (tuple(t[2]), t[3], t[4])
                         for t in want.get("findings", [])] if want["exit"] != 2 else None,
            "cap_violations": [tuple(t) for t in want.get("cap_violations", [])]
                              if want["exit"] != 2 else None,
            "undescribed": [tuple(t) for t in want.get("undescribed", [])]
                           if want["exit"] != 2 else None,
        }
        # Compared only where the manifest declares it: naming the document a
        # finding first appeared in is an ADDITIONAL assertion, demanded above
        # exactly where it is load-bearing.
        if want["exit"] != 2 and "first_documents" in want:
            expected["first_documents"] = list(want["first_documents"])
        if want["exit"] == 2 and "refusal_mentions" in want:
            expected["refusal_reason"] = want["refusal_mentions"]
            said = got.get("why")
            got["refusal_reason"] = (want["refusal_mentions"] if said is not None
                                     and want["refusal_mentions"] in said else said)
        ok = all(got.get(k) == expected[k] for k in expected)
        # The pointer is part of the fixture's identity: one file carries several
        # entries, and a PASS/FAIL line naming only the path cannot say which.
        subject = fx["path"] + (f"  --pointer {fx['pointer']}" if fx.get("pointer") else "")
        w(f"  [{'PASS' if ok else 'FAIL'}] {subject}  ({fx['why']})")
        if not ok:
            failures.append(subject)
            for k in sorted(expected):
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
    parser.add_argument("--pointer", default=None,
                        help="RFC 6901 JSON Pointer to the document INSIDE a larger "
                             "envelope, e.g. --pointer /raw for a CI report that "
                             "quotes the diff it was built from. One extension: "
                             f"{POINTER_EACH!r} in an ARRAY position selects EVERY "
                             "element and judges each as its own document — "
                             f"--pointer /raw/{POINTER_EACH}/diff over a report "
                             "carrying twenty comparisons judges twenty, and the "
                             "count is in the output. A pointer that does not "
                             "resolve, or that selects an EMPTY array, is exit 2 — "
                             "never a skipped file and never a green over nothing.")
    parser.add_argument("--check-formats", action="store_true",
                        help="assert `format` (date-time, uri). OFF by default: "
                             "Draft 2020-12's default vocabulary makes format an "
                             "ANNOTATION, so asserting it is stricter than §8 clause 1. "
                             "Needs the optional format validators from "
                             "requirements.txt and REFUSES to run (exit 2) without "
                             "them — a checker-less assertion would pass everything.")
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
                     args.check_formats, args.expect_documents, args.pointer)
    except InstrumentError as exc:
        print(f"::error::instrument failure — {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        render(report, sys.stdout)

    if report["findings"] or report["cap_violations"]:
        return 1
    if args.strict_undescribed and report["undescribed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
