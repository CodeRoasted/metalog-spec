# ADR 0011 — The schema is closed; a map is closed over its values

- **Status:** Proposed — accepted when the editor merges its pull request
- **Date:** 2026-11-15
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §2 (document structure), §7 (`extensions`, placement), §8 clause 1, §9 (the
  MAJOR check), §12.4 (`provenance`), ADR 0003 (the four undescribed wire members),
  GOVERNANCE §2, RFC issue #8 (P1)

## Context

§7 has made `extensions` the only carrier of non-standard members since v0.8.0: a producer
**MUST NOT** write vendor data as a bare member of a standard object, at any depth. The schema
enforced that inside every closed object and nowhere else. Six object positions were open: both
document roots, the `window` object of a `provenance` entry, the `current.window` and
`previous.window` objects of a `MetaLogDiff`, and `provenance[].source`. A bare vendor member at
any of them validated, and the conformance tool could only report it as *legal-but-undescribed*,
a report that changes no exit code.

The cost is measured. The reference implementation wrote three vendor blocks bare at the document
root of all 17 of its published determinism-evidence documents, each of which validated with zero
errors, while the `$defs/extensions` key pattern already accepted the namespaced spelling and
rejected the bare one. The defect was found by a human audit and repaired by a producer pass; the
schema's verdict was "conformant" before and after.

The root was open because §2 says *"Consumers MUST ignore unknown top-level fields"*, and that
obligation had been encoded as `additionalProperties` at the root. The two are different
propositions about different subjects. The sentence is a runtime obligation on a consumer; the
keyword is a property of a document. Encoding the first as the second granted **producers** the
un-namespaced extension point §7 denies them.

Two of the six positions show that the openness was not designed: `provenance[].window` was open
while the document-level `window`, the same concept with the same members, was closed; and
`provenance[].source` declared no members at all while §12.4's own example carries `service` and
`host` there.

## Decision

1. **Every object position states its admission rule in `additionalProperties`**, and there are
   three: closed (`false`); a map closed over its values by a value schema (`source.tags`, a cube
   coordinate, a `value_counts` map); a map whose values are not yet constrained, written as a
   subschema that asserts nothing and carries a `description` saying why
   (`attribution.sketch_params`). An absent `additionalProperties` is a schema defect, and the
   conformance tool's self-test refuses to run on one. The rule is checked by walking the schema;
   no list of exempt positions is kept.
2. **The six open positions close.** `provenance[].source` closes over the members of the
   document-level `source` block: both reference one `$defs/source`, so the two cannot drift.
3. **Validation and acceptance are separated in §2.** A consumer still ignores unknown top-level
   members of a document it can otherwise process. A validator holding an older schema that
   rejects a newer document's member is reporting that it does not know the member, which is
   true, and the rejection is not a reason to refuse the document.
4. **The *legal-but-undescribed* species leaves the conformance tool.** After closure the only
   positions that admit an unnamed key are maps, whose keys are data, and `extensions`, whose keys
   a consumer ignores by design. The walker could report nothing, so it is removed rather than kept
   to print an empty section.

## Alternatives considered

### A. Leave the roots open and rely on §7's prose

Rejected on the measurement above: the rule was published, restated in the schema's own key
pattern, and violated in every published document by the implementation that wrote it. A rule
with no gate holds as long as everyone's attention does.

### B. A conformance ladder (Core / Extended) instead of closure

Rejected. It adds a second axis to reason about. After closure, *valid* means *everything
non-standard is namespaced*, which is the property a ladder would be built to approximate.

### C. Close by listing the exempt map positions

Rejected. A list rots on the next map the specification adds, and a hand-kept census of these
positions has already misfiled one: `attribution.sketch_params` and `provenance[].source` were
byte-identical in the schema text and meant opposite things. `false` on the first admits only the
empty object, and §6 makes it required, so every document carrying `attribution` would have failed.

### D. Freeze `attribution.sketch_params`'s value grammar in the same change

Rejected as premature. `sketch_type` names three families and no parameter set is frozen for any
of them; `attribution` is RESERVED (§2). Constraining the values would restrict producers this
specification cannot see.

## Consequences

- A producer writing vendor data bare at either root, inside a `provenance` or diff `window`, or
  inside `provenance[].source` becomes non-conformant, and moves the data under a reverse-DNS key
  in `extensions`. A member this specification describes is not vendor data: `run_outcome` and
  `reservoir_delta` (adopted in 0.9.0 under ADR 0003) stay at their roots.
- The reference implementation's published evidence carries no member the closed schemas reject
  (measured over the 35 documents and 10 diffs of its latest published digest).
- ADR 0003's alternative C named the open roots as the reason §8 clause 1 could not see a bare
  member. That reason no longer holds; ADR 0003's decisions are unchanged.
- Schema file names and the MAJOR of `metalog_version` are unchanged.
