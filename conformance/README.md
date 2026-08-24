# conformance — the test `SPEC.md` §8 declares

`SPEC.md` §8 closes with:

> There is no central conformance authority. **The schema is the test.**

This directory is that test, made runnable. It ships **with the standard** rather
than with any implementation, because a conformance test only an editor can run is
not a conformance test: an external implementer must be able to check their own
producer without asking anyone.

```
pip install -r conformance/requirements.txt

# Prove the instrument has teeth before believing anything it says.
python3 conformance/metalog_validate.py --selftest

# Judge your own documents.
python3 conformance/metalog_validate.py my_metalogs.jsonl
python3 conformance/metalog_validate.py --kind diff my_diff.json
```

---

## What it reports, and why it never reports one number

A single "N errors" number hides three findings with different owners — and one of
them is not a failure at all. This tool never adds them together.

**SCHEMA-INVALID** — a document violated a *closed* object (`additionalProperties:
false`), a `required` member is missing, a value failed its `type`/`pattern`/bound.
This is §8 clause 1 failing. **Exit 1.**

**CAP-EXCEEDED** — an array is longer than the cap the *same document* declares
for it: `stats.top_k` past `stats.top_k_size`, `stats.reservoir` past
`stats.reservoir_size`, `behavior.branching` past `behavior.branching_size`,
`cube.cells` past `cube.cell_budget`. This is §8 clause 4 failing. **Exit 1.**

The schema cannot reach this defect, and that is not an oversight in the schema:
JSON Schema's `maxItems` takes a *constant*, while the bound here is the *value
of a sibling field*. A document can therefore be perfectly schema-valid and
still lie about its own bound — which is exactly what the
`invalid/cap_exceeded.metalog.jsonl` fixture is.

The pair set is **derived from the schema**, never hand-kept: an integer
property `<x>_size` whose sibling `<x>` is an array is a cap and its array, so a
pair added to the schema tomorrow is checked on arrival. `cube.cell_budget` is
the one declared exception, because it is named for §16.10's BUDGET object
rather than for the array it bounds. Objects under `extensions` are skipped —
that is vendor space (§7), and a vendor's own `foo_size` is not a claim this
standard may adjudicate.

**An undeclared cap is not a violation.** A producer that omits
`behavior.branching_size` declares no cap (§4.2); the tool reads that as a
posture and says so, rather than assuming a default and going green.

**LEGAL-BUT-UNDESCRIBED** — a member that an *open* container permits and that no
schema describes. The MetaLog root is open by design, so this is **not** a
conformance failure and never changes the exit code. It is reported because a
producer emitting one is doing one of two things, and the distinction matters:

- riding ahead of a schema that lags its own prose (a **schema lag** — GOVERNANCE
  §3 makes this the spec's problem, not the implementation's), or
- extending the format outside §7 `extensions`, where vendor data belongs.

To help tell those apart, each reported member is tagged `[in SPEC.md]` or
`[nowhere]` — does the prose name it *as a member* (a code span or a quoted key)?
**That tag is a lead, not a verdict.** A member whose name is also a code span for a
different concept in another section reads `[in SPEC.md]` and is not a schema lag.
Open the section before acting on it.

The two species are **disjoint by construction**: a member rejected by a closed
object is never also counted as undescribed.

---

## Exit codes are a contract

| code | meaning |
|---|---|
| **0** | conformant against the schema |
| **1** | findings — at least one document is schema-invalid |
| **2** | **the instrument could not run honestly** and has no verdict |

Exit 2 is not a softer failure, it is a *different* one: an unreadable line, an
empty corpus, a document count that did not match `--expect-documents`, a missing
schema, an unresolvable `$ref`, a failed self-test. A caller that treats 2 as 1
loses the distinction between "your documents are wrong" and "repair the
instrument"; a caller that treats 2 as 0 has a gate that goes green because it
never looked.

---

## Why the self-test exists

A validator that cannot fail is decoration. `--selftest` runs fourteen fixtures whose
expected results are **hand-authored in `fixtures/manifest.json` from the spec and
the schemas** — never captured from a run, because an expectation copied out of the
tool under test makes the tool its own oracle, and the pair then agree forever
while both are wrong.

Six of those fixtures carry a `control` tag, naming **five** distinct blindnesses
(`instrument-failure` is carried by two), and the self-test **refuses to run**
if any tag is missing from the manifest — deleting a fixture cannot quietly widen
what a green covers. Each control forecloses one specific way this validator could
have gone green while blind:

| control | the blindness it forecloses |
|---|---|
| `multi-document-section` | The published evidence is `### name ###` sections whose bodies are JSONL — **one document per line**. A reader that takes a section as one document validates its first line and silently ignores the rest, returning a smaller, entirely plausible number. This fixture puts the only violation on the *second* line of a section, so that reader fails twice over: wrong document count and a missed finding. |
| `undescribed-false-positive` | The schema opens several containers on purpose (`extensions`, `source.tags`, cube coordinates keyed by axis name, `param_histogram.value_counts`). A walker that reports those has invented findings, and a false positive from a prescriptive instrument costs more than a miss: it sends someone to delete a field the schema does describe. This fixture exercises all of them and must report zero. |
| `closed-object-violation` | The instrument must detect the real defect shape, not a toy one — extra members inside `stats.top_k[]` and `cube.axes[]`, the same two instance paths the reference implementation trips today. |
| `declared-cap-violation` | §8 clause 4 is unreachable from the schema — `maxItems` takes a constant, the bound is the value of a sibling field — so a document can be **schema-valid and cap-violating**, which is exactly what a schema-only validator reports `CONFORMANT`. This fixture is that document, violating at two locations (`stats` and `behavior`) so a `top_k`-only checker reds, and carrying a vendor `shard_size`/`shard` pair under `extensions` that must **not** be reported. |
| `instrument-failure` | A truncated corpus, and a `--pointer` that does not resolve, must both exit 2. **There is no code path that skips a line or a file**: every non-blank line is either a section header or a document, anything else stops the run, and an unreachable pointer refuses rather than dropping the file. A parser bug cannot express itself as a smaller document count — only as a refusal to answer. |

Measured on the committed tool, 2026-08-19: **seven** independent mutations each
red the self-test — section-as-one-document · offending-member computation blinded ·
undescribed walker made root-only · open-container guard removed · unreadable line
downgraded to a skip · empty corpus accepted · unresolved pointer downgraded to a
skipped file — while the unmutated control passes 12/12. Blinding the
offending-member computation reds **four** fixtures, not one: that guard is measured
as shared, not sole. Deleting a `control` tag from the manifest exits 2, as designed.

---

## What this does **not** reach

Declared, because an instrument's silence is read as coverage.

- **§8 clauses 2 and 3 are not tested here.** Clause 2 (every required field
  populated *according to its definition*) is only covered as far as the schema can
  express it. Clause 3 (`template_id` computed exactly as §3.2 specifies) needs a
  pinned cross-implementation vector, and none exists yet — swapping the digest
  would pass every check in this directory. The tool prints this limit on every run.
- **Clause 4 is tested, but only where a cap is DECLARED.** The check compares an
  array against the cap in its own document; a producer that declares no cap for a
  block is unbounded on that block and cannot be caught here. `stats.top_k_size` is
  required, so `top_k` is always covered; `reservoir_size`, `branching_size` and
  `cell_budget` are optional, so those three blocks are covered only for producers
  that declare them. An omission is reported as a posture, never as a pass.
- **`format` is an annotation, not an assertion.** Draft 2020-12's default
  vocabulary treats `format` as annotation-only, so `date-time` and `uri` are *not*
  enforced by default — asserting them would be stricter than clause 1 says. Pass
  `--check-formats` to opt in. The flag needs the optional format validators from
  `requirements.txt` and REFUSES to run without them (exit 2): jsonschema registers
  a checker only when the matching validator is importable, so in a bare
  environment the flag would assert nothing while claiming to assert — measured
  2026-08-19, an empty-string `date-time` read CONFORMANT under the flag before
  the refusal existed. (Measured on the published determinism evidence,
  2026-08-19, with the checkers armed: enabling it adds no findings — every
  format-carrying value there is well-formed.)
- **A green on a `MetaLogDiff` corpus says nothing about §13.2.** The prose requires
  a diff to carry at least one signal field; `metalog_diff.v0.schema.json` requires
  only `diff_version`, `current` and `previous` and encodes no `anyOf`, so a diff
  carrying nothing but those three members validates cleanly. Measured 2026-08-19 on
  two published diff documents: **zero errors, and neither carries a signal field.**
  This is a limit of what the schema expresses, and the tool reports what the schema
  says — it does not invent the clause the schema is missing.
- **A bare vendor member at either document root is reported, never failed.** §7 makes
  `extensions` the only carrier of non-standard members, at any depth. The schema
  enforces that wherever the object is closed; both document roots are
  `additionalProperties: true`, so a bare vendor member there validates, appears under
  LEGAL-BUT-UNDESCRIBED, and changes no exit code. Granting the container at a root —
  as v0.9.0 does for `MetaLogDiff` — gives that data a legal home and makes the
  container's own reverse-DNS grammar enforceable; it does **not** make the placement
  rule decidable. Only closing the root would, and that is a *breaking* change under
  `GOVERNANCE.md` §2.
- **This tool does not know how large its corpus was supposed to be.** Its reader
  cannot silently skip a line — an unreadable one is fatal, an empty corpus is exit 2 —
  but a corpus that parses cleanly and simply contains *less* than the caller expected
  validates cleanly, and the verdict is then truthful about a smaller subject than the
  caller believes. Measured 2026-08-20 against the reference implementation's evidence:
  emptying one `### name ###` section, and deleting one section header outright, each
  read **CONFORMANT, exit 0**. `--expect-documents` closes only half of this — it
  catches a *reader* that miscounts what is present, never a corpus that genuinely
  holds less. The roster of what *should* be there is knowable only to the caller, so a
  caller judging a multi-section corpus has to reconcile that roster itself before
  trusting the verdict below it.
- **Cross-document properties are out of scope.** `compose()` commutativity and
  identity (§12.2) and the `MetaLogDiff` algebra (§13) are properties of *pairs and
  sets* of documents; this tool judges each document against the schema.
- **The golden-pair suite `GOVERNANCE.md` §3 anticipates (`test/golden/`) is a
  different instrument and does not exist.** Input → output pairs any
  implementation can replay would test clause 3; this directory does not.
- **`anyOf`/`oneOf` are unioned, not evaluated, by the undescribed walker.** That
  over-approximates what the schema "describes", which is the conservative
  direction: the walker may miss an undescribed member, it may never invent one.
  Schema validation itself is unaffected — that is the `jsonschema` library, at
  full strictness.

---

## Where it runs

- **`metalog-spec` CI** (`.github/workflows/conformance.yml`, every push and PR)
  runs the self-test and validates `schema/metalog.v0.example.json`. This is the
  leg that reaches an outside contributor's PR. It cannot see any implementation's
  output.
- The **reference implementation's own release gate** runs it over the document
  stream it is *about to* publish, before that artifact leaves the build. Same tool,
  same schema, earlier subject.
- The **CodeRoast superproject** runs the same tool over the reference
  implementation's *published output* — both surfaces: its determinism evidence (a
  MetaLog document stream) and its published diff documents, which are carried
  inside a larger report envelope and reached with `--pointer /raw`. That leg lives
  outside this repository because the evidence does, and a gate must live where it
  can open its subject.

The last two are not redundant. One asks whether what is about to ship still matches
the standard; the other asks what a reader is exposed to right now. Only the first can
stop a drift before it is public, and only the second can notice that something
already published stopped matching — including bytes released before a schema
tightened.

A note on the second form, because it is the reason `--pointer` exists: a document
quoted inside an envelope is still a document, and a conformance tool that can only
read bare files simply declares that surface out of scope. `--pointer` reads it
instead, and refuses (exit 2) rather than skipping a file the pointer cannot reach.

---

*Prose in this file is CC BY 4.0; `metalog_validate.py` and the fixtures are MIT.
See `LICENSE-SPEC` and `LICENSE` — the split is a rule, not a list.*
