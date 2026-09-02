# ADR 0004 — `diff_version` is the spec version, not a second axis

- **Status:** Accepted — editor (Emmanuel Prunet), 2026-09-02
- **Date:** 2026-09-02
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §13.1.1 (the rule this ADR decides), §2 (`metalog_version`),
  §2.1 (`producer.version`), §9 (versioning, and the "separate axis" §2.4 names),
  §13.2 (`comparison_outcome`, REQUIRED as of 0.10.0), GOVERNANCE §2/§3/§7

## Context

`MetaLogDiff` (§13) has carried a REQUIRED `diff_version` member since the
document type was introduced in 0.2.0. Until this decision, **the specification
never said what its value means.**

Measured over `SPEC.md` at the commit preceding this ADR, `diff_version` occurred
in exactly three places:

1. a value inside the §13.1 example document (`"0.4.0"`);
2. an entry in §13.2's list of REQUIRED members;
3. a §13.2.1 sentence excluding it from what a vacuity predicate may read.

None of the three is a definition. `schema/metalog_diff.v0.schema.json`
constrained the member to a **shape** (`^0\.[0-9]+\.[0-9]+$`) and to no value.

Two readings were therefore reachable from the published text, and they are not
compatible:

- **A.** `diff_version` is the version of *this specification* that the diff
  document conforms to — the same axis as `metalog_version`, carried by the other
  document type this specification defines.
- **B.** `diff_version` is an independent version of the `MetaLogDiff` *format*,
  moved only when the diff document's own shape changes incompatibly.

## The cost, measured

The reference implementation read it as **B**. Its source carries the literal
`diff_version{"0.6.0"}` with sibling comments recording the reasoning explicitly —
a new derived block is *"additive on the DERIVED diff → no `diff_version` bump"* —
while the same producer correctly stamps `metalog_version` at the current spec
version.

The consequence reached a **published** surface. The reference implementation's
published determinism evidence, measured 2026-09-02, carries **9 `MetaLogDiff`
documents, every one declaring `diff_version: "0.6.0"` and every one carrying
`comparison_outcome`** — a member this specification made REQUIRED at v0.10.0,
four MINOR versions later. The same file's 23 MetaLog documents declare
`metalog_version: "0.10.0"`, correctly. A consumer that honours the declaration is
being handed a document that describes itself as a version in which one of its own
required members did not exist.

That is not the implementation's defect. Reading B was available from the text,
and a version field is the one place a specification cannot leave to inference,
because it is the field a consumer branches on *before* it has read anything else.

## Decision

**Reading A. `diff_version` is the version of this specification that the document
conforms to.** §9's SemVer rules and MAJOR check reach it unchanged. A producer
MUST emit the version it implements and MUST NOT emit one older than the version
at which the newest member the document carries was minted. §13.1.1 carries the
normative text.

`canonicalization_version` and `retention_profile` (§2.4) remain the separate axis
§9 names. `diff_version` is not one of them, and a change to the producer's
processing contract does not move it.

## Why not B

B is internally coherent and it is what a careful implementer inferred, so it
deserves the argument rather than a dismissal.

- **B needs machinery that does not exist and would have to be invented.** An
  independent version axis needs its own SemVer policy, its own compatibility
  statement and its own record of what changed at each of its numbers. This
  specification has none of those for `diff_version`, and every diff member it has
  ever minted is dated in the *spec's* numbering — "new in v0.4.0" for
  `tail_delta`, "new in v0.9.0" for `reservoir_delta`, "granted in v0.9.0" for the
  diff-root `extensions`. An axis that has never been numbered separately in four
  years of changelog entries is not a second axis; it is the first one, unnamed.
- **B makes the schema unable to describe its own subject.** There is one
  `metalog_diff.v0.schema.json` for the whole 0.x line, and it now REQUIRES
  `comparison_outcome`. Under B a genuine 0.6.0 diff is a document the shipped
  schema rejects, and the number therefore selects a schema that does not exist.
- **B costs a consumer a second compatibility model** for no gain: it would have
  to know both which spec version minted a member and which diff version admits
  it.
- **The one thing B buys — a diff document that need not move when unrelated parts
  of the spec do — is worth less than it looks.** A consumer's only mechanical
  check is §9's MAJOR comparison, and both axes have the same MAJOR.

## Consequences

- **Breaking for a producer that stamped an older value**, which is the intended
  direction: such a producer was already emitting a self-contradictory document.
  Landed in 0.10.0 because 0.10.0 is unreleased under GOVERNANCE §7 — no tag, no
  Release, therefore no implementer holding the old reading.
- **Nothing enforces it, and §13.1.1 says so in the same breath as the rule.**
  `pattern` fixes the shape; JSON Schema cannot require that a member's value be
  at least the version at which a sibling member was minted. §8 clause 1 passes a
  document that lies here. This is a producer obligation, decidable by an
  implementer over its own output.
- Every `diff_version` in this repository was repointed to `0.10.0` in the same
  pass: 15 `MetaLogDiff` documents across 8 conformance fixture files, plus the
  §13.1 example.
- §2.1's `producer.version` example was changed from `"0.6.0"` to `"2.1.0"`. It
  had been spelled with the same number as `metalog_version`, which invites
  exactly the coupling this ADR denies; §2.1 now states that a producer version
  moves on the implementation's own schedule.
- **The reference implementation is now measurably non-conformant on this member**
  until it repoints its literal, and GOVERNANCE §3 resolves that in the
  specification's favour. Its published evidence must be regenerated; the fix is
  one literal, and the correct form binds it to the constant the producer already
  keeps for `metalog_version` rather than restating the number a third time.
