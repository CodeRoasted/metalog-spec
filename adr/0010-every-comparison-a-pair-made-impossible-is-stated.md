# ADR 0010 — Every comparison a pair made impossible is stated, and the both-absent line

- **Status:** Proposed — accepted when the editor merges the pull request that carries it
- **Date:** 2026-11-14
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** [ADR 0007](0007-a-comparison-not-performed-is-stated.md) (the member this
  ADR extends), SPEC §3.5 and §3.5.2 (histogram caps, `field_histogram_deltas`), §3.7.2
  (`stats.reservoir_size`), §4.2 (the transition graph), §13.1, §13.2.3, §13.6, §13.7,
  §16.2, §16.10, GOVERNANCE §2

## Context

ADR 0007 gave a `MetaLogDiff` a way to say "this comparison was not performed",
`incomparable_signals`, and used it for one case: `ngram_delta` across two n-gram orders.
It named two more cases with the same shape and left them out. A census of every optional
signal property of the diff schema against one-sided input finds six:

1. Only one input carries `behavior`: `ngram_delta` and `branching_delta` are absent with
   no statement, so the diff reads like a comparison that found the sequence structure
   unmoved.
2. Only one input carries `cube`: `cube_diff` is absent the same way.
3. Both carry a `cube` whose axis schemas differ (an axis name, a kind, a chain's levels):
   §13.6 said the diff is emitted only when `axes` are equal, but §16.2 puts the collapse
   stamps on the axes and §16.10 diffs two cubes at their minimal common collapse, so the
   text contradicted itself and did not separate a schema difference from a stamp
   difference.
4. Across two orders `branching_delta` rows were emitted. §4.2 never said what the
   transition graph is; a producer reading it off its order-n sequence table gets a graph
   that depends on the order, so the rows compare two different quantities and can report
   a change on an unchanged workload.
5. Only one input keeps a reservoir: `reservoir_delta` reports every salient entry of the
   other side outside its `top_k` as born or dead. This is a false witness, not a silence.
6. Only one input tracks field histograms, or both track at different caps:
   `field_histogram_deltas` compares nothing, or compares two truncations.

Cases 5 and 6 share a second defect. The wire could not say whether an absent
`stats.reservoir` was empty or never kept, nor whether a document without
`param_histograms` tracked none or had none to track: both caps were SHOULD, and only
beside an emitted block.

## Decision

**A comparison the PAIR made impossible is stated in `incomparable_signals`, under one of
four closed reasons, and the property is omitted.**

- `absent_in_one_input`, with `absent_in` (the input lacking the block) and `block`:
  exactly one input carries `behavior` (keys `ngram_delta`, `branching_delta`),
  `behavior.branching` when both carry `behavior` (key `branching_delta`), `cube` (key
  `cube_diff`), a kept reservoir (key `reservoir_delta`), tracked histograms (key
  `field_histogram_deltas`).
- `ngram_size_differs`, now also for `branching_delta`: §4.2 defines the transition graph
  as the projection of the counted sequences onto their first two ids, so every
  `branching` value is a function of `ngram_size`.
- `cube_axes_differ`, with both inputs' axis descriptors stripped of their collapse
  stamps: the axis schemas differ, and no surjection maps one into the other.
- `histogram_caps_differ`, with the four declared caps; neither side is reduced to the
  other's.

A key carries one reason: absence is read before order, and before caps, because an
operand that does not exist has no order and no cap.

**The keeping of a block is declared, so absence becomes decidable on the wire.** A
producer that keeps a reservoir declares `stats.reservoir_size` in every document; a
producer that builds histograms declares both histogram caps in every document (SHOULD →
MUST). An input keeps a reservoir when it carries the block or declares the cap, and
tracks histograms when it declares `param_histograms_size`.

**A collapse-only cube pair is comparable.** Two cubes of one schema whose stamps differ
are read at their minimal common collapse, which is a surjection that fuses cells and
loses granularity, never a count. `cube_diff.axes` declares that common collapse, so it
equals neither input's `axes` when the stamps differ.

## The both-absent line, and why it is drawn

When **neither** input carries the block, nothing is stated. The pair holds no operand:
no comparison was made impossible, there is a signal the producer class does not have.
Stating it would put the same keys on every diff a block-less producer ever writes (a
streaming producer that keeps no reservoir, tracks no histogram and buffers no sequence),
and a member present on every document is read as noise, which defeats the member on the
documents where it means something. The member names a comparison the PAIR made
impossible, never one the producer never offered.

## Alternatives considered

- **Compare a one-sided block as all-new.** Rejected: configuration read as workload,
  the turnover §13.2.3 already refuses for two orders.
- **Declare a collapse-only cube pair incomparable.** Rejected: the coarsening is exact,
  and since collapse is the guard a producer applies under load (§16.10), the cube would
  go silent exactly in the windows where load spiked.
- **Define the transition graph at order 1 whatever `ngram_size` is**, which would make
  `branching_delta` comparable across orders. Rejected for now: it costs a second bounded
  accounting table in every producer running above order 2 (the order-n table cannot
  yield the bigram counts, by §13.2.3's own argument) and changes every higher-order
  document's `branching`, to buy comparability for a pair §2.4 already refuses whenever
  both inputs are stamped. The question reopens the day a producer runs mixed orders in
  one stamped pipeline.
- **Read "kept" from a matching `retention_profile`.** Rejected: the identifier is opaque
  (§2.4: a consumer MUST NOT read a cap out of it), and the inference cannot reach an
  unstamped pair, which is the pair this decision exists for.
- **Reduce the larger histogram map to the smaller cap.** Rejected: a bounded map is a
  selection, and re-truncating it is not the map a producer at the smaller cap would have
  kept.

## Consequences

- Four keys and three reasons join the closed vocabulary; the schema states, per key,
  that a named property is absent and not named in `withheld_signals`.
- Breaking by the letter under GOVERNANCE §2, all in 0.10.0: §4.2's definition (a
  producer building its graph otherwise no longer conforms), the one-sided and
  cross-order MUSTs, §13.6's schema-not-stamp equality, and the two caps declared in
  every document that keeps the block.
- A pre-0.10.0 document that kept a reservoir and omitted the cap beside an empty one
  reads as keeping none, so its pair is stated incomparable: the conservative direction,
  a true comparison withheld, never a false one made.
- Relations no keyword can see stay producer obligations: which input lacks a block, that
  the stripped axes equal the inputs', that the four caps equal the inputs' declared caps.
