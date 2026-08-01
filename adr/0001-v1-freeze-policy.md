# ADR 0001: MetaLog v1 Freeze Policy

## Status

Accepted. **Revised** — the freeze conditions below replace an earlier set that
gated the format's 1.0 on one implementer's internal delivery milestones. Those
conditions are **withdrawn**; see *Alternatives considered*.

## Context

MetaLog is still in the v0 draft line. v0.2.0 added template deduplication, formal
behaviour fields, composition, sessions, and `MetaLogDiff`. Consumers need a clear,
checkable rule for when the format stops breaking.

"Checkable" is the whole difficulty, and it is what this ADR exists to get right.
A freeze condition is a **promise to implementers**, so an implementer must be able
to evaluate it. A condition that only the editor can evaluate is not a policy — it is
an announcement, and it asks the ecosystem to take the freeze on trust.

That constrains the conditions more than it first appears. §8 already states the
conformance model — *"there is no central conformance authority; the schema is the
test"* — so the freeze bar has to be expressible in those same terms: artifacts
anyone can fetch and run, not judgements anyone has to accept.

## Decision

**The 0.x line stays explicitly unstable.** During 0.x a MINOR bump **MAY** break
compatibility (SPEC §9). This does not change.

**v1.0 is frozen only when all five conditions below hold, and each is verifiable by
a third party with nothing but this repository:**

1. **Two independent implementations interoperate on the v0 envelope.** Each emits
   documents the other consumes, both preserving the semantics of §3.4 template
   resolution. At most one of them may be the reference implementation. This is the
   condition that actually retires the risk a freeze exists to retire: a format with
   a single implementation has not been shown to be implementable, only to be
   implemented once.

2. **Language-agnostic conformance vectors are published in this repository** as
   input → output pairs, covering `diff()` and `compose()` in addition to document
   shape. GOVERNANCE §3 already promises this suite; the freeze makes it a
   precondition rather than future work. It is separately load-bearing because §8's
   schema check tests a document's **shape**, never the **operations** — a document
   produced by a wrong `diff()` still validates, so schema conformance alone cannot
   distinguish a correct implementation from a confidently broken one.

3. **Every normative **MUST** in `SPEC.md` is exercised by at least one vector.**
   Without this, "the schema is the test" is an unmeasured claim: the schema
   constrains structure, and a MUST about *behaviour* can be universally violated
   with every document still valid.

4. **`schema/` and the worked example agree under an off-the-shelf JSON Schema
   validator** at the candidate version, checked mechanically rather than by review.

5. **No `rfc:` issue proposing a breaking change is open.** Freezing while a known
   breaking change is in flight would freeze a version already believed wrong, and
   would spend the MAJOR bump the freeze is meant to make rare.

**After 1.0**, change types and their process are governed by **GOVERNANCE §2**,
which is the single owner of that table. This ADR deliberately does not restate it:
two copies of one versioning rule are free to diverge, and the copy a reader finds
first would win by accident rather than by authority.

## Alternatives considered

**The withdrawn conditions — gating 1.0 on the reference implementation's delivery.**
The previous revision required integration tests in one named implementation, a
`MetaLogDiff` implementation, validated composition, two named private components
publishing field-exposure documents, and a compatibility matrix naming that
implementation's package version.

Three defects, and the third is disqualifying on its own:

* **Not third-party evaluable.** No external implementer can determine whether
  another organisation's integration tests pass, so the freeze was decidable by
  exactly one party.
* **Category error.** It gated a vendor-neutral format's own version on one vendor's
  internal schedule. A format's stability is a property of the format.
* **It published the names of components that exist nowhere else in this public
  surface**, disclosing internal structure to no specification purpose.

The delivery sequencing of any particular implementation is tracked by that
implementation's maintainers and is out of scope here.

**Freeze on adoption count instead** — rejected: adoption measures market timing,
not whether the format is finished, and it would let a widely-copied mistake freeze
precisely because it spread.

**Freeze on a fixed date** — rejected: a date is trivially checkable, which is its
only virtue. It carries no evidence that the format is ready.

## Consequences

* v0.x schemas may still change incompatibly; consumers pin `metalog_version` and
  tolerate unknown fields.
* Release notes call out draft-breaking changes clearly until v1.0.
* **The freeze is now blocked on artifacts, not on assertions.** Conditions 2 and 3
  are real work — the vector suite does not exist yet — and that cost is deliberate:
  it is the same work an implementer would otherwise have to do privately, with no
  way to compare results.
* **A second implementation is now on the critical path to 1.0.** If none appears,
  the honest outcome is that the format stays 0.x, which is a truer signal than a
  1.0 backed by one implementation.
