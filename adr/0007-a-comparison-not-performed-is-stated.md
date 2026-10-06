# ADR 0007 — A comparison not performed is stated, never left as an absence

- **Status:** Proposed — pull request #21; accepted when the editor merges it
- **Date:** 2026-10-06
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §2.4 (the comparability gate and `behavior.ngram_size` in
  `retention_profile`), §4 (`top_ngrams`, `probability`), §12.1 (the compose clause
  for two orders), §13.1 (`ngram_delta` across two orders), §13.2 (the witness rule),
  §13.2.1 (`x-metalog-vacuous`, clause 5: descriptors), §13.2.2 (`withheld_signals`),
  §13.2.3 (the member this ADR decides), GOVERNANCE §2

## Context

`behavior.ngram_size` fixes what a `top_ngrams` key denotes: an order-2 key and an
order-3 key are different objects. The same pull request adds the parameter to
`retention_profile` (§2.4), so two documents produced at different orders and both
stamped are refused by the comparability gate. But that gate is conditional: it binds
only when **both** inputs carry the identifier. An unstamped pair at two orders still
reaches §13.

For that pair, a producer has three things it could do with `ngram_delta`, and the
text before this decision said nothing about any of them:

- **Compute it.** No key can match across orders, so every n-gram of one side reads as
  vanished and every n-gram of the other as new. Under §13.2 that non-empty delta is a
  **witness**, and the document asserts `"changed"` for a change in configuration.
- **Omit it.** This is what the reference implementation does. Under §13.2.1 step 3 an
  absent property is not a witness, so the document reads exactly like a comparison that
  ran and found no n-gram movement. A reader cannot tell the two apart.
- **Reduce one order to the other** and compare at a common order.

## Decision

When both compared documents carry `behavior` at different `ngram_size`, a producer
**MUST** omit `ngram_delta` and **MUST** state the omission, with its reason, in a new
optional member at the `MetaLogDiff` root:

```jsonc
"incomparable_signals": {
  "ngram_delta": { "reason": "ngram_size_differs", "previous_ngram_size": 2, "current_ngram_size": 3 }
}
```

- The member is keyed by the omitted signal property's name; its value carries a
  `reason` from a vocabulary the schema closes, and the evidence for that reason.
- It is a **descriptor** under §13.2.1 clause 5: never a witness. A comparison that was
  not performed is evidence of neither outcome, so the member never makes `"changed"`
  legal and never makes `"unchanged"` false. `"unchanged"` beside it means the
  properties that *were* compared did not change, and a consumer **MUST NOT** read
  either outcome as a statement about a property the member names.
- Every key is absent from the document and is not named in `withheld_signals`. The
  schema states both with a root `dependentSchemas`.
- The rule binds whether or not the inputs are stamped. Stamped pairs are normally
  refused by §2.4 first; this is what the residual pair receives.

**No reduction between orders**, in either direction:

- Down (order `n` to `m < n`): `top_ngrams` is truncated at `top_ngrams_size`, and
  `dropped_ngram_observations` counts observations refused before counting. Neither
  says which order-`m` key the missing mass would have fed, so marginal counts are
  lower bounds of unknown slack and the reduced ranking can be wrong. The last `n − m`
  order-`m` sequences of each stream have no order-`n` extension, so the sum
  undercounts even on an untruncated table.
- `probability` is p(last | first n − 1), normalised before the cut (§4). The
  conditional at one depth does not determine the conditional at another without the
  weight of every longer prefix, and neither those weights nor the pre-cut denominator
  is on the wire.
- Up (order `m` to `n > m`) needs sequences the order-`m` table never held.

## Alternatives considered

1. **Silent absence** (the reference implementation's behaviour before this decision).
   Rejected: a false all-clear. The document is indistinguishable from one whose
   comparison found no n-gram movement.
2. **Total turnover** (compute the delta anyway). Rejected: it witnesses `"changed"` for
   a configuration difference, which is the defect the same pull request's §2.4 change
   removes for stamped pairs.
3. **Decay: reduce the higher order to the lower, or carry the lower order up.**
   Rejected: no reduction is exact on a truncated table, and `probability` is
   conditioned at a different depth on each side (above). A reduced delta would present
   an estimate of unknown error as a measurement.
4. **Reuse `withheld_signals` (§13.2.2).** Rejected: that member names a change the
   producer **found** and did not serialise, and it is a witness by declaration. Naming
   `ngram_delta` there would assert `"changed"` for a comparison nobody performed.
   Spelling both under one word, with opposite witness semantics, would also invite
   exactly that confusion, which is why the new member is not called `withheld_*`.
5. **Fail or refuse the whole diff.** Rejected: the incomparability is confined to one
   block. Refusing the document would destroy a well-defined template, divergence and
   tail comparison, the same reason §12.1 omits only `behavior` under composition.
6. **A free-text reason, or an n-gram-specific member** (for example a `reason` string
   inside a stub `ngram_delta`). Rejected: a free-text reason cannot be checked or
   branched on, and a stub `ngram_delta` must declare one `ngram_size` where two exist.
   The keyed member with a closed vocabulary is the smallest shape that states a reason
   a machine can read, and its vocabulary grows additively.

## Consequences

- One new optional member, a descriptor, in the witness set by §13.2.1 step 2. The
  shipped schema now declares fourteen optional signal properties.
- A producer that omits `ngram_delta` across two orders without the member is
  non-conformant; so is one that computes the delta across them. Both are breaking by
  the letter under GOVERNANCE §2, and both land in 0.10.0, which has no tag and no
  Release.
- The conformance tool gains three fixtures and one control
  (`incomparable-signal-is-not-a-witness`). Two relations stay producer obligations
  because no keyword can see the inputs: the two orders equal the inputs' and differ
  from each other.
- **Not decided here, and named so nobody assumes it was:** a pair where only ONE
  input carries `behavior`, and a `cube_diff` across unequal `axes` (§13.6), are absent
  from the diff today with no statement either. Both have the same shape as this
  decision's case, and the vocabulary can take them additively; neither is in this
  text.
