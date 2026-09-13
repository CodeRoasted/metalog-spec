# ADR 0006 — No size per line count: the 4 KB headline is withdrawn

- **Status:** Accepted — editor (Emmanuel Prunet), 2026-09-13
- **Date:** 2026-09-13
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §11.1 (what is bounded, and by what), §11.2 (per-entry costs),
  §11.3 (the formula), §11.4 (worked ceilings), §11.5 (the section this ADR
  rewrites), §3.4 (template modes), §3.6.1, README, RATIONALE §R1 and §R3,
  ADR 0002, GOVERNANCE §2

## Context

From 0.1.1 this specification published a size target: *"≤ 4 KB per MetaLog
covering ≥ 1 M log lines"*. It was the README's tagline — *"What was this log
stream doing in the last N minutes, in 4 KB or less?"* — and §3.6.1, RATIONALE
§R1 and §R3, and ADR 0002 each cited it as a budget to preserve.

In 0.9.0 §11 was rewritten as a formula, and §11.5 scoped the target to the
`stats`-only document (no `reservoir`, no `behavior`, no `cube`), reached by
either of two routes:

1. `top_k_size ≤ 32` in inline mode, or
2. `top_k_size ≤ 64` in id-only mode, template strings out of band.

Neither route had been measured when it was written.

## The evidence

**Route 1 was measured, and it misses.** On 2026-09-12 the reference
implementation — the only implementation the README lists — built the target's
own scope in its most favourable form: one window of exactly 1 000 000 lines over
64 templates with integer harmonic counts; `top_k_size` 32, full; no reservoir,
no `behavior`, no `stability`; no parameters, so no `param_histograms`; one level;
every `top_k` entry carrying a 55–56-byte template string inline; compact JSON.

| Form of the same document | Bytes | Against 4 096 |
|---|---|---|
| inline, as serialised | **6 113** | +49 % |
| every template string emptied | **4 331** | +6 % |
| id-only (the `template` member dropped) | **3 883** | −5 % |

The 32 inline entries take 5 438 bytes and everything else takes 675. The last two
rows are **computed** on the serialised document, not emitted: the reference
implementation does not emit id-only mode. The second row closes route 1 for any
skeleton on this entry shape: at `top_k_size` 32, the inline document misses the
target with template strings of zero bytes. A producer whose entries are leaner
than this one's is bounded by §11.2's arithmetic below, not by this measurement.

**Route 2 is contradicted by this specification's own text**, with no measurement
needed. §11.4 prices a `stats`-only document at `top_k_size` 64 at ~9 KB, and
§3.6.1 prices 64 id-only entries at ~9 KB. At the lowest cost §11.2 publishes for a
`top_k` entry (99 bytes, carrying `level`), 64 id-only entries come to ~6.3 KB
before the fixed envelope.

**The target was the wrong kind of claim, not only a wrong number.** §11 opens by
refusing any single figure, because it "would be a figure for one producer's
configuration and would silently rot". A size per line count is worse than one
producer's figure: it pairs a size with a quantity the size does not depend on.
Per §11.1 a document is bounded by its caps, and `lines_observed` reaches it only
through the width of the numbers it records. The "≥ 1 M log lines" half of the
headline carried no information, and the "≤ 4 KB" half was a configuration claim
presented as a property of the format.

## Decision

**Withdraw the headline everywhere, and publish no size per line count.**

§11.5 states the bound that holds: a document's size is set by the caps its producer
declares, its template mode (§3.4) and the content its entries carry, never by the
number of lines its window observed. §11.3's formula, applied to a document's
declared caps, is the bound; `envelope_bytes` is the one exact figure. Both route
clauses are deleted. The README tagline and §11 summary, §3.6.1, RATIONALE §R1 and
§R3, and ADR 0002 now argue from the formula instead of from the target.

**Nothing on the wire changes.** No field, schema, example or conformance clause
moves, and no document changes validity. The change is **editorial** under
GOVERNANCE §2 — §11 is informative and §3.6.1 is rationale — so no RFC or comment
window applies. The CHANGELOG records it under 0.10.0, which is unreleased.

## Alternatives considered

### B. Rescope the target to the configuration that measured under it

Keep "≤ 4 KB" and scope it to id-only mode at `top_k_size ≤ 32`, with strings out
of band (3 883 bytes, computed). Rejected, for three reasons:

- The tagline stays false for every inline document, and inline is the mode a
  self-contained document uses (§3.4).
- It publishes one producer's figure, which §11 refuses, with a 213-byte margin.
  §11.2 prices a `component` on a `top_k` entry at +23 bytes; over 32 entries that
  is 736 bytes, and the target is missed again. That figure is arithmetic, not a
  measurement.
- It would need rescoping the next time any producer's entry shape moved — the rot
  §11 was rewritten to prevent.

### C. Change the wire until 4 KB is reached

Shorten member names, or drop members in a `stats`-only mode. Rejected. It breaks
every implementation, both schemas and the conformance fixtures of a public format
to rescue a sentence that was never a property of that format. Shortened names also
cut against the human-readable form RATIONALE §R1 chose JSON for.

### D. Keep the target and label it aspirational

Rejected. A number no implementation meets, in a specification whose value is that
its claims can be checked, costs the reader's trust in every other figure in §11.
A target with no route that reaches it is not a target.

## Consequences

- **The memorable number leaves the public pitch.** That is this decision's cost,
  and it is accepted: the replacement tagline is weaker as a slogan and true as a
  claim.
- **The CHANGELOG entries for 0.1.1, 0.3.0 and 0.9.0 still repeat the headline**
  and are left as written. They record what those versions said; the 0.10.0 entry
  records the withdrawal.
- **Two residuals remain, and §11.5 states both.** `param_histograms` is bounded by
  caps the document does not declare, and no parameter caps the length of a
  template string, a `component` or an extension payload. A consumer that needs an
  exact figure reads `envelope_bytes`.
- **Anyone who repeated the target** in their own material should re-derive any
  size they publish from their own declared caps and §11.3, and publish the
  configuration with it.
