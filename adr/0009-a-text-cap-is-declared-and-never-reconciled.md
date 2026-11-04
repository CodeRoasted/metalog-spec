# ADR 0009 — A text cap is declared, and two caps are never reconciled

- **Status:** Proposed — accepted when the editor merges its pull request
- **Date:** 2026-11-04
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §2.4 (the comparability gate), §2.6 (`max_text_bytes`, the form `T`),
  §3.5 (field histograms and their two caps), §3.8 (`component` and its tie-break), §8 clause 4,
  §11 (the size budget), §12.1 (compose), §13 (`MetaLogDiff`), ADR 0008 (compose is commutative
  in bytes), GOVERNANCE §2, issue #26

## Context

A `value_counts` key, a `component`, a `level`, a `structural_role` and a cube coordinate value
are copied from the observed stream, and before this change no parameter bounded their length.
A key is a slice of one log line, so a consumer that retains documents could bound them only by
the longest line its transport admits: about 4 KB a key at a 4 096-byte line, hundreds of times
the same document at short text. Issue #26 proposed three declarations to close that and §11.5's
other residual: `max_text_bytes` with a SHA-256 digest form, and the two histogram caps.

Its compose clause had a composer **re-cap** an input whose cap was larger, or undeclared, to the
smaller cap before merging. Re-capping a single member is exact: the digest form of a value at
cap `L`, cut again at a power of two `L′ ≤ L / 2`, is byte-equal to `T` at `L′` of the original
value, because every byte the cut reads lies inside the prefix the first form kept. The proposal
concluded that the re-capped document is the one a producer at the smaller cap would have
emitted.

**That conclusion fails wherever the specification selects among capped members by their order
and discards the rest.** Three rules do:

- the `component` tie-break inside one window (§3.8): highest count, then the lexicographically
  smaller member;
- the per-template label rule of `compose()` at equal counts (§12.1), over `component` and the
  where-path of a `cube_coord`;
- the truncation of a merged `value_counts` map at equal counts.

The document keeps the winner and loses the members it was compared with. And `T` at two caps
can order two values differently: the cut moves from byte `L − 17` to byte `L′ − 17`, so where
the shorter prefixes agree, the digest decides.

**Example.** Two 66-byte components tie on count: `payments.settlement.a-worker-001` and
`payments.settlement.b-worker-001`, each followed by 34 `x`.

| | member |
|---|---|
| a producer at 64 emits | `payments.settlement.a-worker-001xxxxxxxxxxxxxxx~a6381e08c8600373` |
| that member re-capped to 32 | `payments.settle~a6381e08c8600373` |
| a producer at 32 emits | `payments.settle~545d5897a6d49b5f` |

Over 200 such tied pairs, sharing their first 20 bytes and computed with SHA-256 and §2.6's cut
rule, the re-capped winner differs from the producer's on 104. Two conformant composers then emit
different documents for the same observations. A consumer that aggregates by component reads the
difference as a shift.

The digest form raised one more question: how a reader learns the cap. `retention_profile` names
every retention parameter (§2.4), and the cap is one, but the identifier is opaque by definition.
A reader that decoded the cap from it would rely on a format this specification declines to
define.

## Decision

1. **The cap is a declared root member, `max_text_bytes`,** on a MetaLog and on a `MetaLogDiff`.
   It is a power of two from 32 to 4 096. A document that omits it is uncapped, and a producer
   that caps **MUST** declare. `retention_profile` still changes with the cap, since §2.4's rule
   reaches it, but a reader never reads the cap out of it.
2. **`T` is applied once,** to an observed value, when the producer builds the window's document.
   No operation applies it to a member of a document: not compose, not a diff, not a consumer.
3. **`compose()` and a `MetaLogDiff` refuse two inputs that declare different caps, or of which
   only one declares it.** The rule binds whether or not the inputs carry `retention_profile`.
   When both carry it, §2.4's gate refuses the pair first, so the new gate decides the pair that
   gate does not reach.
4. **The two histogram caps,** `stats.param_histograms_size` and `stats.value_counts_size`, are
   declared as issue #26 proposed, and compose takes the minimum of each. Their selections are
   made by `param_index` and by count, not over text at two caps, so the minimum stays what a
   producer at the smaller caps would hold.
5. **Conformance.** The schema marks every position of observed text with
   `x-metalog-observed-text`, and §8 clause 4 bounds each such member by the declared cap. The
   refusal is a rule over two documents, which no single-document check can decide.

## Alternatives considered

**Re-cap, as issue #26 first proposed.** Rejected: it is exact member by member and not exact
over a selection, as the example shows.

**A cap-invariant selection order.** Every admissible cap is at least 32, and every cap of 64 or
more is at least twice 32, so any document determines `T` at 32 of each value it holds. Breaking
every such selection by `T` at 32, then by the member bytes, would pick the same value at every
cap, and re-capping would become exact: over the same 200 pairs, no winner differs. Rejected:

- it rewrites two public MUSTs (§3.8's tie-break and §12.1's label rule) for every producer,
  capped or not;
- it requires SHA-256 in every such tie, including in a producer that caps nothing;
- it serves only a composition that §2.4 already refuses whenever both documents carry
  `retention_profile`.

If a use for composing across caps appears, this is the recorded way back: it moves no member
of the wire format, only an order.

**Carry the cap in `retention_profile`.** Rejected: the identifier is opaque (§2.4), and a value
a reader must decode from it is a format the specification has declined to define.

**An extension member until the core member lands.** Rejected: once the core member exists,
the extension member would duplicate a standard field, which §7 forbids, so every reader would
have to migrate off it; until then, two carriers of one fact could disagree.

## Consequences

- No existing document changes validity: every new member is optional, and capping is a MAY.
- A composer or diff producer is bound only by documents that declare the new member, which no
  earlier version defined. The change is therefore additive under GOVERNANCE §2.
- Two uncapped documents compose and diff as before. Two documents at one cap compose and diff
  with no re-mapping. A capped and an uncapped document are refused, loudly.
- §11.5's two residuals shrink to one: template strings and extension payloads.
