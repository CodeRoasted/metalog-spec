# MetaLog Specification — v0.9.0 (Draft)

> **Status:** Draft. Subject to incompatible change until v1.0.
> **Cross-reference:** [`RATIONALE.md`](RATIONALE.md) for *why*
> each design decision was made.

This document uses [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)
keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**.

> **What changed in 0.6 (the cube — EXPERIMENTAL):** added §16 the **`cube`**
> block — an intra-window joint categorical condensation (a *closed cube* over
> `level × structural_role × where`-chain) — and §13.6 **`cube_diff`** (its
> emerging border). The cube is **additive, provisional, and removable in a single
> revert** (§16.8); it is gated for comparability by `canonicalization_version` and
> `retention_profile`. `reservoir` entries gain an optional `cube_coord` (the
> LOCATION-only reservoir→cell cross, §16.6). See [`CHANGELOG.md`](CHANGELOG.md).
>
> **What changed in 0.5 (Phase-3 formalization, in progress):** added §15 the
> **re-derivation coordinate** — every window is addressable back to its source
> (`raw(window) = replay(source, bounds)`) for on-demand raw recovery and citable
> findings. §14 *Sessions* is now a removed-section tombstone (deferred to
> correlation-keyed `trace_id` processing). Further 0.5 additions are landing:
> the `reservoir` (salient-entry) section, header `canonicalization_version` /
> `retention_profile` with `compose()`/diff version-gating, and compose-visible
> field histograms. See [`CHANGELOG.md`](CHANGELOG.md).
>
> **What changed in 0.2:** template strings are no longer required
> inside `stats.top_k` entries — they live in an optional top-level
> `templates` dedup map instead, and may be omitted entirely
> (id-only mode). The `behavior` block has been formalised
> (`dominant_path`, `graph_edge_count`, `branching`). Two sibling
> sections were added: `compose()` (§12) for merging MetaLogs across
> windows or shards, and a separate `MetaLogDiff` document (§13). See
> [`CHANGELOG.md`](CHANGELOG.md) for the full diff.

---

## 1. Definitions

- **Log line** — A single textual record emitted by a system,
  terminated by a newline.
- **Template** — The invariant skeleton of a log line, with variable
  parts replaced by placeholders. Example: the line
  `User alice logged in from 10.0.0.1` has template
  `User <*> logged in from <*>`.
- **TemplateID** — A stable, content-derived identifier for a
  template. See §3.2.
- **Window** — A contiguous time interval over which a single MetaLog
  is computed.
- **Producer** — A program that consumes log lines and emits MetaLog
  documents.
- **Consumer** — A program that reads MetaLog documents (dashboard,
  alert engine, LLM prompt builder, archive, etc).
- **MetaLog** — A JSON document conforming to this specification.
- **MetaLogDiff** — A separate JSON document describing the
  difference between two MetaLogs. See §13.
- **Cube** — A bounded *joint* over a small, fixed set of low-cardinality
  categorical axes, condensed by closure (a *closed cube*). See §16.
- **Emerging border** — The minimal `(lower, upper)` cell-pair characterising
  what grew (or vanished) between two cubes. See §13.6.

---

## 2. Document structure

A MetaLog **MUST** be a single JSON object containing the following
top-level fields:

| Field | Type | Required | Purpose |
|---|---|---|---|
| `metalog_version` | string | yes | Spec version this document conforms to. SemVer string (e.g. `"0.6.0"`). |
| `producer` | object | yes | Identifies the producing implementation. See §2.1. |
| `window` | object | yes | The time interval covered. See §2.2. |
| `source` | object | yes | What was observed (service, host, fleet). See §2.3. |
| `canonicalization_version` | string | no | Opaque identifier for the canonicalization rules in effect. Gates `compose()`/diff comparability. See §2.4. |
| `retention_profile` | string | no | Opaque identifier for the retention parameters (top_k, reservoir, salience weights, diversity caps). Gates `compose()`/diff comparability. See §2.4. |
| `stats` | object | yes | Per-template counts and frequency metrics. See §3. |
| `templates` | object | no | Optional dedup map `template_id → template_str`. See §3.4. |
| `behavior` | object | no | Sequence/transition fingerprint. See §4. |
| `stability` | object | no | Divergence from the previous window. See §5. |
| `attribution` | object | no | Distribution of templates across sub-sources. See §6. |
| `cube` | object | no | Joint categorical condensation (closed cube). **Experimental.** See §16. |
| `coordinate` | object | no | Re-derivation coordinate: `raw(window) = replay(source, bounds)`. See §15. |
| `run_outcome` | string | no | Terminal verdict of the run this window covers, when the stream stated one. See §2.5. |
| `provenance` | array | no | When this document was composed from others. See §12. |
| `extensions` | object | no | Vendor-specific data. See §7. |

Producers **MUST** emit the required fields and **MAY** emit any
subset of the optional fields. Consumers **MUST** ignore unknown
top-level fields and **MUST** ignore unknown keys inside
`extensions`.

### 2.1 `producer`

```jsonc
{
  "name": "insight",          // string, required
  "version": "0.6.0",         // string, required, SemVer
  "implementation_uri": "https://github.com/.../insight"  // string, optional
}
```

### 2.2 `window`

```jsonc
{
  "start": "2026-04-24T10:00:00Z",   // RFC 3339, UTC, required
  "end":   "2026-04-24T10:05:00Z",   // RFC 3339, UTC, required
  "duration_seconds": 300,            // number, required, MUST equal end - start
  "lines_observed": 184273            // integer, required, count of log lines that fed this MetaLog
}
```

`start` **MUST** be strictly less than or equal to `end`
(equality is permitted for empty / heartbeat documents).
`duration_seconds` **MUST** equal `end - start` rounded to the
nearest second. If a producer cannot count `lines_observed` exactly,
it **MUST** emit its best estimate and **SHOULD** emit an
`extensions.org.metalog.lines_observed_estimated: true` flag.

### 2.3 `source`

```jsonc
{
  "service": "checkout-api",          // string, optional
  "fleet":   "prod-eu-west",          // string, optional
  "host_count": 12,                   // integer, optional, distinct hosts contributing
  "tags": { "env": "prod", "region": "eu-west" }  // object<string,string>, optional
}
```

Identifies *what* the MetaLog describes. All fields are optional but
producers **SHOULD** populate at least one of `service` or `fleet`.

### 2.4 `canonicalization_version` and `retention_profile`

A MetaLog **MAY** carry two opaque processing-identifier strings that name the
**contract** under which it was produced:

- `canonicalization_version` — names the **canonicalization rules** in effect
  (masking, tokenization, classification — the rules that map raw bytes to
  templates and structural metadata). It **MUST** be bumped when those rules'
  *output-affecting* semantics change; a binary rebuild with no rule change
  **MUST NOT** bump it. It is **not** a binary build id.
- `retention_profile` — names the **retention parameters** in effect: `top_k`
  size (§3.1), reservoir admission weights and size and diversity caps (§3.7),
  and the salience arithmetic. It **MUST** be bumped when any of those
  parameters change.

The values are **opaque strings**. This spec defines neither a registry of names
nor a canonical format; producers and consumers within an environment **MUST**
agree on their meaning out-of-band.

**Comparability gate (normative).** When both inputs to `compose()` (§12) or to
a `MetaLogDiff` operation (§13) carry `canonicalization_version`, the values
**MUST** be **equal**; an operation across mismatched values **MUST** fail or
**MUST** signal incompatibility to the consumer. The same rule applies to
`retention_profile`. When an input omits an identifier, the operation **MAY**
proceed but the consumer **SHOULD** treat the result with caution — the
documents may have been produced under incompatible contracts.

The `cube` block (§16) is part of these contracts: its **axis set**, each axis's
**chain** levels, and the frozen **`floor_depth`** are fixed by the
`canonicalization_version` (WHERE grounding) and `retention_profile` (axis/floor
configuration). Two cubes are diffable into a `cube_diff` (§13.6) **only** when both
identifiers match **and** their `axes` are equal.

### 2.5 `run_outcome` — terminal verdict of the run the window covers (optional)

> **New in v0.9.0.** A string at the document root.

A window often covers a bounded **run** — a CI job, a batch, a deployment step —
that ends by stating a verdict about itself. `run_outcome` carries that verdict as
a **closed**, low-cardinality label:

| value | meaning |
|---|---|
| `success` | the run completed and stated no failure |
| `failure` | the run failed as a whole |
| `unstable` | the run completed and stated a *partial* failure — not the same claim as `failure` |
| `aborted` | the run did **not** complete: cancelled, timed out, or killed. **The observed stream is truncated**, and every count in the document is a count over a stream that stopped early. |

**The enum is closed.** A producer whose source system publishes a verdict outside
these four **MUST NOT** widen it; that verdict is vendor data and belongs in
`extensions` (§7). The values are lower-case and **case-sensitive**, as for every
other vocabulary this spec *mints* (`sketch_type` §6, `cube.axes[].kind` §16.2).
This is deliberately unlike `level` (§3), whose values are the observed stream's
own tokens and are not minted here.

**Normative points.**

- `run_outcome` **MUST** be derived from the **observed events** — the stream's own
  terminal statement — and **MUST NOT** be taken from producer state or an
  out-of-band control plane. Same species as `level` and `component` (§3.8): a
  label the observed stream carries about itself. A field sourced from outside the
  window's bytes is not re-derivable from them, which is the guarantee §15 exists
  to make.
- It **MUST** be **omitted** when no verdict was observed. There is **no** wire
  value meaning "unknown", so absence carries the same meaning in every version of
  this spec, including documents produced before v0.9.0.
- Consumers **MUST NOT** read absence as `success`. Absence means **this document
  asserts no verdict** — because none was observed, because the producer predates
  the field, or because a composition could not agree on one.
- **Composition (§12).** A composed document **MUST NOT** carry a `run_outcome`
  unless every input that carries one carries the **same** value; when they agree
  it **MAY** carry that value. A composed window spanning a green run and a red one
  has no single verdict, and asserting either would be a claim no input made.
  Omitting is the safe direction precisely because absence asserts nothing.

**Why a consumer reads it before reading the deltas.** Whether two windows straddle
a `success` → `failure` boundary changes how every delta in a `MetaLogDiff` (§13)
should be read: a large divergence across a green→red pair is the finding, while
the same divergence between two failed runs may be the difference between two
unrelated failures. And an `aborted` window is truncated by construction — a
template that appears to have *vanished* may simply never have been reached.

---

## 3. `stats` — per-template frequency

The required core of a MetaLog. Captures *which templates fired and
how often*, in bounded space.

```jsonc
{
  "unique_templates": 87,             // integer, required, distinct templates seen in this window
  "top_k": [                           // array, required, ordered by count desc
    {
      "template_id": "h:8a3f...c012",      // string, required, see §3.2
      "count":       12453,                 // integer, required
      "frequency":   0.0676,                 // number, required, count / lines_observed
      "template":   "User <*> logged in from <*>",  // string, OPTIONAL — see §3.4
      "level":       "INFO",                 // string, optional, dominant log level
      "component":   "auth"                  // string, optional, dominant source — see §3.8
    }
    // ... up to k entries ...
  ],
  "top_k_size": 64,                   // integer, required, value of k used
  "tail_count": 4117,                  // integer, required, sum of counts not in top_k
  "tail_unique": 31,                   // integer, required, number of distinct templates in tail
  "tail_summary": {                    // object, optional — see §3.6 (new in v0.3.0)
    "tail_template_count": 31,         // integer, required if tail_summary present
    "tail_entropy_bits":   3.42,       // number,  required if tail_summary present
    "tail_max_rate":       0.0021      // number,  required if tail_summary present
  },
  "entropy_bits": 5.83                 // number, optional, Shannon entropy over template distribution
}
```

### 3.1 Bounded size

A producer **MUST** cap the `top_k` array at a fixed size determined
before window start. The default and **RECOMMENDED** value is
`k = 64`. Producers **MAY** use a different `k` and **MUST** report
the value used in `top_k_size`.

The choice of `k = 64` is a deliberate compromise between coverage
and envelope size; see [§11 Size budget](#11-size-budget) for the
math and [`RATIONALE.md` §R3](RATIONALE.md#r3-why-a-fixed-top-k--tail-summary-not-a-full-histogram)
for the reasoning. Producers targeting edge / ultra-compact
deployments **SHOULD** use `k = 16`. Producers targeting wide
high-cardinality services **MAY** use `k = 256` and accept the
larger envelope.

The remaining templates **MUST** be summarised into `tail_count` and
`tail_unique`. This guarantees a MetaLog has bounded size regardless
of input cardinality.

### 3.2 TemplateID

`template_id` is a stable, content-derived identifier:

```
template_id = "h:" + lower_hex(SHA-256(template_string)[0:16])
```

- The hash function **MUST** be SHA-256 over the UTF-8 bytes of the
  canonical template string. The 32-byte digest **MUST** be
  truncated to its first 16 bytes (the leading 128 bits) and encoded
  as 32 lowercase hex characters, prefixed with `"h:"`.
- The input **MUST** be the UTF-8 bytes of the canonical template
  string with placeholders normalised to `<*>` and surrounding
  whitespace trimmed.
- Two MetaLogs from different producers describing the same template
  **MUST** compute the same `template_id`. This is what makes
  MetaLogs comparable across implementations.

SHA-256 is chosen over faster alternatives (BLAKE3, xxh3) because it
is available in every mainstream language standard library. See
[`RATIONALE.md` §R2](RATIONALE.md#r2-why-sha-25616-for-template_id)
for the rationale.

The `"h:"` prefix is reserved for hash-based IDs. Other prefixes are
reserved for future ID schemes; consumers **MUST** treat unknown
prefixes as opaque identifiers and **MUST NOT** assume two IDs refer
to the same template unless their full strings (including prefix)
are equal.

### 3.3 Frequency precision

`frequency` **MUST** be in `[0.0, 1.0]` and **SHOULD** be reported
to at least 4 significant digits. Producers **MAY** round to fewer
digits if the underlying count is itself an estimate.

### 3.4 Template strings — id-only mode and dedup map

A `top_k` entry's `template` field is **OPTIONAL** in v0.2.0
(it was required in v0.1.x). Producers **MAY** emit template
skeletons in any of three modes:

| Mode | Where | Use case |
|---|---|---|
| **inline** | `stats.top_k[i].template` | Self-contained documents; small cost (~50–100 B per entry). |
| **dedup** | top-level `templates` map | Many MetaLogs sharing a corpus (multi-window archives, sharded composition). Each `template_id` appears once across the document. |
| **id-only** | omitted entirely | Bandwidth-bound transports; the consumer reconstructs strings from a side channel keyed by `template_id`. |

The top-level dedup map is shaped:

```jsonc
{
  "templates": {
    "h:90585f810bb26f3ccb3193975150dd40": "User <*> logged in from <*>",
    "h:6c05dc06a24a45a267b3818679e456dd": "GET /api/v1/cart/<*> 200 <*>ms"
  }
}
```

- Keys **MUST** match the `^[a-z]+:.+$` template_id format.
- A consumer that needs the human-readable template for an entry
  **MUST** look it up first in the inline `template` field (if
  present), then in the top-level `templates` map (if present), then
  fall back to opaque rendering of the `template_id`.
- A producer **SHOULD NOT** emit both inline and the dedup map for
  the same `template_id` (wasted bytes); if it does, the inline
  value **MUST** be byte-equal to the map value.
- A composer (§12) **SHOULD** prefer the dedup map for the
  composed document.

Producers operating in id-only mode **MUST** ensure consumers have
out-of-band access to a `template_id → template_str` resolver
(e.g. a separate dictionary endpoint, a sidecar archive file, or
the producer's source code). Otherwise the document is opaque.

---

### 3.5 Field histograms — wildcard parameter distributions (optional)

> **New in v0.3.0.** Producers **MAY** include per-template, per-wildcard-position
> value-count histograms inside each `top_k` entry under the key `param_histograms`.

When a Drain-style template has wildcard positions (e.g. `"GET <*> -> <*>"`), the
histogram re-surfaces the empirical distribution P(value | template_id, param_index)
so that consumers can detect distribution shifts in individual field slots (e.g. URL
paths, status codes) rather than only at the template level.

```jsonc
{
  "template_id": "h:8a3f...",
  "count": 12453,
  "frequency": 0.0676,
  "param_histograms": [        // array, optional; one entry per tracked wildcard slot
    {
      "param_index": 0,        // integer, required, 0-based wildcard position
      "value_counts": {        // object, required, top-N observed values → count
        "/api/users": 800,
        "/health":    200
      },
      "total":       1100,     // integer, required, total events for this slot
                               // MAY exceed sum(value_counts) when the cap is hit
      "approximate_cardinality": 1847  // integer, optional — see §3.5.1
    },
    {
      "param_index": 1,
      "value_counts": { "200": 950, "500": 50 },
      "total": 1000,
      "approximate_cardinality": 6
    }
  ]
}
```

- A producer **MUST NOT** emit `param_histograms` for entries not in `top_k`.
- The `value_counts` map **MUST** be bounded (producers **SHOULD** cap at a
  configurable limit, default 256, and count overflows in `total`).
- A consumer **MUST** treat an absent `param_histograms` array as equivalent to
  an empty array (the slot was not tracked).
- **The whole histogram is cross-machine bit-identical (determinism).** The
  value-distribution fields — `param_index`, `value_counts` counts, `total` — are
  integers. The slot's Shannon entropy is **losslessly derivable from `value_counts`**
  and therefore **MUST NOT** be emitted here (a consumer that needs it computes it).
  `approximate_cardinality` is `uint64`-typed but HLL-estimate-derived; it **MUST** be
  computed **deterministically — no libm transcendentals** — via an exact dyadic
  register sum plus a fixed-point logarithm, so that it is **bit-identical across
  machines** (§15.6). It is kept on the wire because it is the **uncapped**
  distinct-value count, **not** derivable from the capped `value_counts` (its whole
  reason to exist). `MetaLogDiff.field_histogram_deltas` (§3.5.2) carries
  `js_divergence` + entropy deltas; these too **MUST** be computed deterministically
  (fixed-point logarithm, defined reduction order) so they are bit-identical across
  machines.

#### 3.5.1 `approximate_cardinality`

`approximate_cardinality` is an **OPTIONAL** `uint64` field in each
`param_histograms` entry. When present, it contains a HyperLogLog estimate of the
number of **distinct** values observed for that wildcard slot in this window,
independent of the `value_counts` cap.

Producers **SHOULD** use a HyperLogLog sketch with standard error ≤ 1.5% (precision
`p = 14`, 16 384 registers). The field is useful for detecting high-cardinality
injection attacks (§3.5.2) and for cardinality-aware alerting in downstream
detectors.

- When `approximate_cardinality` is absent, consumers **MUST** use
  `len(value_counts)` as a lower-bound estimate of distinct values.
- `approximate_cardinality` **SHOULD** be ≥ `len(value_counts)`.
- Producers **MUST NOT** report `approximate_cardinality = 0` for a slot that
  received at least one event.

#### 3.5.2 Cardinality drift and the `MetaLogDiff` extension

A `MetaLogDiff` (§13) that covers documents containing `param_histograms` **SHOULD**
include a `field_histogram_deltas` array. Each entry carries the per-slot JS
divergence and — when both documents provide `approximate_cardinality` — a
cardinality delta:

```jsonc
"field_histogram_deltas": [
  {
    "template_id":             "h:8a3f...",   // required
    "param_index":             0,             // required
    "js_divergence":           0.31,          // number, optional
    "previous_entropy_bits":   0.28,          // number, optional
    "current_entropy_bits":    0.47,          // number, optional
    "previous_sample_count":   1100,          // integer, optional — new in v0.8.0
    "current_sample_count":    1315,          // integer, optional — new in v0.8.0
    "previous_cardinality":    1847,          // integer, optional
    "current_cardinality":     183204,        // integer, optional
    "cardinality_delta":       181357         // integer (signed), optional
                                              // = current - previous; positive = grew
  }
]
```

- `cardinality_delta` **MUST** equal `current_cardinality - previous_cardinality`
  (signed, positive = grew, negative = shrank).
- `previous_sample_count` / `current_sample_count` (**new in v0.8.0**) are each
  side's `param_histograms[].total` — the **number of observations the
  distribution was estimated from**. A producer emitting `js_divergence`
  **SHOULD** emit them, because without a sample size the divergence is not
  interpretable: a JS of 0.9 over eleven observations and a JS of 0.9 over eleven
  thousand are different claims, and only the second is a regime shift. Consumers
  **SHOULD** apply a minimum-sample floor before acting on `js_divergence`. These
  are **observation** counts, distinct from `*_cardinality` (distinct values) and
  from the template's stream share.
- Consumers detecting high-cardinality injection **SHOULD** alarm when
  `current_cardinality / previous_cardinality > N` (e.g. N = 10) and
  `previous_cardinality < threshold` (baseline was low-cardinality).
- `field_histogram_deltas` **MUST** be sorted by `js_divergence` descending.

**Composition (compose-visible).** `param_histograms` are **carried** through
`compose()` — they are not lossy at composed scales. For each
`(template_id, param_index)` present in both inputs the composer merges
`value_counts` (union + summed counts, truncated to the cap), sets the merged
`total`, recomputes `entropy_bits`, and updates `approximate_cardinality`. See
§12.1 for the normative rule. As a result, per-slot value-distribution shifts
remain visible in a `MetaLogDiff` taken against a composed (pyramid-baseline)
document, not only at the raw scale.

> **Wire-emission status (reference producer, v0.5.0).** `param_histograms` is an
> **optional** wire field. The reference producer (`insight-metalog`) computes the
> histograms and carries them through `compose()` in its **internal representation**,
> but does **not yet emit them on the wire** (and `MetaLogDiff.field_histogram_deltas`
> is likewise computed but not yet serialised) — a conformant choice, since a consumer
> treats an absent `param_histograms` as an empty array. Wire emission is **batch-mode**:
> the §11 streaming envelope cannot afford per-slot value maps, but a full-fidelity
> (batch) diff can. It lands together with the ordinal **Wasserstein-1** trait
> — `js_divergence` over `value_counts` treats a
> numeric slot's support as **unordered**, so emitting histograms for ordinal slots
> before that trait exists would surface a magnitude-blind delta. When emitted,
> `value_counts` **MUST** serialise in a deterministic (key-sorted) order for replay
> bit-identity (§15.6).

---

### 3.6 `tail_summary` — bounded shape of the long tail (optional)

> **New in v0.3.0.** Producers **MAY** include a `tail_summary` object inside
> `stats` to give consumers a bounded, comparable picture of the templates that
> fell *outside* `top_k`. The block adds at most three numeric fields to the
> document; cost is ~60 bytes per window irrespective of input cardinality.
> See [`adr/0002-stats-tail-summary.md`](adr/0002-stats-tail-summary.md) for
> the design discussion and the trade-off against composition lossiness
> (§12.3).

```jsonc
"tail_summary": {
  "tail_template_count": 31,     // integer, required if tail_summary present
                                 // distinct templates contributing to tail_count
                                 // (informational mirror of stats.tail_unique;
                                 // emitted alongside the other fields so the
                                 // tail can be reasoned about in isolation)
  "tail_entropy_bits":   3.42,   // number,  required if tail_summary present
                                 // Shannon entropy over the *tail-only*
                                 // distribution (counts of templates NOT in
                                 // top_k, row-normalised across the tail)
  "tail_max_rate":       0.0021  // number,  required if tail_summary present
                                 // max(count_i) / lines_observed across all
                                 // tail templates; gives consumers an upper
                                 // bound on per-template tail activity
}
```

- The block is **OPTIONAL**. Producers **MAY** omit `tail_summary` entirely;
  consumers **MUST** treat its absence as "no tail-shape information available".
- When emitted, **all three fields are REQUIRED**. Producers **MUST NOT** emit
  a partial `tail_summary`.
- `tail_template_count` **MUST** equal `stats.tail_unique`. The duplication
  is intentional: it allows the `tail_summary` block to be carried, cached,
  or transmitted independently of the parent `stats` object without losing
  context.
- `tail_entropy_bits` **MUST** be computed over the row-normalised tail
  distribution `p_i = count_i / tail_count`. A tail of one template yields
  0.0 (Dirac); a uniform tail of `tail_template_count = n` yields `log2(n)`.
- `tail_max_rate` **MUST** be in `[0.0, 1.0]` and **MUST** equal
  `max(count_i) / lines_observed` across all tail templates, or 0.0 when
  `tail_count = 0`.
- Producers **MAY** emit `tail_summary` even when `tail_count = 0`; in that
  case `tail_template_count = 0`, `tail_entropy_bits = 0.0`, and
  `tail_max_rate = 0.0`.

#### 3.6.1 Why a summary instead of a longer `top_k`?

Doubling `top_k` from 64 to 128 adds 64 entries — roughly **9 KB** per
window in id-only mode and **13–14 KB** inline, at §11.2's measured
per-entry costs. `tail_summary` provides three of the four signals that
matter most for downstream detection — *how many* templates are in the tail
(`tail_template_count`), *how spread* they are (`tail_entropy_bits`), and
*how loud* the loudest one is (`tail_max_rate`) — for an envelope cost of
~60 bytes. This preserves the headline 4 KB / 1 M-lines target ([§11](#11-size-budget))
while letting consumers detect tail-mass shifts (e.g. error-burst templates
that never quite reach `top_k` but collectively grow), which the current
`tail_count` / `tail_unique` pair cannot expose.

#### 3.6.2 Compatibility with composition (§12)

A composer **SHOULD** recompute `tail_summary` from the merged document's
tail rather than averaging inputs. When inputs do not provide
`tail_summary`, the composer **MAY** omit it from the composed document
(consumers must already handle absence). The block is intentionally
designed to survive lossy composition: all three fields are computable from
the post-composition `stats` regardless of input attribution.

### 3.7 `reservoir` — salient entries retained beyond `top_k` (optional)

`top_k` retains by **frequency**; `tail_summary` (§3.6) captures only the
*aggregate* shape of everything below it. Neither preserves a **rare-but-important
single** template — a lone fatal, an off-path branch — which is exactly the event
a fingerprint must not lose. The optional `stats.reservoir` is a **bounded** set
of such entries, retained by **intrinsic salience, not frequency**.

#### 3.7.1 Entry shape

| field | type | meaning |
|---|---|---|
| `template_id` | string | as in `top_k` (§3.2). |
| `count` | uint | occurrences in the window. |
| `frequency` | number | `count / lines_observed` (§3.3 precision). |
| `template` | string, optional | omitted in dedup / id-only modes (§3.4). |
| `level` | string, optional | severity level when known. |
| `component` | string, optional | dominant functional source (§3.8); omitted when the format carried none. |
| `structural_role` | string, optional | announced role (e.g. `terminator`); omitted when none. |
| `structural_surprise` | uint `0..100` | deviation of the template's most-likely incoming transition from the `dominant_path` (§4.1); `0` = on the expected flow. |
| `novelty` | uint `0..100` | how late the template first appeared within the window (first-seen position over `lines_observed`); `0` = present from the start. The `retention_profile` MAY weight/cap it softer than severity/structure. |
| `salience` | uint | the deterministic admission/ranking score (§3.7.2). |
| `within_window_ordinal` | uint, optional | reconciled first-seen ordinal; the per-entry re-derivation sub-coordinate (§15.4). |
| `cube_coord` | object, optional | the entry's **LOCATION** in the cube (§16) — the reservoir→cell cross (§16.6). Present only when a `cube` block is emitted. |

A `reservoir` entry **MUST NOT** also appear in `top_k` (the reservoir holds only
templates that did not qualify by frequency).

`cube_coord`, when present, is the **LOCATION-only** (`level` + `where`-path) cube
coordinate the entry occupies — the one-way, read-only bridge that restores the
WHERE of a salient template the (capped) emerging border never surfaced. It carries
**no salience back into the cube** and is a **pure function** of the entry's
`(level, where-path)`. See §16.6 for the firewall invariant.

#### 3.7.2 Salience and admission

`salience` is a **deterministic, integer** score combining intrinsic axes —
severity (from `level` / `structural_role` / content), `structural_surprise`, and
`novelty` — **modulated by rarity**. Rarity is a **modulator, never a gate**: a
benign, contentless template scores `0` and **MUST NOT** be admitted (rarity alone
never promotes a template). Admission is **salience-ranked**, subject to a
**per-class diversity cap** (the reservoir covers *distinct* salient kinds, not
many variants of one), and **bounded** by the configured reservoir size.

A producer that emits `reservoir` **SHOULD** report the cap it applied
in **`stats.reservoir_size`** (uint, optional, added in v0.9.0). The
`retention_profile` identifier gates *comparability*; it is opaque, so
it cannot tell a consumer how many entries the block can reach.
`reservoir_size` is what makes the block's contribution to the
envelope computable (§11.1) and its bound checkable (§8 clause 4).
Absent, the consumer knows only that some cap was applied.

The exact weights, reservoir size, and diversity caps are the producer's
**`retention_profile`** (§9), not fixed by this spec. Their **mechanism** is
normative: salience combines the named axes with rarity-modulation, admission is
salience-ranked + diversity-capped, arithmetic is **integer** with **tie-break by
`template_id`**, and a given input under a given `retention_profile` **MUST** yield
a **bit-identical** reservoir. Two documents are comparable (diff, §13) only under
a **matching** `retention_profile` **and a stable template text** — see §3.7.2.1.

##### 3.7.2.1 The tie-break is content-derived, so comparability is byte-scoped

The tie-break key is `template_id`, which is **SHA-256 over the canonical template
string** (§3.2). It is therefore **content-derived but meaning-blind**: its ordering
is pseudo-random with respect to what a template *means*. Two consequences follow,
and the second is not obvious.

1. **Reproducibility holds, exactly as stated above.** For byte-identical input under
   a matching `retention_profile`, the retained set is bit-identical. This tie-break
   is *why* — an implementation-defined or container-iteration-order tie-break at the
   admit/evict boundary is precisely what this rule exists to forbid.
2. **A semantically neutral edit to template text is NOT reservoir-neutral.** Renaming
   a token that survives masking changes the template string, hence `template_id`,
   hence the order of **equally-ranked** candidates — so a *different* member of a tie
   is retained once the reservoir is full. The change is invisible in every count:
   salience, frequency and level are unchanged, and only *which* tied template
   occupies the last slot moves.

Consumers **MUST NOT** attribute a reservoir-membership difference to a change in
behaviour when the two documents' template texts differ. "Content-preserving" is a
human notion; this spec preserves **bytes**, not meaning, and offers no predicate for
semantic equivalence. A diff (§13) across a rename, a re-word, a version-string change
or any other template-text edit is **outside the comparability domain** — the
reservoir delta it reports is re-selection, not signal. Producers **SHOULD** treat a
template-text change as a re-baseline, in the same way a `retention_profile` change is
one.

> *Informative.* The failure mode this prevents is a quiet one: because the counts
> agree, a reservoir re-selection reads as a small, plausible behavioural delta rather
> than as an incomparable pair. It is the reservoir analogue of the n-gram interleaving
> noise described in §12.3.1.

#### 3.7.3 Relationship to `tail_summary` and composition

`tail_summary` (§3.6) is computed over the **residual after `top_k` ∪
`reservoir`**; a reservoir-promoted template **MUST NOT** be double-counted in the
tail aggregates. Under composition (§12) the reservoir is **carried**: `salience`
is **re-derived** over the merged counts (rarity shifts on merge),
`structural_surprise` / `novelty` are carried as the **max** across inputs, and
entries remain **excluded from the tail**. A composed reservoir is re-derivable
for any template that was salient in **at least one** input; it cannot recover a
template that was pure-tail in every input (the `compose`-lossy-tail limit).

### 3.8 `component` — the dominant functional source of a template (optional)

> **New in v0.8.0.** An optional string on a `top_k` entry (§3) and on a
> `reservoir` entry (§3.7.1). One definition, two carriers — the member means the
> same thing in both.

`component` names the **functional source** — logger, module, unit, subsystem,
build job — that dominates this template's occurrences in the window. It is the
same species as `level`: a low-cardinality categorical label the observed stream
carries about itself, condensed to the one value that dominates.

- A producer **MUST** derive `component` from the observed events, never from its
  own processing state. It answers *where in the emitting system did this
  template come from*, not *what did the producer do with it*.
- `component` **MUST** be **omitted** when the format carried no component. An
  empty string is **forbidden**: an absent location that renders as present is
  worse than a gap a consumer can see.
- When several components emitted the template, the producer **MUST** emit the
  one with the highest occurrence count, and **MUST** break a tie deterministically
  (lexicographic order over the component strings), so the field is replay
  bit-identical (§15.6).
- `component` is a **label, not a key**. Consumers **MUST NOT** treat equality of
  `component` across two documents as evidence that the two windows observed the
  same deployment; naming conventions are producer-side and unversioned.

Where a producer also emits a `cube` (§16), the `where` chain axis is grounded in
the same underlying notion (§16.2). They are not redundant: §16's axis is a
*window-level joint coordinate* whose values are chain prefixes, and this member is
a *per-template scalar label*. A consumer holding only `top_k` has no cube to read.

---

## 4. `behavior` — sequence fingerprint (optional)

Captures *how* templates follow each other, beyond raw frequency.

```jsonc
{
  "ngram_size": 2,                     // integer, required, size of n-grams (2 = bigrams)
  "top_ngrams": [                      // array, required, ordered by count desc
    {
      "sequence": ["h:8a3f...", "h:b104..."],  // array of template_ids
      "count": 8421,
      "probability": 0.677              // p(next | prev) for n=2; joint prob otherwise
    }
  ],
  "top_ngrams_size": 64,                // integer, required
  "dropped_ngram_observations": 1274,   // integer, optional, minimum 1 — OMIT the key entirely when none were dropped (never write 0)
  "graph_edge_count": 312,              // integer, optional, edges in the transition graph
  "dominant_path": [                    // array, optional, the most-traversed path
    "h:8a3f...", "h:b104...", "h:c977..."
  ],
  "branching": [                        // array, optional, per-node fanout & entropy
    {
      "template_id": "h:8a3f...",
      "fanout": 3,                      // distinct outgoing transitions
      "total_outgoing": 9421,           // sum of counts on outgoing edges
      "entropy_bits": 0.918             // H over the row-normalised outgoing distribution
    }
  ]
}
```

**`dropped_ngram_observations` — the accounting bound, distinct from top-k truncation.**
`top_ngrams` is a RANKING cut: every entry it drops was seen, counted and ranked, and the
retained set is the top `top_ngrams_size` of them. A producer MAY additionally bound the
number of distinct n-gram keys it will *account for at all*; past that bound an arriving
key is refused **before it is ever counted**. That is a different and heavier loss — an
n-gram that would have ranked first can be absent purely because it arrived late — so it
is reported rather than inferred, on the same principle as `dropped_edges`.

The field counts **OBSERVATIONS, not distinct keys**, and the noun is normative. How many
distinct keys were refused is **not knowable** without retaining exactly the unbounded set
the bound exists to refuse; the number of observations that fell on refused keys is
knowable, and is what a consumer needs to size the loss.

It is **OMITTED when zero**, so a producer that never hits its bound emits byte-identical
documents to one that has no bound. Absence is disambiguated by `metalog_version`: in a
document declaring **0.7.0 or later**, an absent field means **no observations were
dropped**; in an earlier document it means **unknown**. Consumers **MUST NOT** treat a
missing field in a pre-0.7.0 document as zero.


### 4.1 `dominant_path`

The producer's best estimate of the most-traversed path through the
transition graph. Reconstruction **MUST** be deterministic for a
given window. A common choice is greedy: start at the highest-count
node, follow the highest-count outgoing edge at each step, stop on
sink, cycle, or a producer-defined max length.

Consumers **MUST NOT** assume the path is acyclic, optimal, or
unique — it is a *fingerprint* feature, not a graph algorithm
result.

### 4.2 `branching`

Per-node fanout statistics. Allows consumers to ask "which templates
are decision points?" without retrieving the full transition matrix.

For each node:

- `fanout` is the number of distinct outgoing edges.
- `total_outgoing` is the sum of edge counts leaving the node.
- `entropy_bits` is the Shannon entropy of the row-normalised
  outgoing distribution: `H = -Σ p_i log2(p_i)` where
  `p_i = count_i / total_outgoing`. Higher entropy = harder to
  predict next template = more branchy.

Producers **MUST** compute `branching` over the same observation
window as `top_ngrams` (one is not allowed to span more events than
the other). Producers **SHOULD** emit branching for at least the
nodes that appear in `top_ngrams` and `dominant_path`; emitting it
for *every* node is **NOT REQUIRED** (and may exceed the size
budget).

A producer that caps `branching` **SHOULD** report the cap in
**`behavior.branching_size`** (uint, optional, added in v0.9.0).
`branching` is the one variable-length block this spec places no cap
on: an uncapped producer grows it with the window's distinct node
count. Declaring the cap makes the block's contribution to the
envelope computable (§11.1); **omitting the field means the producer
declares no cap**, which is a legal but unbounded posture, and a
size-constrained consumer should read the omission that way rather
than assume a default.

Producers that cannot compute sequence information (e.g. a streaming
producer with no buffering) **MUST** omit the `behavior` object
entirely rather than emit empty fields.

---

## 5. `stability` — divergence from previous window (optional)

Quantifies *how much the system's behaviour changed* since the
previous window. Stability is a special case of §13 Diff with the
`previous` document being the previous closed window.

```jsonc
{
  "previous_window_end": "2026-04-24T10:00:00Z",  // RFC 3339, required
  "kl_divergence": 0.043,        // number ≥ 0, KL(current || previous) over template freqs
  "js_divergence": 0.021,        // number in [0, 1], symmetric Jensen-Shannon
  "new_templates": 3,            // integer, templates seen now but not in previous window
  "vanished_templates": 1,       // integer, templates in previous but not now
  "stability_score": 0.94        // number in [0, 1], 1.0 = identical, producer-defined formula
}
```

A producer **MAY** include only a subset of these fields. The
`stability_score` is producer-defined; consumers **MUST NOT** assume
two producers compute it the same way and **SHOULD** prefer the
explicit divergences (`kl_divergence`, `js_divergence`) for
cross-vendor comparisons.

For arbitrary pair-wise comparison (not just consecutive windows),
producers and consumers **SHOULD** use a `MetaLogDiff` document
(§13) instead.

---

## 6. `attribution` — sub-source distribution (optional)

When a single MetaLog covers multiple hosts, services, or tenants,
attribution captures *which template fired most for which sub-source*
in compressed form.

```jsonc
{
  "dimension": "host",                  // string, required, e.g. "host" or "service"
  "sketch_type": "count_min",           // string, required: "count_min" | "exact" | "topk_per_dim"
  "sketch_params": {                     // object, required, depends on sketch_type
    "width": 2048,
    "depth": 4,
    "hash_seed": 42
  },
  "encoded": "base64:..."                // string, required, base64 of the sketch payload
}
```

The sketch encoding for each `sketch_type` is reserved for v1.0.
Until then, producers **SHOULD NOT** emit `attribution` in
interoperable MetaLogs.

---

## 7. `extensions` — vendor-specific data

```jsonc
{
  "com.example.foo": { "anything": "here" }
}
```

- Keys **MUST** be reverse-DNS-prefixed to avoid collision.
- Consumers **MUST** ignore unknown extensions.
- Vendors **MUST NOT** put data in `extensions` that *replaces* a
  standard field. If you need a field that doesn't exist in the spec,
  open an issue.

**Placement (new in v0.8.0).** `extensions` is **the only** carrier of
non-standard members. A producer with vendor data **MUST NOT** write it as a bare
member of a standard object, at any depth, including objects the schema does not
currently close.

Vendor data is often **per-row**, and a document-level container cannot carry a
per-row value without inventing a join key. So the container is granted at each
object the spec names, with one grammar shared by all of them —
`$defs/extensions`, defined once per schema file and referenced, never restated
inline. Each of the two schema files carries that definition rather than
cross-referencing the other: both are independently consumable, and a cross-file
`$ref` cannot be resolved offline. The copies are asserted identical by
`conformance/metalog_validate.py --selftest`, so the duplication cannot quietly
become a divergence.

| object | granted |
|---|---|
| the MetaLog document root | v0.1.0 |
| `stats.top_k[]` (MetaLog) | v0.8.0 |
| the `MetaLogDiff` document root (§13) | v0.9.0 |

A producer needing the container at an object not on this list **MUST** open an
issue rather than write a bare member: adding a placement is an *additive* change
under `GOVERNANCE.md` §2 and costs one reviewer. The list is deliberately short
and grows on evidence — a container granted everywhere in advance could never be
withdrawn, because removing one is a *breaking* change.

**What detects a bare member, and what does not.** Inside a **closed** object the
schema rejects it, and §8 clause 1 reports it. At either **document root** it does
not: both roots are `additionalProperties: true`, so a bare vendor member there
validates, and the MUST above is the only thing forbidding it. That is a property
of the schema, not a softening of the rule. The gap is not silent either —
`conformance/metalog_validate.py` reports such a member as
**legal-but-undescribed**, which is a report and not a verdict. Closing a root
would make the rule decidable there; it is a *breaking* change under
`GOVERNANCE.md` §2, and granting a placement neither performs it nor waits on it.

Granting the container **does not** re-open the object. A misspelled standard
member is still a violation, because it is not inside `extensions` — which is the
whole reason the extension point is a named container and not a key prefix.

---

## 8. Conformance

A producer is **conformant** with this spec at version *X.Y.Z* if:

1. Every MetaLog it emits validates against
   [`schema/metalog.v0.schema.json`](schema/metalog.v0.schema.json)
   for that version's MAJOR.
2. Every required field is populated according to its definition
   above.
3. `template_id` values are computed exactly as specified in §3.2.
4. Every array is truthfully bounded by the cap the **same document**
   declares for it: `stats.top_k` by `stats.top_k_size` (required),
   and — where the producer declares them — `stats.reservoir` by
   `stats.reservoir_size`, `behavior.top_ngrams` by
   `behavior.top_ngrams_size`, `behavior.branching` by
   `behavior.branching_size`, `cube.cells` by `cube.cell_budget`.
   A cap a producer does **not** declare is not a claim, and its
   absence is not a violation.

A consumer is conformant if it accepts any document that validates
against the schema, ignoring unknown fields and unknown extensions,
and resolves template strings according to §3.4.

There is no central conformance authority. **The schema is the test
for clause 1.** Clause 4 is not reachable from the schema — JSON
Schema's `maxItems` takes a constant, while the bound here is the
value of a sibling field — but it *is* decidable from the document
alone, and [`conformance/metalog_validate.py`](conformance/metalog_validate.py)
decides it. Clauses 2 and 3 are not mechanically decidable today:
clause 2 only as far as the schema expresses it, and clause 3 not
until a pinned cross-implementation digest vector exists.

---

## 9. Versioning

This spec follows SemVer:

- **MAJOR** changes break the schema (e.g. removing a required
  field, changing a field's type).
- **MINOR** changes add optional fields or extend enum values.
  *Pre-1.0 caveat:* during the 0.x line, MINOR bumps **MAY**
  introduce incompatible changes (this is what 0.2.0 does relative
  to 0.1.x — `template` moved from required to optional in `top_k`
  entries).
- **PATCH** changes are clarifications and typo fixes.

Producers and consumers **MUST** check `metalog_version`'s MAJOR
component and **MAY** refuse to process documents with an unknown
MAJOR.

**Processing identifiers (separate axis).** Distinct from the spec version,
`canonicalization_version` and `retention_profile` (§2.4) identify the
*producer-side processing contract* under which a document was generated. They
evolve independently of `metalog_version`. `compose()` (§12) and `MetaLogDiff`
(§13) **MUST** enforce equality of these identifiers across inputs that carry
them; see §2.4 for the comparability gate.

---

## 10. Security considerations

- A MetaLog is **derived from logs** and **MAY** contain fragments
  of sensitive data leaked into template skeletons (e.g. an
  email address that ended up in the invariant part of a template).
  Producers **SHOULD** apply redaction policies before computing
  templates. Operating in id-only mode (§3.4) mitigates leakage at
  the wire but does not eliminate it (the resolver still holds the
  strings).
- A MetaLog's `template` strings reveal what software is running.
  This is **less sensitive** than raw logs but **not zero**.
  Consumers **SHOULD** treat MetaLogs with the same access controls
  as service-level metrics.
- Sketches in `attribution` are probabilistic and **MUST NOT** be
  treated as authoritative for security decisions.

---

## 11. Size budget

This section is **informative**. It gives an implementer a way to
**compute** the envelope a MetaLog can reach, rather than a number to
trust. The distinction matters: the parameters below are the
producer's, not this spec's, so any single figure published here would
be a figure for one producer's configuration and would silently rot
the first time that configuration moved.

### 11.1 What is bounded, and by what

§3.1's guarantee is about **input cardinality**: however many distinct
templates a window contains, `stats` retains `top_k_size` of them and
summarises the rest into `tail_count` / `tail_unique`. That guarantee
is exact, and its subject is `stats`.

A document's *size* is a different quantity: the sum over **every**
variable-length block it carries. Each such block is capped by a
parameter the producer fixes before window start, so the whole
document is bounded — but by a **set** of parameters, not by `k` alone:

| Block | Bounded by | Declared in the document as |
|---|---|---|
| `stats.top_k` | top-k size | `stats.top_k_size` (required) |
| `stats.reservoir` (§3.7) | reservoir size | `stats.reservoir_size` |
| `stats.top_k[].param_histograms` (§3.5) | per-template histogram cap, and the `value_counts` cap within each | *not declared* — see §11.5 |
| `behavior.top_ngrams` (§4) | n-gram retention size | `behavior.top_ngrams_size` (required when `behavior` is present) |
| `behavior.branching` (§4.2) | branching size | `behavior.branching_size` |
| `cube.cells` (§16) | the closed-cell budget of §16.10 | `cube.cell_budget` |

`retention_profile` (§2.4) is **not** a substitute for these fields. It
is an opaque identifier and it answers *"were these two documents
produced under the same regime?"* — a comparability question. It
cannot answer *"how large can a document from this producer get?"*,
because a consumer cannot read a size out of an opaque string. The two
jobs are separate and both are needed.

### 11.2 Per-entry cost

Measured on [`schema/metalog.v0.example.json`](schema/metalog.v0.example.json),
JSON-encoded with no whitespace. That document is in **id-only** mode
(§3.4): template strings live in the top-level `templates` dedup map,
so the entry costs below exclude them. **Inline mode adds the skeleton
string — typically 50–100 bytes — to every `top_k` and `reservoir`
entry.**

| Entry | Measured bytes (id-only) | Notes |
|---|---|---|
| `top_k` entry | **99–177** | 99 with `level` only; 122 with `component`; 177 with a per-row `extensions` object |
| `reservoir` entry | **165–296** | 165 for the required fields alone; 235 with `level`/`component`/`structural_role`; **296** with §16.6's `cube_coord` cross |
| `top_ngrams` entry | **~121** | at `ngram_size` 2; each additional gram adds one `template_id` (~40) |
| `branching` entry | **~107** | |
| `cube` cell | **27–99** | grows with the number of pinned axes in `coord` and with WHERE-chain depth |
| Fixed envelope | **~460** | `metalog_version`, `producer`, `window`, `source`, and the optional blocks' framing |
| `templates` dedup map | **~370** for 4 entries | id-only mode only; ~90 per distinct template |

A `reservoir` entry costs roughly **1.5× to 2.5×** a `top_k` entry: it
carries the salience axes (`salience`, `structural_surprise`,
`novelty`, `within_window_ordinal`) that justify its admission, and
optionally the `cube_coord` cross. Pricing the reservoir at the
`top_k` rate under-counts it.

### 11.3 The envelope, as a formula

```
envelope  ≈  fixed_envelope
           + top_k_size        × cost(top_k entry)
           + reservoir_size    × cost(reservoir entry)
           + top_ngrams_size   × cost(n-gram entry)
           + branching_size    × cost(branching entry)
           + cell_budget       × cost(cube cell)
           + templates_map                       (id-only mode)
           + param_histograms                    (§11.5)
```

Every term is a **declared cap × a measured per-entry cost**, and each
cap is either required in the document or optional-and-declarable
(§11.1). A consumer that wants a bound for a specific producer reads
the caps out of one of that producer's documents and applies its own
measured costs; it never has to trust a table.

### 11.4 Worked examples

Three configurations, in id-only mode with the `templates` map shared
across documents (§3.4), using the midpoints of §11.2:

| Configuration | Caps | Approx envelope |
|---|---|---|
| **Edge** — `stats` only | `top_k_size` 16, no reservoir, no `behavior`, no `cube` | **~2.7 KB** |
| **Default** — `stats` + `behavior` | `top_k_size` 64, `top_ngrams_size` 64, `branching_size` 64 | **~23 KB** |
| **Wide service** — all blocks | `top_k_size` 128, `reservoir_size` 64, `top_ngrams_size` 64, `branching_size` 64, `cell_budget` 4096 | **~298 KB**, of which **~252 KB is the cube** |

An unshared `templates` map adds roughly 90 bytes per distinct
template on top (~1.4 KB, ~5.8 KB and ~17 KB respectively).

**These are ceilings, not typical sizes.** Every cap is an upper
bound: a window containing fewer distinct templates than `top_k_size`
emits fewer entries, and a producer that omits `behavior` or `cube`
drops those terms entirely. The formula answers *"how large can this
get?"*; only `extensions.org.metalog.envelope_bytes` (§11.5)
answers *"how large was it?"*.

The third row is the one worth reading twice. The cube's closed-cell
budget dominates every other term combined, and a producer that
enables §16 without pricing that budget will be surprised by an
envelope one to two orders of magnitude above the `stats`-only figure
it started from. §16.10's budget is a **static producer constant**
precisely so that this number is knowable in advance; declaring it in
`cube.cell_budget` is what makes it knowable to the *consumer*.

Conversely: the `stats`-only envelope really is small — ~9 KB at
`top_k_size` 64 — and adding `behavior` multiplies it by roughly 2.5.
Both facts are recoverable from the formula; neither is recoverable
from a table indexed on `k`.

### 11.5 Reaching the 4 KB / 1M-lines target

The headline "≤ 4 KB per MetaLog covering ≥ 1 M log lines" target is a
statement about the **`stats`-only** document — no `reservoir`, no
`behavior`, no `cube`. Under that scope it is reached at:

1. `top_k_size ≤ 32` in inline mode, **or**
2. `top_k_size ≤ 64` in id-only mode (§3.4) with template strings
   shipped out-of-band or via a `templates` dedup map shared across
   many MetaLogs.

Real log streams follow a Zipfian distribution: the top 64 templates
typically account for 95–99% of all observations, which is why the
target is reachable at all.

**Two residuals, stated rather than hidden.** `param_histograms`
(§3.5) is bounded by two producer parameters — a per-template
histogram cap and the `value_counts` cap (§3.5 recommends a default of
256) — and **neither is declared in the document today**. And the
per-entry costs above are *this* document's; a producer whose
templates, components or extension payloads are larger will measure
larger costs. For both reasons producers **SHOULD** report their
actual envelope size in
`extensions.org.metalog.envelope_bytes` (or equivalent), which is the
only figure that is exact rather than estimated.

---

## 12. Composition (associative merge)

Two MetaLogs covering disjoint or overlapping windows of the same
source **MAY** be combined into a single MetaLog via the `compose`
operation. This enables sharded ingestion (per-host MetaLogs merged
to a fleet MetaLog) and time-axis rollup (1-minute MetaLogs merged
to a 1-hour MetaLog).

### 12.1 Definition

`compose(A, B) -> C` produces a MetaLog `C` such that:

- `C.window.start = min(A.window.start, B.window.start)`
- `C.window.end   = max(A.window.end,   B.window.end)`
- `C.window.duration_seconds = C.window.end - C.window.start` (real time, **not** sum of inputs)
- `C.window.lines_observed = A.window.lines_observed + B.window.lines_observed`
- `C.source` is `A.source` if equal to `B.source`, otherwise the
  most-specific common prefix (e.g. same `fleet`, drop differing
  `service`); empty if no common prefix.
- `C.stats.top_k` is recomputed from the union of per-template
  counts (sum across `A.stats.top_k`, `B.stats.top_k`, and best-effort
  attribution of tail mass), then truncated to `top_k_size`.
- `C.stats.tail_count` is `A.tail_count + B.tail_count` plus any
  templates that fell out of the new top-K.
- `C.stats.tail_unique` and `C.stats.unique_templates` are
  recomputed from the union.
- `C.stats.entropy_bits` is recomputed from the merged counts.
- `C.behavior.top_ngrams` is recomputed from the union of per-key
  counts and re-truncated to `top_ngrams_size`.
- `C.behavior.dropped_ngram_observations` is the SUM of both inputs'
  values (absent counts as zero); it is omitted when that sum is zero.
- `C.behavior.graph_edge_count` is the union edge count.
- `C.behavior.branching` is recomputed from the merged graph.
- `C.behavior.dominant_path` is re-derived greedily from the merged
  graph; consumers **MUST NOT** assume it equals the path of either
  input.
- `C.stability` **MUST** be omitted (it is meaningless across
  composed inputs); consumers wanting a current-vs-prior view of a
  composed document should use §13 Diff explicitly.
- `C.canonicalization_version` is `A.canonicalization_version` if equal to
  `B.canonicalization_version`. When the values **differ**, `compose()` **MUST**
  fail (the inputs were produced under incompatible canon contracts; merging
  them yields a fingerprint addressable to no consistent contract). When **one**
  or **both** inputs omit the identifier, the composer **MAY** proceed but
  **MUST NOT** synthesize a value (omit it in `C`). The same rule applies to
  `C.retention_profile`.
- `C.stats.reservoir` is **carried** through composition: salience is **re-
  derived** over the merged per-template counts (rarity shifts on merge),
  `structural_surprise` and `novelty` are carried as the **max** across inputs,
  and carried entries remain **excluded** from the tail (§3.7.3). The composed
  reservoir is therefore present at every pyramid scale.
- `C.stats.top_k[*].param_histograms` are **carried** through composition. For
  each `(template_id, param_index)` pair present in **both** inputs'
  histograms, the composer **MUST** merge: union the `value_counts` keys, sum
  the counts, truncate to the producer's `max_param_histograms` cap (keeping
  the top-N by count); set `total = A.total + B.total`; recompute
  `entropy_bits` over the (possibly-truncated) merged `value_counts`;
  `approximate_cardinality` **MAY** be merged via a sketch union when the
  producer supports it (§3.5.1), otherwise set to `max(A.cardinality,
  B.cardinality)` as a conservative lower-bound estimate. When a histogram is
  present in only **one** input (the other had the template in its tail, or
  omitted the histogram), the composer **MAY** carry it unchanged — in which
  case `total` reflects only that input's contribution — or **MAY** omit it.
  This makes per-slot value-distribution shifts visible in `MetaLogDiff`
  against composed baselines (status-code regimes, latency-bucket shifts, etc.)
  that previously vanished at composed scales.
- `C.cube` (§16) is **re-closed**, not merged cell-by-cell. The distributive
  **counts** compose by addition (SIMD-friendly), but the **closure does not
  distribute** (e.g. `auth:500 ∪ auth:200` makes `(auth, *)` emerge — closed in
  neither input). The composer **MUST** therefore expand both cubes to full counts,
  add, and **re-close**; recompute is the deterministic default (incremental closure
  is arrival-order-sensitive and **MUST NOT** feed deterministic content). Both
  inputs' `cube.axes` **MUST** be equal. The **compose cube** draws its WHERE
  coordinate from each input's **`source`** block (service / fleet / region — the
  cross-document organ), distinct from the intra-window cube's `component`-chain
  (§16.7). When either input omits `cube`, `C.cube` **MAY** be omitted.
- `C.templates` is the union of `A.templates` and `B.templates`
  (both keyed by `template_id`; values are byte-equal by §3.2 so
  conflicts cannot arise).
- `C.provenance` is `A.provenance ∪ B.provenance ∪ [{window: A.window, source: A.source, lines_observed: A.window.lines_observed, document_id: <id of A if known>}, {window: B.window, source: B.source, ...}]`.

### 12.2 Algebraic properties

- **Associativity (best-effort):** `compose(compose(A, B), C)` and
  `compose(A, compose(B, C))` **SHOULD** produce documents whose
  required fields agree exactly. Behavior fields (`dominant_path`,
  `branching`, `top_ngrams` ordering) **MAY** differ in tie-breaking;
  the underlying counts **MUST** agree.
- **Commutativity:** `compose(A, B)` and `compose(B, A)` **MUST**
  agree on all required fields.
- **Identity:** `compose(A, ZERO)` **MUST** equal `A`, where `ZERO`
  is a MetaLog with `lines_observed = 0` and empty stats.

### 12.3 Lossy aggregation

Composition is **inherently lossy** when either input had a
non-empty tail: the per-template counts of templates that fell into
either input's tail are unknown. Composers **MAY** under-attribute
those counts to the merged tail. The total `lines_observed` across
the merged document **MUST** still equal `A.lines_observed +
B.lines_observed` (no lines are invented or lost), even if the
top-K coverage drops slightly.

#### 12.3.1 Multi-source n-gram noise (informative)

When a composed document covers **multiple sub-sources** (e.g. several
service instances merged into a fleet view) the `behavior.top_ngrams`
field carries an additional, **structural** source of noise that consumers
**MUST** account for. Per-source event streams interleave during
composition in an order that depends on per-event timestamps and tie-break
rules; small differences in interleaving order can swap which template
follows which, even when the per-source behaviour is unchanged. This
manifests downstream as:

- *Dominant-path swaps*: the greedy path reconstruction (§4.1) can flip
  between two near-equal candidates window-to-window, producing a stream of
  "the dominant path changed" signals that reflect interleaving rather than
  service behaviour.
- *N-gram churn*: bigrams `(A, B)` and `(A, B')` can both have appreciable
  mass and trade ranking each composition, leading to "new n-gram" /
  "vanished n-gram" reports against a stable underlying workload.

Consumers operating on composed MetaLogs **SHOULD** treat the standalone
confidence of n-gram-derived signals (BranchingShift, NoveltyNGram,
VanishedTemplate when scoped to an n-gram pair) as **inherently bounded
below the level required for an isolated alert** and **SHOULD** surface
those signals only as supporting evidence for incidents that other
detectors (Drift, FieldDrift, VolumeAnomaly, Composite cross-scale
agreement) also raise. This is a *structural* limitation of multi-source
composition, not a producer defect.

### 12.4 `provenance` block

When emitted, `provenance` is an array of objects:

```jsonc
[
  {
    "window":  { "start": "...", "end": "..." },
    "source":  { "service": "checkout-api", "host": "checkout-3" },
    "lines_observed": 91204,
    "document_id": "sha256:..."   // optional, content hash of the composed input
  }
]
```

Consumers **MAY** use `provenance` to reconstruct the breakdown of
a composed document. Producers **MUST NOT** put sensitive
identifiers in `provenance`.

---

## 13. `MetaLogDiff` — pair-wise difference document

A `MetaLogDiff` is a **separate JSON document type** (not a block
inside a MetaLog) that describes the difference between two
MetaLogs. It generalises the `stability` block (§5) to arbitrary
pairs (not just consecutive windows).

A producer **MUST** enforce the §2.4 comparability gate on the two inputs: when
both carry `canonicalization_version`, the values **MUST** be equal; when both
carry `retention_profile`, the values **MUST** be equal. Diffing across
mismatched processing identifiers **MUST** fail or be signalled as
incompatible — the templates and salience scores under different contracts are
not directly comparable.

### 13.1 Document structure

```jsonc
{
  "diff_version": "0.4.0",
  "current":  { "window": { "start": "...", "end": "..." }, "document_id": "sha256:..." },
  "previous": { "window": { "start": "...", "end": "..." }, "document_id": "sha256:..." },
  "kl_divergence": 0.043,
  "js_divergence": 0.021,
  "stability_score": 0.94,
  "template_deltas": [
    { "template_id": "h:8a3f...", "previous_count": 12000, "current_count": 12453, "delta": 453, "previous_frequency": 0.0651, "current_frequency": 0.0676 }
  ],
  "new_templates":      [ "h:9aa..." ],
  "vanished_templates": [ "h:1bb..." ],
  "branching_delta": [
    { "template_id": "h:8a3f...", "previous_entropy_bits": 0.91, "current_entropy_bits": 1.42, "delta_bits": 0.51 }
  ],
  "ngram_delta": {
    "ngram_size": 2,
    "new_ngrams":      [ ["h:9aa...", "h:8a3f..."] ],
    "vanished_ngrams": [ ["h:1bb...", "h:8a3f..."] ],
    "rate_changed": [
      { "sequence": ["h:8a3f...", "h:b104..."], "previous_probability": 0.677, "current_probability": 0.412, "delta": -0.265 }
    ]
  },
  "field_histogram_deltas": [          // array, optional — see §3.5.2
    {
      "template_id":           "h:8a3f...",
      "param_index":           0,
      "js_divergence":         0.31,
      "previous_entropy_bits": 0.28,
      "current_entropy_bits":  0.47,
      "previous_cardinality":  1847,
      "current_cardinality":   183204,
      "cardinality_delta":     181357
    }
  ],
  "tail_delta": {                      // object, optional — see §13.5 (new in v0.4.0)
    "previous_tail_template_count": 40, "current_tail_template_count": 38, "tail_template_count_delta": -2,
    "previous_tail_entropy_bits": 4.0,  "current_tail_entropy_bits": 1.0,  "tail_entropy_bits_delta": -3.0,
    "previous_tail_max_rate": 0.001,    "current_tail_max_rate": 0.02,     "tail_max_rate_delta": 0.019
  },
  "extensions": {                      // object, optional — vendor data, §7 (placement granted in v0.9.0)
    "com.example.deploy_window": "2026-01-14.3"
  }
}
```

### 13.2 Required vs optional fields

- `diff_version`, `current`, `previous` are **REQUIRED**.
- All other fields are **OPTIONAL** but at least one of
  `kl_divergence`, `js_divergence`, `template_deltas`,
  `new_templates`, `vanished_templates`, `branching_delta`,
  `ngram_delta`, or `tail_delta` **MUST** be present (an empty diff
  is a no-op document and should not be emitted).
- `template_deltas` **SHOULD** be capped at the larger of the two
  inputs' `top_k_size`. Producers **MAY** report the cap in
  `extensions.org.metalog.deltas_truncated_at` — the §7 container is
  granted at this root from **v0.9.0**, which is the release that gave
  this MAY a placement to name.

### 13.3 Direction and sign

- `previous` is the **earlier** document; `current` is the **later**
  document.
- `delta = current - previous`. Positive = grew; negative = shrank.
- `kl_divergence = KL(current || previous)`.
- `js_divergence` is symmetric in the inputs but the **role** of
  `current` and `previous` is fixed by the document fields above.

### 13.4 Use cases

- **Change detection:** a Phase-4 detector ingests a stream of
  MetaLogs and emits a `MetaLogDiff` whenever the divergence
  exceeds a threshold.
- **Cross-region comparison:** diff two regional fleet MetaLogs to
  spot region-specific behaviour (here `previous` and `current` are
  semantically two snapshots, not in time order).
- **Pre/post deploy:** diff the MetaLogs of the 5 minutes before
  and 5 minutes after a deploy.

### 13.5 `tail_delta` — long-tail shape change (new in v0.4.0)

`tail_delta` is the pair-wise difference of the two documents'
`stats.tail_summary` blocks (§3.6). It generalises the tail-shape
signal to arbitrary pairs the same way the rest of the diff
generalises `stability` (§5).

- A producer **MUST** emit `tail_delta` only when **both** input
  documents carry a `stats.tail_summary`. A one-sided tail is a tail
  *appearing* or *vanishing*, which is already expressed by the
  template-level `new_templates` / `vanished_templates` signals.
- Each of the three `tail_summary` fields is reported as a
  `previous_` / `current_` pair plus a `*_delta` (`= current −
  previous`), so consumers need not re-derive it.
- **Interpretation.** A *negative* `tail_entropy_bits_delta`
  (tail concentrating toward one template) combined with a
  *positive* `tail_max_rate_delta` (the loudest tail template
  growing) is the signature of a single chronic error emerging
  inside the long tail **without breaching `top_k`** — a class of
  change invisible to `template_deltas` alone. This is the pair-wise
  analogue of the streaming tail-shift detector described in
  consumer implementations; the diff field is stateless and carries
  no baseline.
- `tail_delta` **MUST NOT** be treated as an alert on its own; it is
  structured evidence. Consumers decide significance.

### 13.6 `cube_diff` — emerging border (new in v0.6.0, EXPERIMENTAL)

`cube_diff` is the pair-wise difference of the two documents' `cube` blocks (§16):
the **emerging border** — the smallest constraint characterising *what grew* between
`previous` and `current`. The emerging region (`count_previous ≤ θ_was ∧
count_current ≥ θ_now`, the two absolute thresholds of §16.5 **MUST-2**) is
**order-convex**, bounded by a **(lower, upper) border pair**:

- `lower` — the most-**specific** emerging cells (the precise description, e.g.
  `(db, timeout, error)`).
- `upper` — the most-**general** emerging cells = the **minimal generators** = the
  deterministic **headline** (e.g. `{ "where": ["db"] }` — "the smallest condition
  that characterises everything that emerged").

`vanishing` is the dual (`count_previous ≥ θ_was ∧ count_current ≤ θ_now` —
disappearance). Each border cell carries `coord` + `previous_count` +
`current_count`.

```jsonc
"cube_diff": {
  "axes": [ /* MUST equal both inputs' cube axes */ ],
  "emerging": {
    "lower": [ { "coord": { "level": "ERROR", "where": ["db", "pool"] }, "previous_count": 0, "current_count": 53 } ],
    "upper": [ { "coord": { "where": ["db"] },                            "previous_count": 0, "current_count": 57 } ]
  },
  "vanishing": { "lower": [], "upper": [] }
}
```

- A `cube_diff` **MUST** be emitted only when **both** inputs carried a `cube` **and**
  their `axes` are equal (the §2.4 comparability gate plus an equal cube schema).
- Emergence **MUST** be defined by the two absolute thresholds, **never** a growth
  ratio (§16.5 MUST-2); the WHERE chain **MUST** be a single-parent tree (§16.5
  MUST-1). Either violated ⇒ the border is ill-defined.
- The `upper` border is the deterministic headline — *computed, not narrated*. An
  LLM narrator (if any) narrates a result already decided (§16.1).
- `cube_diff` **MUST NOT** be treated as an alert on its own; it is structured
  evidence. Consumers decide significance.

---

## 14. Sessions

*Reserved — removed in 0.5.0.* This section number formerly specified
per-session n-grams (`behavior.session_aware` / `sessions_observed`). It was
removed as a premature, unsourced specialization. Session-awareness is deferred
to correlation-keyed processing over a standard `trace_id` (a `CORRELATION_ID`
class); n-grams remain computed over the global event stream until then. The
number is retained as a tombstone to keep cross-references stable. See
[`CHANGELOG.md`](CHANGELOG.md).

---

## 15. Re-derivation coordinate (optional)

A MetaLog document is a **lossy** fingerprint: canonicalization, top-k/reservoir
compression, and `compose()` discard the raw bytes. The **re-derivation
coordinate** makes any window **addressable back to its source**, so ground truth
is recoverable on demand — `raw(window) = replay(source, bounds)` — with no raw
buffering, and every finding **citable and verifiable**.

### 15.1 Two guarantees

A coordinate provides one or both of:

1. **Raw recovery** (mandatory when a coordinate is present): `source_ref` +
   event-time `bounds` recover the window's raw bytes. **Independent of the
   canonicalization version** — it addresses bytes upstream of canon.
2. **Fingerprint reproduction** (optional): additionally
   `canonicalization_version` + `config_hash` re-derive the *same fingerprint*
   (canon output depends on canon code + config, not just raw bytes).

### 15.2 Fields

A `coordinate` describes either a **raw** window (a single addressable source)
or a **composed** window (the set of its raw children's coordinates, §15.5).
**Exactly one** of the two field groups below **MUST** be present in a given
coordinate; a producer **MUST NOT** emit both and **MUST NOT** emit neither.
Consumers discriminate by the presence of `children`.

**Raw coordinate** — addresses a single source:

- `source_ref` — `{ resolver_kind: string, handle: string }`. An **opaque,
  resolvable** handle plus a tag selecting the resolver. The handle's meaning is
  defined by the environment, **not** this spec (e.g. a deterministic-replay
  source key, an immutable artifact URI, or an `otel_trace` reference). A
  producer **MUST NOT** assume a particular resolver.
- `bounds` — `{ start_tick: uint64, end_tick: uint64 }`. **Event-time** integer
  ticks; the window is `[start_tick, end_tick)`. Ticks **MUST** be integers (no
  float) and **MUST** be bit-identical across replays.

**Composed coordinate** — addresses a `compose()` output:

- `children` — a non-empty array of `coordinate` objects, each addressing a raw
  (or recursively composed) child of the composition. A composed coordinate
  **MUST NOT** carry `source_ref` or `bounds`: it has no single source, and a
  coarse `[start, end]` standing in for the children would over-claim across
  gaps, shards, or sources (§15.5).

A coordinate of either kind **MAY** additionally contain:

- `canonicalization_version` — string; required for guarantee (2). The semantic
  canonicalization-rules version, **not** a binary build id.
- `config_hash` — string; hash of the effective canon+metalog config, for
  guarantee (2).

> **Encoding note (non-normative).** Earlier drafts of `0.5.0` required
> `source_ref`/`bounds` on every coordinate and forced composed coordinates to
> emit sentinel values (e.g. `source_ref={"composed",""}`, `bounds={0,0}`) as a
> "see children" marker. That workaround is **no longer permitted**: the two
> field groups are mutually exclusive, and sentinel values **MUST NOT** be
> emitted on composed coordinates.

### 15.3 Event-time bounds — normative

Window membership **MUST** be determined **solely** by event-time
∈ `[start_tick, end_tick)`. It **MUST NOT** depend on the global sequence
counter (non-deterministic across replays — the transport race carve-out) or on
replay depth. Two conformance forms by resolver class:

- **Replay resolvers MUST be prefix-monotone in the target:**
  `replay(source, [start, T_mid])` **MUST** equal the event-time prefix of
  `replay(source, [start, T])` for every `T_mid ≤ T`.
- **Fetch resolvers** (immutable source) **MUST** yield **deterministic
  event-time selection:** the set of events with event-time ∈ `[start, end)` over
  the fetched bytes **MUST** be stable across fetches.

*Conformance evidence (replay).* Verified on a deterministic-replay source: two
replays to a target are byte-identical (1502 lines), and a replay to an earlier
target is the exact event-time prefix of the later one (752-line prefix at the
mid target) — bounds are replay-depth-independent. Producers **SHOULD** keep such
a replay round-trip as a standing conformance fixture.

### 15.4 Granularity

- A **window-level** coordinate is the unit of addressability.
- A **per-reservoir-entry** sub-coordinate (`within_window_ordinal`, the
  reconciled first-seen ordinal within the window) is **OPTIONAL** and bounded by
  the reservoir size. It is a **guarantee-(2)** aid: a reservoir entry is a canon
  artifact, so locating it requires re-deriving raw (1) then re-canonicalizing
  (2). A producer **MUST NOT** emit a per-line coordinate (unbounded).

### 15.5 Composition

A composed document's coordinate **MUST** be the **set of its raw children's
coordinates** (carried alongside `provenance`, §12.4), **never** a single coarse
`[first, last]` range (which over-claims across gaps, shards, or sources). A
composed coordinate therefore always resolves to **raw children**, never to a
composed intermediate.

### 15.6 Determinism, security, and the bounding gate

- Coordinate values are part of the deterministic document — bit-identical across
  replays. They are **descriptive metadata** and **MUST NOT** feed any
  deterministic-content computation.
- Raw recovered via a coordinate **MUST** re-enter the normal canonicalization /
  bounding path before exposure to a downstream consumer — recovery yields a
  bounded re-derived artifact, not a raw dump.
- Resolvability is bounded by **source retention**: a coordinate is a pointer;
  this spec does not guarantee the source outlives the document.

---

## 16. `cube` — intra-window joint categorical condensation (optional, EXPERIMENTAL)

> **Status: EXPERIMENTAL (added in v0.6.0).** The `cube` block is **provisional**.
> It is **additive** — it does not replace or reshape any existing field — and a
> future 0.x release **MAY remove it** in a single revert (§16.8). Consumers **MUST**
> treat its absence as "no joint-categorical information available" and **MUST NOT**
> make it required. It is gated for comparability by **both**
> `canonicalization_version` and `retention_profile` (§2.4).

A MetaLog's 1-D fields carry **marginals** (`level` per template, etc.). A marginal
loses the **joint**: it records "5 timeouts" and "5 events on db" but not "the 5
timeouts *are* on db". The `cube` is a **closed** joint over a small, fixed set of
low-cardinality categorical **axes** — retained losslessly where the data correlates
(the closure collapses redundant cells) and diffed by an **emerging border**
(§13.6). It is an **attributor / projector**, *not* a detector: given events already
marked interesting **elsewhere** (a threshold, a reservoir, a frequency-shift), it
answers "*what is the smallest conjunction of conditions that characterises them*" —
it does **not** decide what is interesting.

### 16.1 Block shape

```jsonc
"cube": {
  "axes": [ /* ordered axis descriptors — §16.2 */ ],
  "cells": [ /* closed cells — §16.4 */ ],
  "cell_count": 5,          // number of closed cells emitted
  "raw_cell_count": 142,    // raw (pre-closure) populated-cell count; collapse rate = cell_count / raw_cell_count
  "cell_budget": 4096,      // optional — the producer's static closed-cell budget (§16.10)
  "floor_saturation": 0.18  // optional WHERE-floor health metric — §16.3
}
```

### 16.2 Axes — fixed, small, frozen, axis-generic

The axis set is **fixed in config, small, chosen once per measure, and frozen** — it
**MUST NOT** be adapted per window (per-window dimension selection destroys
cross-window comparability and is blind to the low-variance dimension that *flips*,
which is exactly the incident). Each axis is one of two kinds:

| `kind` | meaning | value in a cell coord |
|---|---|---|
| `categorical` | a flat low-cardinality category | a string |
| `chain` | a single-parent roll-up hierarchy (§16.3) | an ordered prefix-path (array of strings) |

An axis descriptor additionally carries the **collapse stamps** (§16.10):
`floor_depth` (chain axes — the window's **effective** retained depth, `≤` the
schema-frozen floor of §16.3; equal to it when uncollapsed, `0` when the chain was
dropped) and `band_floor` (the ordinal `level` axis — the applied interval-banding
floor; **omitted when absent**). The stamps make a collapsed cube
**self-describing**: a truncated granularity **MUST NOT** be mistakable for a full
one, and two cubes compare only at their minimal common collapse (§16.10).

The reference producer's grounded axes in v0.6.0 are:

- `level` (`categorical`) — severity.
- `structural_role` (`categorical`) — the announced KIND-FRAMING marker
  (`GroupBegin` / `Terminator` / …); a *property of the line*, not a membership key.
- `where` (`chain`) — the WHERE-chain (§16.3), grounded in canon's `component`.

The axis set is **generic and extensible**: a new axis (e.g. un-folding a `status`
axis from `level` when later causal work demands it) is a **config addition** — one
more entry in `axes` and one more key in each cell `coord` — **not a schema reshape**
(the `coord` object is open over axis names; §16.4). A producer **MUST NOT**
speculatively add an axis that is not grounded in a deterministic canon field.

`template_id` **MUST NOT** be a cube axis: its cardinality is unbounded and drifting,
and it already encodes service/status in its text (a trivial, self-explaining joint).
The cube structures *what crosses* the template alphabet; it does not replace it.

### 16.3 The WHERE chain — single-parent prefix-tree + the frozen floor

`where` is a **chain**: one hierarchical path read coarse→fine (e.g.
`build_step ▸ component` in CI; `subsystem ▸ component`, `namespace ▸ service` in
deployment), declared as the ordered `chain` array (**coarsest first**). A cell's
`where` coordinate is a **prefix** of that chain — `["test", "auth"]` pins the first
two levels and aggregates (`*`) below.

- **The schema floor** is the frozen retained depth (`≤ len(chain)`). The
  hierarchy is **cut at the floor**: levels below it (the **WHICH-leaf** — e.g.
  `file`, an ephemeral `instance.id`) are **not cubed**; they are the matching key
  Sift pairs *along*, consumed below the floor (a key is *allowed* to be
  high-cardinality — that is its role). The **schema** floor is frozen **offline,
  per regime, once — never re-chosen per window**. What *can* move per window is
  the **effective** retained depth, and only **downward**, through the declared
  budget collapse of §16.10 — stamped on the axis as `floor_depth`. The emerging
  border floats *up* from the floor, **never below it**.
- **Roll-up = prefix truncation**, a many-to-one map, so `count` is **monotone under
  roll-up** (`count(coarser) ≥ count(finer)` — generalising unions the row sets).
  This is what preserves the border structure (§16.5 MUST-1). The **runtime
  roll-up** to a coarser effective floor (§16.10's WHERE step, bounding per-window
  cardinality) is exactly *prefix truncation of the chain* and requires **no schema
  change**: `floor_depth` shrinks and the cells roll up.
- **`floor_saturation`** (optional) = the fraction of emerging borders that hit the
  floor without being able to descend. High ⇒ the **schema** floor is too coarse ⇒
  re-freeze it finer **offline on the corpus, never per window** (§16.10's
  per-window step only ever *coarsens*). It is a **health metric, not a gate**: a
  saturated floor is *real signal at a coarse granularity*, not absence of signal.

A WHERE chain **MUST** be a tree — every node has a **single parent**. A multi-parent
node (a DAG) breaks the roll-up function (double-counting) and therefore breaks
count-monotonicity and the border. It is **forbidden** (§16.5 MUST-1).

Transverse membership keys (`trace_id` and the like) are **orthogonal** to the WHERE
chain (they are the leaf of no chain, they cross services), are **consumed, never
stored**, and are **neither a cube axis nor a `structural_role`**. The reference CI
regime is mono-thread → membership is positional → no such key is carried; this is a
**declared regime precondition**, not a law of CI (matrix jobs, intra-step
parallelism, and worker re-buffering can violate it and are out-of-regime).

### 16.4 Cells — closed cells, COUNT measure, deterministic order

`cells` is the set of **closed cells** — the condensed representation: every cell
whose pinned dimensions are *exactly* those constant over its row set. All non-closed
cells regenerate by closure (**lossless reconstruction**). Each cell:

```jsonc
{ "coord": { "level": "ERROR", "where": ["test", "auth"] }, "count": 53 }
```

- `coord` is an object keyed by **axis name**. An **absent** axis means **aggregated
  (`*`)**. A `categorical` axis value is a **string**; a `chain` axis value is an
  ordered **prefix-path array** (`array[i]` = value at chain level `i`; its length is
  the roll-up granularity, `≤ floor_depth`). The object is **open over axis names** —
  so a future axis validates with no schema change — but each value **MUST** be a
  string or an array of strings.
- `count` is the distributive base measure (**integer**).
- The fully-aggregated cell (`coord: {}`) carries the window total.
- Cells **MUST** serialise in a deterministic canonical (coord-sorted) order for
  replay bit-identity (§16.9).

`cell_count` / `raw_cell_count` expose the **collapse rate** the closure achieved on
this window — the condensation measure.

### 16.5 Two hard implementation MUSTs (border-monotonicity preconditions)

The emerging border (§13.6) is well-defined **only** under **both** of these. They
are stated here so an implementation cannot silently violate them:

- **MUST-1 — WHERE is a single-parent prefix-tree.** Roll-up is prefix truncation, a
  many-to-one map; `count` is monotone under it. A DAG (multi-parent node)
  double-counts ⇒ monotonicity lost ⇒ the border is ill-defined. A producer **MUST**
  reject a non-tree WHERE chain.
- **MUST-2 — emergence is defined by absolute thresholds, never a ratio.** A cell is
  emerging iff `count_previous ≤ θ_was ∧ count_current ≥ θ_now` (two **absolute**
  thresholds). This makes the emerging set the intersection of an up-set (monotone)
  and a down-set (anti-monotone) = **order-convex**, bounded by a **(lower, upper)
  border pair**. A growth **ratio** (`count_current / count_previous ≥ ρ`) is a
  *mediant* — neither monotone nor anti-monotone — and **breaks** the border
  structure. A producer **MUST NOT** define emergence by a ratio.

Either MUST violated ⇒ the floating (dynamic-granularity) border is incorrect.

### 16.6 The reservoir→cell cross (LOCATION-only, read-only)

A `reservoir` entry (§3.7) **MAY** carry a `cube_coord` — its LOCATION in the cube,
`{ level, where }` — the **only** bridge between the salience-ranked reservoir and
the emergence-ranked cube. It restores the WHERE of a salient item the **capped**
border never surfaced (the rare-salient-sub-cap / silent-regression case).

This cross is a **hard firewall (normative)**:

- It carries **LOCATION only** (`level` + `where`-path) — **never** salience back
  into the cube.
- It is **read-only and one-way**: cube geometry → item location. It **MUST NOT**
  read or write salience into a cell, re-rank or alter the emerging border, or feed
  any emergence back into the reservoir. The two orderings (the bag's salience rank,
  the cube's emergence rank) remain **separate**; the cross only *annotates* a bag
  entry with its cube coordinate.
- `cube_coord` is a **pure function** of the entry's `(level, where-path)` — no new
  non-determinism, no float.
- **Regime precondition (D9):** valid **only** while the reservoir and the cube close
  on the **same window boundary** (the fixed-window regime — true today). Under
  adaptive window closure the two may close on different boundaries, so the cross
  would point at a cell of the wrong window; it **MUST** be re-designed before reuse
  there (reuse unchanged is *out-of-regime*, not a bug).

### 16.7 Two scales — intra-window and compose

The cube exists at two scales, each drawing its WHERE coordinate from a different
place:

- **Intra-window cube** (within one document): cells aggregate per-event axes; the
  `where` coordinate is each event's canon **`component`-chain**. This is the v0.6.0
  block defined above.
- **Compose cube** (across documents, §12.1): when N per-source documents compose
  into a fleet / rollup document, each input contributes its **`source`** block
  (service / fleet / region) as the WHERE coordinate of a higher-level cube — the
  cross-document organ (env / region / service). Its emerging border lives in a
  `MetaLogDiff.cube_diff` (§13.6); composition **re-closes** (§12.1).

### 16.8 Clean-kill isolation

The cube is a **self-contained, additive** block. In v0.6.0 it does **not** become
the source of truth for any categorical marginal and does **not** reshape `stats`,
`behavior`, or the 1-D `level` fields — those stand unchanged. Removal is therefore a
**single revert**: delete the `cube` block, the `cube_diff` block (§13.6), and the
`reservoir[*].cube_coord` field, and bump `canonicalization_version`.

> The "marginals become projections of the cube" reorganization — replacing stored
> 1-D categorical counts with cube projections to recover the bytes — is
> **deliberately deferred** until the cube is decided to be *kept*. It is **not** part
> of the additive v0.6.0 landing, precisely so that the keep/kill decision stays a
> one-line revert and the size cost stays cleanly *additive* (measurable as the cube's
> own share of the document).

### 16.9 Determinism

The cube is computed **in batch over the closed window** — a finite, frozen, ordered
set — so it is a **pure function** of that set and **bit-identical across stdlibs and
operating systems** (the standing cross-stdlib / cross-OS diagonal). Specifically:

- `count` is integer; the closure and the border are set operations; cells and
  border cells **MUST** serialise in canonical (coord-sorted) order.
- The WHERE roll-up is **prefix truncation only** — there is **no float→int** anywhere
  in the chain.
- New serialization surfaces (the cube block) are **golden-gated**; the landing
  carries **one** `canonicalization_version` bump and its golden cascade in the same
  pass.
- The §16.10 collapse is **deterministic content**: the trigger reads only the
  closed window (never wall-clock, never an environment budget); the policy is pure
  integer (`Δcells / cost` by cross-multiplication — no float); and the fixed
  candidate order (LEVEL before WHERE) **is** the declared total-order tie-break.
  The policy is **version-stamped** — changing its budget, costs, steps or
  tie-break spends `canonicalization_version` — and the collapse path (including
  compare-at-minimal-common-collapse) is fixture-exercised under the cross-stdlib
  diagonal.

### 16.10 The per-window budget collapse — bounded, admissible, stamped

An always-on closed cube can explode (`O(B·2ⁿ)`). The bound is a **per-window,
budget-driven dimensional collapse** — three separated objects:

- **BUDGET** — a static producer constant on the closed-cell count (reference
  producer: 4096), never adaptive, never read from the environment. A producer
  **SHOULD** report it in `cube.cell_budget` (uint, optional, added in v0.9.0):
  the budget is static precisely so that it is knowable in advance, and
  declaring it is what makes it knowable to the **consumer**. It dominates every
  other term of the size formula (§11.4), so an undeclared budget leaves the
  consumer unable to price the block at all.
- **TRIGGER** — a pure function of the closed window's content: closed cells over
  budget. **Closure-first, collapse-last**: when closure alone fits, nothing
  degrades — collapse is the rare guard, not the normal path.
- **POLICY** — while over budget, apply the best **admissible** monotone coarsening
  of the base and **re-close**, iterating until under budget (or no step reduces
  the count). Best = maximal `Δcells / cost`, measured by trial re-closure; the
  step costs are **frozen and window-independent** — the policy can never learn
  from the data it is bounding.

The admissible steps — and **admissibility is a BARRIER, never a price**:
inadmissible coarsenings are unreachable by construction, so no explosion can ever
"justify" an unsafe collapse:

- **LEVEL interval-banding** — floor `f`: levels `[0..f-1]` merge into their top
  representative `f-1` (`{TRACE, DEBUG}` first — the cheapest, near-lossless band).
  **The severity frontier is absolute: `{ERROR, FATAL}` are never banded** — the
  maximum floor stops at `ERROR`'s index, preserving the distinction the failure
  lexicon, the `Terminator` role and border attribution all read.
- **WHERE prefix truncation** — one level toward the root (a depth-1 chain
  degenerates to a drop). Location loss is the **declared last resort**: its frozen
  cost dominates every banding step.

The applied collapse is **stamped on the axes** (§16.2's `band_floor` / effective
`floor_depth`) — a collapsed cube is self-describing. Comparability follows from
the stamps:

- **Diff reads both cubes at their minimal common collapse** — the coarser stamp
  per axis (maximum `band_floor`, minimum retained depth) — so neither side
  manufactures a distinction the other collapsed away.
- **Compose seeds the minimal common collapse of its members, then re-closes** —
  the merge is never finer than its coarsest member (roll-down-then-re-close).
- **Expansion never means un-collapse**: a coarsened window is never re-derived
  finer downstream; finer truth exists only upstream of the collapse, in the raw
  events.

Neither the axis **set** (§16.2) nor the **schema** floor (§16.3) ever adapts per
window — the collapse coarsens **values** inside the frozen schema, declares
itself, and pays in **granularity, never in correctness**: the coarsening is a
surjection that fuses cells, so counts stay exact at the coarser granularity and
nothing is dropped.
