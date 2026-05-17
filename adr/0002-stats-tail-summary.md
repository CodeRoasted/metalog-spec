# ADR 0002 — `stats.tail_summary` block (MetaLog v0.3.0)

- **Status:** Accepted
- **Date:** 2026-05-17
- **Spec version introduced:** 0.3.0
- **Supersedes:** —
- **Related:** ADR 0001 (v1 freeze policy), SPEC §3.6, SPEC §12.3

## Context

The current spec (v0.2.x) summarises the long tail with two integers in
`stats`: `tail_count` (total events not in `top_k`) and `tail_unique`
(distinct template count in the tail). This is sufficient to compute
"how much mass is in the tail" but exposes nothing about the **shape** of
the tail.

Downstream detection layers — in particular the InSight pipeline —
encountered two recurring blind spots:

1. **Slow-onset error bursts that never quite reach `top_k`.** A new
   error template can grow steadily in the tail (3 → 10 → 30 → 80
   events/window) without ever overtaking the `top_k_size`-th
   most-frequent benign template. The tail mass changes, but
   `tail_count` alone cannot say *whether one template grew* or *every
   tail template grew a little*. The first case is alarmable; the
   second is benign drift.
2. **Tail concentration after composition.** When per-source MetaLogs
   are composed (§12) the merged tail can end up dominated by a single
   template (e.g. one host emitting a periodic warning) that should
   have been promoted to `top_k` had the documents been emitted at the
   merged grain. Consumers have no way to detect this without either
   doubling `top_k_size` (~10 KB per window per envelope; §11) or
   exchanging out-of-band tail summaries.

The "log-reductor" consumer additionally constrains the design:
MetaLogs must remain small enough to forward over bandwidth-constrained
transports. Doubling `top_k_size` is therefore not acceptable as a
solution.

## Decision

Introduce a single optional object `stats.tail_summary` carrying three
numeric fields per document:

```jsonc
"tail_summary": {
  "tail_template_count": 31,     // mirrors stats.tail_unique
  "tail_entropy_bits":   3.42,   // H over the row-normalised tail distribution
  "tail_max_rate":       0.0021  // max(count_i)/lines_observed across tail templates
}
```

The block is **OPTIONAL** at the document level. When present, all three
fields are **REQUIRED**. Producers MUST NOT emit a partial block.

### Envelope cost

Three JSON numbers + framing = **~60 bytes per window**, independent of
input cardinality. The 4 KB / 1 M-line headline budget (§11) is
preserved.

### Why these three fields

| Field | Question it answers |
|---|---|
| `tail_template_count` | *How many* templates are in the tail? (Repeated from `tail_unique` so the block is self-contained when carried alone.) |
| `tail_entropy_bits` | Is the tail concentrated on one template (low H) or spread evenly (H ≈ log₂(n))? |
| `tail_max_rate` | How loud is the loudest tail template, as a fraction of `lines_observed`? |

Together these three numbers let consumers answer "did the tail get
*lumpier*?" — the single most common false-negative gap reported by
detection-layer audits. They cannot perfectly reconstruct the tail
distribution; that would require the full histogram, which by design
the tail does not carry.

## Alternatives considered

### A. Double `top_k_size` from 64 → 128

Rejected. Adds ~10 KB per window envelope (§11). Violates the
log-reductor's bandwidth constraint and degrades the cross-cluster
shipping economics that v0.2 was designed to deliver.

### B. Per-template tail entries (`stats.tail_top_k`)

Rejected. Inverts the size-bound guarantee: any per-entry tail surface
re-introduces unbounded growth in the presence of high-cardinality
template streams. The original `top_k` truncation exists precisely to
prevent this.

### C. Carry the full tail histogram in `extensions`

Rejected. Vendor-only extensions are not interoperable; consumers
cannot rely on them being present. The blind spot described in
"Context" applies to the *core spec consumers*, not to one vendor.

### D. Per-source `tail_summary` keyed by `attribution.dimension`

Deferred. Per-source breakdown would solve the multi-source case more
fully but is coupled to the `attribution` block (§6) whose sketch
encoding is reserved for v1.0. Revisiting once attribution stabilises.

### E. Sliding-window historical tail signals

Out of scope for MetaLog. MetaLog is per-window state, not a
time-series. Trend-over-tail-shape belongs in the consumer layer
(InSight Sen's-slope detector, or equivalent).

## Consequences

### Positive

- Detection layers gain a bounded, cross-vendor view of tail shape
  with no change to `top_k_size`.
- Composition (§12) loses no additional information: `tail_summary`
  is recomputed from the merged tail directly. The block is in fact
  *more* composable than `top_k` because no per-template attribution
  is needed.
- Backwards compatible. Consumers that do not understand
  `tail_summary` simply ignore it (consistent with the "ignore unknown
  fields" rule in §8 Conformance).
- Producers that cannot or will not implement HyperLogLog (cf. §3.5.1)
  can still emit `tail_summary` — the entropy and max-rate
  computations are O(tail_unique) and require no sketching.

### Negative

- One more required dimension to test (when present). Schema tests
  must verify all three fields appear together or not at all.
- The duplication of `tail_template_count` ↔ `stats.tail_unique`
  could theoretically drift if a producer computes them at different
  points in the window-close pipeline. Mitigation: §3.6 makes the
  equality a normative MUST and a future test fixture asserts it on
  conformance samples.

### Neutral

- The choice to make the block atomic ("all three or none") rather
  than three independent optional fields trades slightly more rigid
  emission for a clearer absence semantics in consumers — preferred
  given the small envelope cost.

## Migration

Producers may adopt `tail_summary` opportunistically; no flag day.
Consumers should branch on presence:

```text
if doc.stats.tail_summary is present:
    use tail_summary.tail_entropy_bits, tail_summary.tail_max_rate
else:
    fall back to stats.tail_count, stats.tail_unique (coarser)
```

The block has no impact on `template_id` computation, composition
identity (§12.2), or the schema MAJOR.

## Open questions

- Should `tail_max_rate` be split into a per-template-id "max tail
  template" pointer to allow consumers to investigate the offender
  directly? Deferred to a follow-up ADR if the field-only summary
  proves insufficient in practice.
- Should `tail_summary` be promoted to **REQUIRED** in v1.0? Likely
  yes, contingent on producer adoption telemetry during the 0.3.x
  line.
