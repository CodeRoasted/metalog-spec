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

# Judge documents carried inside an envelope — one, or every element of an array.
python3 conformance/metalog_validate.py --kind diff --pointer /raw my_report.json
python3 conformance/metalog_validate.py --kind diff --pointer /raw/-/diff \
        --expect-documents 40 report_a.json report_b.json
```

---

## What it reports, and why it never reports one number

A single "N errors" number hides four findings with different owners — and one of
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
standard may adjudicate. **This standard's own `x-metalog-*` schema keywords are
skipped too**, and for the mirror-image reason: an annotation is a *predicate*, not
a description of a document location, so an `<x>_size`/`<x>` pair appearing inside
one would mint a cap **no schema declares** and then enforce it against every
document. Measured 2026-09-01: the derived pair set is byte-identical with and
without the skip on the shipped v0.10.0 pair, and on a copy whose annotation was
given such a pair the unskipped walk mints `('shard_size', 'shard')` while this one
mints nothing. The rule is stated over the **prefix** rather than over one keyword,
so `x-metalog-reserved` (SPEC §2's RESERVED level) needed no second pass.

**An undeclared cap is not a violation.** A producer that omits
`behavior.branching_size` declares no cap (§4.2); the tool reads that as a
posture and says so, rather than assuming a default and going green.

**WITNESS** — a `MetaLogDiff` whose `comparison_outcome` disagrees with the
document's own signal properties: `"changed"` with no non-vacuous signal property,
or `"unchanged"` carrying one. This is §8 clause 6 failing. **Exit 1.**

The schema cannot reach this either, and for two independent reasons — the second
is the one a reader misses. The predicate is `x-metalog-vacuous`, an *annotation* a
generic validator ignores by design (SPEC §13.2.1); **and** the rule quantifies over
the *schema's* property set rather than over the instance, so even a validator
taught the keyword could not express "at least one of the properties I declare".

Three things about the rule are load-bearing, and each has its own fixture:

- **Vacuity is DECLARED, never inferred from shape.** Each optional signal property
  of `metalog_diff.v0.schema.json` carries an `x-metalog-vacuous` keyword whose
  value is a Draft 2020-12 assertion subschema; the property is vacuous exactly when
  its value validates against it. Shape does not answer the question: `cube_diff.axes`
  is a required, non-empty **descriptor** and never a finding, `tail_delta` carries
  findings with no array at all, and `stability_score`'s no-change value is **`1`**,
  not `0`.
- **The witness set is read from the SCHEMA, never from the document.** A member a
  document carries that the schema does not declare is not in the set — otherwise a
  producer could manufacture a witness by inventing a member at the open root.
- **Schema-validity comes first (§13.2.1 step 1).** `{"maxItems": 0}` is *inert* on
  a non-array, so judging an unvalidated document would call a mistyped property
  vacuous and make a real witness disappear. Documents the step withholds are
  **counted and printed**, never absorbed: a withheld verdict is not a pass.

**The instrument REFUSES rather than judges when the declarations are themselves
defective.** SPEC §8's closing paragraph makes this a MUST, and it is exit 2, not a
verdict: a missing declaration, a boolean one, a `$`-keyword at any depth inside
one, one with no `description`, one that is not a valid Draft 2020-12 schema. An
absent declaration is the load-bearing case, because absence is the one defect that
reads as *permission* — skipping an undeclared property would silently shrink the
witness set. The self-test prints the denominator every run (`12 of 12 optional
signal properties declared`), because an arm armed at zero is unobservable.

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
object is never also counted as undescribed. WITNESS is disjoint from both for a
different reason — it is decided only on a document that already passed SCHEMA-INVALID.

---

## Exit codes are a contract

| code | meaning |
|---|---|
| **0** | conformant against the schema |
| **1** | findings — at least one document is schema-invalid |
| **2** | **the instrument could not run honestly** and has no verdict |

Exit 2 is not a softer failure, it is a *different* one: an unreadable line, an
empty corpus, a document count that did not match `--expect-documents`, a missing
schema, an unresolvable `$ref`, a missing or defective `x-metalog-vacuous`
declaration in the shipped schema, a failed self-test. A caller that treats 2 as 1
loses the distinction between "your documents are wrong" and "repair the
instrument"; a caller that treats 2 as 0 has a gate that goes green because it
never looked.

---

## Why the self-test exists

A validator that cannot fail is decoration. `--selftest` runs twenty-six fixtures whose
expected results are **hand-authored in `fixtures/manifest.json` from the spec and
the schemas** — never captured from a run, because an expectation copied out of the
tool under test makes the tool its own oracle, and the pair then agree forever
while both are wrong.

Fourteen of those fixtures carry a `control` tag, naming **twelve** distinct blindnesses
(`instrument-failure` is carried by three), and the self-test **refuses to run**
if any tag is missing from the manifest — deleting a fixture cannot quietly widen
what a green covers. Each control forecloses one specific way this validator could
have gone green while blind:

| control | the blindness it forecloses |
|---|---|
| `multi-document-section` | The published evidence is `### name ###` sections whose bodies are JSONL — **one document per line**. A reader that takes a section as one document validates its first line and silently ignores the rest, returning a smaller, entirely plausible number. This fixture puts the only violation on the *second* line of a section, so that reader fails twice over: wrong document count and a missed finding. |
| `undescribed-false-positive` | The schema opens several containers on purpose (`extensions`, `source.tags`, cube coordinates keyed by axis name, `param_histogram.value_counts`, `attribution.sketch_params`, `provenance[].source`). A walker that reports those has invented findings, and a false positive from a prescriptive instrument costs more than a miss: it sends someone to delete a field the schema does describe. This fixture exercises all of them and must report zero. The last two were added on 2026-08-24, and their absence was not cosmetic: the fixture carried no `attribution` block at all while its own entry claimed "sketch-shaped free objects", so the two positions whose disposition the closure walk had to rule on were the two this control could not see. |
| `closed-object-violation` | The instrument must detect the real defect shape, not a toy one — extra members inside `stats.top_k[]` and `cube.axes[]`, the same two instance paths the reference implementation trips today. |
| `declared-cap-violation` | §8 clause 4 is unreachable from the schema — `maxItems` takes a constant, the bound is the value of a sibling field — so a document can be **schema-valid and cap-violating**, which is exactly what a schema-only validator reports `CONFORMANT`. This fixture is that document, violating at two locations (`stats` and `behavior`) so a `top_k`-only checker reds, and carrying a vendor `shard_size`/`shard` pair under `extensions` that must **not** be reported. |
| `instrument-failure` | A truncated corpus, a `--pointer` that does not resolve, and a pointer whose envelope changed shape underneath it must all exit 2. **There is no code path that skips a line or a file**: every non-blank line is either a section header or a document, anything else stops the run, and an unreachable pointer refuses rather than dropping the file. A parser bug cannot express itself as a smaller document count — only as a refusal to answer. Each of these fixtures also pins the *reason*, not only the number: exit 2 is a class, and an instrument refusing for a reason nobody intended would otherwise satisfy a fixture that reads the code alone. |
| `pointer-array-every-element` | An envelope carries as many documents as its producer performed comparisons, and the shape it takes is a **list**. A pointer that resolves to one document judges the first and prints the same confident verdict over the rest — not a smaller check, a green covering a subject nobody chose. This fixture is a four-entry envelope whose violation sits at entry **2**, and its `/raw/0/diff` twin in the same manifest pins what the single-document reading does with those exact bytes: **exit 0, CONFORMANT**. The contrast is executable rather than remembered. |
| `pointer-empty-selection` | The other way a corpus reaches zero, and the only one no exception-shaped guard can see: the pointer resolves perfectly onto an array that is **empty**. Every path taken is correct and the subject is nothing. Exit 2 — a verdict over zero documents is green for the one reason that matters, that it never looked. |
| `vacuity-is-declared-not-shaped` | §8 clause 6 asks whether a signal property carries a **finding**, and its JSON *shape* does not answer that. The fixture is a conformant `"unchanged"` diff carrying **eleven of the twelve** optional signal properties, every one present and vacuous by its own `x-metalog-vacuous` declaration. A **presence** reader finds eleven witnesses on a document that carries none — the exact clause 0.10.0 deleted. An **emptiness** reader finds three (`template_deltas` holds a row whose `delta` is `0`; `tail_delta` holds nine members and no array; `cube_diff.axes` is a required non-empty **descriptor**). A reader that assumed `const: 0` for every scalar finds a fourth, `stability_score: 1`. The twelfth property, `reservoir_delta`, is absent on purpose: §13.7 forbids emitting an all-empty block, so its declared vacuous state is unreachable by construction and writing it here would have made a "valid" fixture violate §13.7. |
| `witness-rule-changed-arm` | `"changed"` obliges a witness. The fixture is the control above with **one token** changed, so the exit-code difference between the two is attributable to that token and nothing else. The finding names no member, because on this arm the defect *is* an absence. |
| `witness-rule-unchanged-arm` | `"unchanged"` forbids one, and a rule that binds only the other arm is satisfied forever by a producer that always writes `"unchanged"`. The fixture is the same control with **one row** changed — `template_deltas[0]` from `delta: 0` to `delta: 3`, with `current_count` moved to match (§13.3) — so the witness sits inside an array that is non-empty and the same length in both documents, where a presence reader and an emptiness reader are blind to the mutation. |
| `witness-set-from-schema` | §13.2.1 step 2 reads the witness set from the **schema**, never from the document. The fixture carries a bare `vendor_private_counter` at the diff root, which is open: legal-but-undescribed, exit 0, and **not** a witness. Read the set from the document instead and it becomes one — a producer could then manufacture a witness by inventing a member at an open root. Measured 2026-09-01: that mutation passed the other twenty-five fixtures **25/25**, so until this entry existed the sentence had no arm at all. |
| `pointer-token-literal-in-object` | The extension must not swallow the standard it extends. `-` means *every element* where an **array** sits, because RFC 6901 gives that token no resolvable meaning there; where an **object** sits it is a literal member name and stays one. This fixture is an envelope carrying a member spelled `-` beside a second member, so a reading that wildcards the token everywhere judges two documents where one was addressed. |

Measured on the committed tool, 2026-08-19: **seven** independent mutations each
red the self-test — section-as-one-document · offending-member computation blinded ·
undescribed walker made root-only · open-container guard removed · unreadable line
downgraded to a skip · empty corpus accepted · unresolved pointer downgraded to a
skipped file — while the unmutated control passes 12/12. Blinding the
offending-member computation reds **four** fixtures, not one: that guard is measured
as shared, not sole. Deleting a `control` tag from the manifest exits 2, as designed.

Measured again on the every-element pointer, 2026-08-25, **ten** further mutations
each red it — the wildcard judging only the first element · only the last · every
element but counting one · every element without naming which · an empty selection
accepted · the token wildcarded against objects too · a numeric index expanding as
if it were the token · a deleted `control` tag · a fixture omitting which element
its finding came from · a refusal fixture omitting the reason — while the unmutated
control passes 22/22. Two of those ten are the manifest's own demands, and each was
verified by **bypassing its partner**: remove the demand *and* the key it asks for,
and the suite goes green on a strictly weaker oracle. That is what the demand costs
and why it is derived from the fixture's own pointer rather than kept in a list
beside it.

Measured a third time on the witness rule, 2026-09-01: **six** mutations of the
clause-6 evaluator each red it, and the shape of what they red is the evidence —
dropping §13.2.1 step 1 (schema-validity first) reds **7**, reading the witness set
from the document reds **1**, dropping the `"changed"` arm reds **1**, dropping the
`"unchanged"` arm reds **1**, reading vacuity from shape reds **4**, reading it as
presence reds **4** — while the unmutated control passes 26/26. The three that red
exactly **one** fixture are what proves those three arms non-redundant: deleting a
check that reds four says little about which of the four was load-bearing. Six
further mutations of the schema's own declarations — one deleted, one `true`, one
`false`, one carrying `$ref`, one with no `description`, one that is not a valid
Draft 2020-12 schema — each exit **2** naming the clause they broke, on a plain run
and on `--selftest` alike, which is what proves the refusal is reachable without a
corpus at all.

**Before any fixture runs, the self-test compares the two schemas' shared `$defs`.**
Each schema file is independently consumable — `SPEC.md` §8 invites downloading one
alone — and this tool resolves only in-document pointers, so a grammar both files
need is *duplicated* rather than cross-referenced. A duplicate that can drift is
worse than no duplicate: it publishes one name with two meanings, and whoever
downloaded a single file has no way to notice. So every `$defs` name present in both
files must agree in **every keyword but `description`**, which is excluded so that a
copy can name its source. The set is derived from the artifacts, never enumerated —
a mirror added tomorrow is checked on arrival.

This is not a hypothetical guard. Run it against the shipped v0.8.0 pair and it reds:
`band_floor` joined `$defs/cube_axis` in `metalog.v0.schema.json` and not in
`metalog_diff.v0.schema.json`, so a diff of two collapsed cubes was **rejected by the
diff schema while both of its inputs validated** (§13.6 requires `cube_diff.axes` to
equal both inputs' `cube.axes`; §16.10 stamps a collapsed axis with `band_floor`).
A drift is **exit 2**, not exit 1: the standard's own artifacts disagree, and no
verdict about anyone's documents is honest until they don't.

**Then it walks every object position in both schemas and requires each one to
declare its own closure.** Three dispositions are legal and there is no fourth:
`additionalProperties: false` (closed — the members are named), a **constraining**
value schema (a map: closed over its VALUES, never over its key set), or
`{"description": "<why it is open>"}` (open, with its reason attached). An
**absent** `additionalProperties` is a defect, because absence is not a disposition
— it is the lack of one, and two positions can share a byte-identical
`{"type": "object"}` while meaning opposite things: `provenance[].source` is a
standard object whose members §12.4 names, and `attribution.sketch_params` is a map
whose keys are data. Nothing in the schema text separates them; only the prose
does. A census of what is open therefore cannot be maintained by reading
`additionalProperties`, and a hand-kept list of exemptions beside the schemas would
rot on the next release — so the rule is enforced instead, and the position set is
derived from the artifacts. A position added tomorrow is checked on arrival.

A bare `true` is refused, and the reason is measured rather than stylistic: it is
the one spelling with nowhere to put the *why*. Accepting it against a
**node-level** `description` would pass both document roots vacuously, on sentences
that describe the document type ("Pair-wise difference between two MetaLog
documents") and say nothing about why the root admits unknown members — a check
that goes green on the two positions it exists to interrogate.
`{"description": ...}` is the same schema as `true` in Draft 2020-12, so this costs
no document its validity; it costs an author one sentence, at the only place a
reader will look for it.

Run against the shipped v0.9.0 pair before this control landed, it reds at **7 of
49** positions: both document roots, `provenance[].window`, the diff's
`current.window` and `previous.window` (all five open with no reason attached), and
`attribution.sketch_params` and `provenance[].source` (both absent). Exit 2, for the
same reason a `$defs` drift is.

**In-place applicators are not positions, and the exclusion is load-bearing.** An
`if`, `then`, `else`, `not`, or a branch of `allOf`/`anyOf`/`oneOf` constrains the
position it sits in rather than being one: `additionalProperties: false` inside an
`if` changes the *condition*, and inside a `then` it closes the object. Demanding a
declaration there would order an author to break his own schema. Nine such fragments
carry `required` or `properties` and no `type` in the shipped pair; a walk blind to
the distinction censuses 58 positions instead of 49 and reds on all nine.

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
- **§13.2 is now reached, and this bullet records what that cost and what it did not
  buy.** Until v0.10.0 it said the opposite: *"a green on a `MetaLogDiff` corpus says
  nothing about §13.2"*, because the clause quantified over field **presence**,
  presence is satisfied by every producer regardless of what it found, and the schema
  required only `diff_version`, `current` and `previous`. §13.2 now quantifies over an
  asserted **verdict** (`comparison_outcome`) and SPEC §8 gained clause 6, so the tool
  decides it. Three limits survive, and none of them is the old one:
  - **Only on a schema-valid document.** §13.2.1 step 1, and it is not ceremony —
    `{"maxItems": 0}` is *inert* on a non-array, so a document that skipped validation
    could have a mistyped array property called vacuous and its real witness would
    disappear. Withheld documents are counted and printed on every run.
  - **Only as far as the declarations are correct.** The tool reads
    `x-metalog-vacuous` and checks its **grammar**; it cannot check whether a
    declaration says the *right* thing about the property. A declaration that named
    the wrong vacuous value would be enforced faithfully and wrongly. What it does
    guarantee is that a **missing or malformed** one stops the run (exit 2) rather
    than shrinking the witness set in silence.
  - **`reservoir_delta`'s declaration is unreachable by construction**, and this is a
    property of the standard rather than of the tool: §13.7 requires an emitted block
    to carry at least one non-empty list, and its declared vacuous state is *all three
    lists empty*. In a conformant document the property is therefore a witness
    whenever it is present, and its declaration can never decide anything. It is still
    the right predicate to write — the grammar has no conformant way to spell "never
    vacuous", the two boolean schemas being exactly what §13.2.1 clause 1 refuses.
- **A bare vendor member at either document root is reported, never failed.** §7 makes
  `extensions` the only carrier of non-standard members, at any depth. The schema
  enforces that wherever the object is closed; both document roots are **open**, so a
  bare vendor member there validates, appears under
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
  trusting the verdict below it. One shrink IS caught without a roster, and only one:
  an envelope whose array the pointer selects every element of, and which now holds
  **zero**, is exit 2 — because there the tool can tell that it judged nothing.
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

### `--pointer`, and the one token it adds to RFC 6901

An envelope carries as many documents as its producer performed comparisons, so the
shape a CI report actually takes is a **list** of them — `raw[0].diff`,
`raw[1].diff`, … A pointer that can only name one of those judges the first and
prints its verdict over all of them, which is not a smaller check: it is a green
covering a subject nobody chose.

So `-` in an **array** position selects **every** element, and each selected element
is judged and counted as its own document:

```
--pointer /raw/-/diff        every comparison in one report
--pointer /runs/-/raw/-/diff every comparison in every run of an aggregate report
```

The token is safe to give this meaning because RFC 6901 §4 already gives it exactly
one meaning in an array — *the element after the last* — and that element never
exists, so no pointer that used to resolve can start resolving differently. In an
**object** position `-` stays a literal member name, exactly as RFC 6901 says: this
tool does not overrule the standard it cites in order to be helpful.

Two consequences a caller should plan for, both of them refusals rather than
verdicts:

- A pointer written for a wire shape the envelope no longer has **stops the run**
  (exit 2) instead of judging what it happens to reach. `-` against an object that
  has no member spelled `-` is that case, and the message says so.
- A pointer that resolves onto an **empty** array selects nothing, and zero
  documents is exit 2. Every path taken was correct and the subject was nothing;
  that is the failure this instrument exists to refuse.

The document count is in the output — per file and in total — so a subject that
shrank is visible rather than silent, and `--expect-documents` turns the total into
a tripwire. Each finding names the **concrete pointer** of the element it came from
(`report.json/raw/2/diff`), because `1 of 40` with no element named is a number
nobody can act on.

---

*Prose in this file is CC BY 4.0; `metalog_validate.py` and the fixtures are MIT.
See `LICENSE-SPEC` and `LICENSE` — the split is a rule, not a list.*
