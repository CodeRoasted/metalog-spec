# ADR 0005 — The outcome a withholding producer did not have

- **Status:** Accepted — editor (Emmanuel Prunet), 2026-09-02
- **Date:** 2026-09-02
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §13.2 (the witness rule), §13.2.1 (`x-metalog-vacuous`),
  §13.2.2 (the member this ADR decides), §3.5.2 (`field_histogram_deltas` and the
  wire-emission note that creates the gap), §11 (the size budget that justifies
  withholding), §8 clause 6, GOVERNANCE §2

## Context

0.10.0 replaced §13.2's presence-quantified clause with a **witness rule**: a
`MetaLogDiff` asserting `comparison_outcome: "changed"` MUST carry at least one
signal property that is non-vacuous by its own `x-metalog-vacuous` declaration,
and one asserting `"unchanged"` MUST carry none.

The rule assumes that what a producer **found** and what its document can **show**
are the same set. They are not, and this specification says so itself. §3.5.2's
wire-emission note blesses a producer that computes `field_histogram_deltas` and
does not serialise it, for a stated reason: a streaming producer's §11 envelope
cannot always afford a per-slot value block.

Compose the two and a state appears with **no conformant document**:

> The comparison ran. Its only finding lies in a signal property this producer
> does not serialise.

- `"changed"` fails §13.2.1 clause 4 — the withheld property is absent from the
  document, step 3 makes an absent property not a witness, and no other property
  carries a finding.
- `"unchanged"` is false. §13.2 defines it as *"the comparison ran and found no
  change"* and says in terms that a producer which found a change and reported
  `"unchanged"` "has emitted a document at war with itself".

The reference implementation already sits on this edge and documents it: its
outcome function deliberately excludes `field_histogram_deltas` from the verdict
because counting it *"would assert changed on a document carrying no witness"*.
Its resolution is to report `"unchanged"` — the false horn — and nothing in the
specification told it otherwise.

**Zero documents in the committed reference corpus exercise the state**, because
the producer's per-template slot-tracking cap is off by default and no rows are
computed. The hole is real and currently unreached, which is the cheapest moment
to close it.

## Decision

Add **`withheld_signals`** (array of strings, optional) at the `MetaLogDiff` root,
naming the signal properties in which this comparison found a change that this
document does not carry. It is an ordinary member of the witness set with an
`x-metalog-vacuous` of `maxItems: 0`: a non-empty array is a **witness**, so
`"changed"` becomes legal on its strength alone; an empty one is vacuous and
changes nothing.

Normative constraints (§13.2.2): every member names a witness-set property other
than `withheld_signals` itself, and one that is **not a witness in this document**;
the array is sorted and duplicate-free; a producer does not list a property merely
because it does not implement one — the member reports a finding, not an inventory
of omissions.

## Alternatives, and why each is worse

- **Oblige serialisation of the withheld property when it carries the only
  finding.** Strictly more information for the consumer, and rejected on the
  contract it implies: whether a block appears on the wire would depend on what
  *other, unrelated* signals did in that window. No implementer can hold that, no
  consumer can predict the shape, and it deletes §3.5.2's affordance and with it
  the §11 rationale that produced the affordance.
- **Oblige silence — emit no `MetaLogDiff` for that pair.** Makes the finding
  vanish, and makes the *existence* of a diff document depend on a producer
  configuration. A consumer cannot distinguish a withheld change from a comparison
  nobody ran. That is the unreadable silence §13.2 exists to forbid, arriving
  through the other door.
- **Scope `"unchanged"` to the properties the document serialises.** One sentence,
  no new member — and it re-mints the exact defect 0.10.0 was cut to remove.
  §13.2 says in terms that the outcome is *"the producer's assertion about the
  comparison it performed, not a summary of which fields it chose to serialise"*.
- **A third `comparison_outcome` token.** Forces every consumer to grow a branch
  for a state most producers never enter, and still says nothing about *where* the
  finding is.
- **Carry it in `extensions`.** §13.2.1 step 2 excludes the `extensions` container
  from the witness set by name, so the document would still carry no witness. The
  exclusion is deliberate and is not being reopened for this.

## Consequences

- **Additive.** No field is removed, no type changes, no conformant document
  becomes invalid, and a producer that serialises every finding it makes never
  emits the member.
- **It weakens the witness rule, in a bounded and visible way, and §13.2.2 says
  so rather than leaving a reader to find it.** A consumer reading `"changed"` is
  no longer guaranteed a finding it can point at; it may be handed only the name
  of a place where one exists. The degenerate case is legible as exactly one
  member, so a consumer that requires a pointable finding tests for it in one
  place. The three alternatives above each cost more.
- **The membership and ordering MUSTs are not mechanically enforced, and that is
  a choice.** An `enum` of the permitted names would be the hand-kept list of
  signal properties §13.2 deleted for having drifted from the schema by three
  members; re-minting it here to police a corner case would trade a live defect
  class for a dead one. Sortedness is not a JSON Schema assertion. The schema
  carries `uniqueItems` and nothing more.
- **The clause ships with teeth.** `conformance/fixtures/valid/changed_witness_withheld.diff.json`
  is the same bytes as `invalid/changed_without_witness.diff.json` with one array's
  content changed, `[]` → `["field_histogram_deltas"]`, so the exit-code difference
  between the two is attributable to that array alone. Verified 2026-09-02 by
  mutation: reverting that one array reds the self-test at 1/27 and naming the
  fixture, and restoring it returns 27/27. The witness-set machinery in
  `conformance/metalog_validate.py` needed no change — it is derived from the
  schema, so the member joined the set on arrival.
