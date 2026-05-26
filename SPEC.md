# MetaLog Specification — v0.4.0 (Draft)

> **Status:** Draft. Subject to incompatible change until v1.0.
> **Cross-reference:** [`RATIONALE.md`](RATIONALE.md) for *why*
> each design decision was made.

This document uses [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)
keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**.

> **What changed in 0.2:** template strings are no longer required
> inside `stats.top_k` entries — they live in an optional top-level
> `templates` dedup map instead, and may be omitted entirely
> (id-only mode). The `behavior` block has been formalised
> (`dominant_path`, `graph_edge_count`, `branching`,
> `sessions_observed`, `session_aware`). Two sibling sections were
> added: `compose()` (§12) for merging MetaLogs across windows or
> shards, and a separate `MetaLogDiff` document (§13). Sessions are
> defined in §14. See [`CHANGELOG.md`](CHANGELOG.md) for the full
> diff.

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
- **Session** — A producer-defined opaque grouping of related events
  (e.g. trace ID, request ID, user session). Used to scope sequence
  observations. See §14.
- **Producer** — A program that consumes log lines and emits MetaLog
  documents.
- **Consumer** — A program that reads MetaLog documents (dashboard,
  alert engine, LLM prompt builder, archive, etc).
- **MetaLog** — A JSON document conforming to this specification.
- **MetaLogDiff** — A separate JSON document describing the
  difference between two MetaLogs. See §13.

---

## 2. Document structure

A MetaLog **MUST** be a single JSON object containing the following
top-level fields:

| Field | Type | Required | Purpose |
|---|---|---|---|
t| `metalog_version` | string | yes | Spec version this document conforms to. SemVer string (e.g. `"0.4.0"`). |
| `producer` | object | yes | Identifies the producing implementation. See §2.1. |
| `window` | object | yes | The time interval covered. See §2.2. |
| `source` | object | yes | What was observed (service, host, fleet). See §2.3. |
| `stats` | object | yes | Per-template counts and frequency metrics. See §3. |
| `templates` | object | no | Optional dedup map `template_id → template_str`. See §3.4. |
| `behavior` | object | no | Sequence/transition fingerprint. See §4. |
| `stability` | object | no | Divergence from the previous window. See §5. |
| `attribution` | object | no | Distribution of templates across sub-sources. See §6. |
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
  "version": "0.2.0",         // string, required, SemVer
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
      "level":       "INFO"                  // string, optional, dominant log level
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
      "entropy_bits": 0.47,    // number, optional, Shannon entropy over value_counts
      "approximate_cardinality": 1847  // integer, optional — see §3.5.1
    },
    {
      "param_index": 1,
      "value_counts": { "200": 950, "500": 50 },
      "total": 1000,
      "entropy_bits": 0.31,
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
    "previous_cardinality":    1847,          // integer, optional
    "current_cardinality":     183204,        // integer, optional
    "cardinality_delta":       181357         // integer (signed), optional
                                              // = current - previous; positive = grew
  }
]
```

- `cardinality_delta` **MUST** equal `current_cardinality - previous_cardinality`
  (signed, positive = grew, negative = shrank).
- Consumers detecting high-cardinality injection **SHOULD** alarm when
  `current_cardinality / previous_cardinality > N` (e.g. N = 10) and
  `previous_cardinality < threshold` (baseline was low-cardinality).
- `field_histogram_deltas` **MUST** be sorted by `js_divergence` descending.

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

Doubling `top_k` from 64 to 128 grows the envelope by ~10 KB per window in
inline mode (§11). `tail_summary` provides three of the four signals that
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
  ],
  "sessions_observed": 0,               // integer, optional, distinct session keys seen
  "session_aware": false                // bool, optional, true iff this fingerprint was computed per-session (§14)
}
```

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

### 4.3 `sessions_observed` and `session_aware`

These two fields disclose how the producer scoped its sequence
observations. See §14. When `session_aware = false`, n-grams cross
session boundaries (the global event stream); when
`session_aware = true`, n-grams are computed within a single session
and aggregated across sessions.

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

---

## 8. Conformance

A producer is **conformant** with this spec at version *X.Y.Z* if:

1. Every MetaLog it emits validates against
   [`schema/metalog.v0.schema.json`](schema/metalog.v0.schema.json)
   for that version's MAJOR.
2. Every required field is populated according to its definition
   above.
3. `template_id` values are computed exactly as specified in §3.2.
4. `top_k` is truthfully bounded at `top_k_size`.

A consumer is conformant if it accepts any document that validates
against the schema, ignoring unknown fields and unknown extensions,
and resolves template strings according to §3.4.

There is no central conformance authority. The schema is the test.

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
- Session keys (§14) **MUST NOT** carry user-identifying information
  in interoperable MetaLogs. Producers **SHOULD** hash external
  identifiers before using them as session keys.
- Sketches in `attribution` are probabilistic and **MUST NOT** be
  treated as authoritative for security decisions.

---

## 11. Size budget

This section is **informative**. It explains how the spec achieves
the headline "bounded-size" property and gives implementers an
honest picture of what envelopes to expect.

### Per-entry cost

A single `top_k` entry, JSON-encoded with no whitespace, costs
roughly:

| Field | Bytes (inline mode) | Bytes (id-only mode) |
|---|---|---|
| `template_id` (`"h:"` + 32 hex) | ~40 | ~40 |
| `template` (typical skeleton, 40–80 chars) | ~50–100 | 0 |
| `count` + `frequency` + optional `level` | ~30 | ~30 |
| JSON syntax overhead (quotes, commas, braces) | ~30 | ~20 |
| **Total per entry** | **~150–200** | **~90** |

### Envelope size by `k`

With the fixed envelope (~400 bytes for `metalog_version`,
`producer`, `window`, `source`, the optional blocks' framing) plus
`k` entries, in inline mode:

| `k` | Approx envelope (inline) | Approx envelope (id-only) | Recommended for |
|---|---|---|---|
| 16  | ~3 KB    | ~1.8 KB | Edge / ultra-compact deployments |
| 32  | ~5 KB    | ~3 KB | Compact deployments |
| **64**  | **~10 KB**   | **~6 KB** | **Default — covers ~95% of Zipfian log streams** |
| 128 | ~20 KB   | ~12 KB | Wide services |
| 256 | ~40 KB   | ~25 KB | High-cardinality / forensic use |

Real log streams follow a Zipfian distribution: the top 64 templates
typically account for 95–99% of all observations.

### Reaching the 4 KB / 1M-lines target

The headline "≤ 4 KB per MetaLog covering ≥ 1 M log lines" target
is reached at:

1. `k ≤ 32` in inline mode, **or**
2. `k ≤ 64` in id-only mode (§3.4) with template strings shipped
   out-of-band or via a top-level `templates` dedup map shared
   across many MetaLogs.

Producers **SHOULD** report their actual envelope size in
`extensions.org.metalog.envelope_bytes` (or equivalent) so consumers
can track the compression ratio achieved on real workloads.

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
- `C.behavior.graph_edge_count` is the union edge count.
- `C.behavior.branching` is recomputed from the merged graph.
- `C.behavior.dominant_path` is re-derived greedily from the merged
  graph; consumers **MUST NOT** assume it equals the path of either
  input.
- `C.stability` **MUST** be omitted (it is meaningless across
  composed inputs); consumers wanting a current-vs-prior view of a
  composed document should use §13 Diff explicitly.
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

Producers **MAY** mitigate by computing `behavior` per session
([§4.3](#43-sessions_observed-and-session_aware)) where sessions are
defined to avoid cross-source interleaving; but consumers **MUST NOT**
assume any particular producer mitigation is in place.

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
  `extensions.org.metalog.deltas_truncated_at`.

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

---

## 14. Sessions

A **session** is a producer-defined opaque grouping of related
events. Examples: HTTP request trace ID, user login session,
distributed-trace span tree, Kafka partition key.

### 14.1 Why sessions matter

A bare global event stream conflates events from concurrent
unrelated activities. The bigram `(login, payment_failed)` looks
suspicious until you realise the login and the failure belonged to
two different users. Session-aware n-grams remove this confounding.

### 14.2 Behaviour when `session_aware = true`

When a producer computes `behavior` per-session and aggregates:

- An n-gram **MUST NOT** span a session boundary. The producer
  groups events by session key, computes the per-session n-grams,
  and sums their counts into the global `top_ngrams` table.
- `behavior.sessions_observed` **MUST** be set to the number of
  distinct session keys that contributed at least one event during
  the window.
- `behavior.session_aware` **MUST** be `true`.
- `dominant_path` is computed over the aggregated per-session
  transition graph (a transition `A → B` exists if some session
  observed `A` immediately followed by `B`).

### 14.3 Behaviour when `session_aware = false`

When a producer cannot or does not want to identify sessions, it
**MUST** omit `behavior.session_aware` (treated as `false`) and
**MAY** omit `behavior.sessions_observed` (treated as `0`). N-grams
are computed over the global event stream as in v0.1.

### 14.4 Session key opacity

Session keys **MUST NOT** appear in interoperable MetaLogs. They
are an internal partitioning hint for the producer. Consumers see
only the aggregated per-session counts via the standard `behavior`
fields. Producers needing to expose session-level breakdowns
**SHOULD** emit one MetaLog per session and combine them via §12
Composition with `provenance` annotations.
