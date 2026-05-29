# MetaLog Specification — v0.5.0 (Draft)

> **Status:** Draft. Subject to incompatible change until v1.0.
> **Cross-reference:** [`RATIONALE.md`](RATIONALE.md) for *why*
> each design decision was made.

This document uses [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119)
keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**.

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
| `canonicalization_version` | string | no | Opaque identifier for the canonicalization rules in effect. Gates `compose()`/diff comparability. See §2.4. |
| `retention_profile` | string | no | Opaque identifier for the retention parameters (top_k, reservoir, salience weights, diversity caps). Gates `compose()`/diff comparability. See §2.4. |
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
| `structural_role` | string, optional | announced role (e.g. `terminator`); omitted when none. |
| `structural_surprise` | uint `0..100` | deviation of the template's most-likely incoming transition from the `dominant_path` (§4.1); `0` = on the expected flow. |
| `novelty` | uint `0..100` | how late the template first appeared within the window (first-seen position over `lines_observed`); `0` = present from the start. The `retention_profile` MAY weight/cap it softer than severity/structure. |
| `salience` | uint | the deterministic admission/ranking score (§3.7.2). |
| `within_window_ordinal` | uint, optional | reconciled first-seen ordinal; the per-entry re-derivation sub-coordinate (§15.4). |

A `reservoir` entry **MUST NOT** also appear in `top_k` (the reservoir holds only
templates that did not qualify by frequency).

#### 3.7.2 Salience and admission

`salience` is a **deterministic, integer** score combining intrinsic axes —
severity (from `level` / `structural_role` / content), `structural_surprise`, and
`novelty` — **modulated by rarity**. Rarity is a **modulator, never a gate**: a
benign, contentless template scores `0` and **MUST NOT** be admitted (rarity alone
never promotes a template). Admission is **salience-ranked**, subject to a
**per-class diversity cap** (the reservoir covers *distinct* salient kinds, not
many variants of one), and **bounded** by the configured reservoir size.

The exact weights, reservoir size, and diversity caps are the producer's
**`retention_profile`** (§9), not fixed by this spec. Their **mechanism** is
normative: salience combines the named axes with rarity-modulation, admission is
salience-ranked + diversity-capped, arithmetic is **integer** with **tie-break by
`template_id`**, and a given input under a given `retention_profile` **MUST** yield
a **bit-identical** reservoir. Two documents are comparable (diff, §13) only under
a **matching** `retention_profile`.

#### 3.7.3 Relationship to `tail_summary` and composition

`tail_summary` (§3.6) is computed over the **residual after `top_k` ∪
`reservoir`**; a reservoir-promoted template **MUST NOT** be double-counted in the
tail aggregates. Under composition (§12) the reservoir is **carried**: `salience`
is **re-derived** over the merged counts (rarity shifts on merge),
`structural_surprise` / `novelty` are carried as the **max** across inputs, and
entries remain **excluded from the tail**. A composed reservoir is re-derivable
for any template that was salient in **at least one** input; it cannot recover a
template that was pure-tail in every input (the `compose`-lossy-tail limit).

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
  ]
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
