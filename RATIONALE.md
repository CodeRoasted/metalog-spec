# MetaLog Design Rationale

> Companion to [`SPEC.md`](SPEC.md). For each notable design choice,
> this file documents *what* was decided, *why*, and *what was
> rejected*. The goal is that nothing in the spec gets re-litigated
> from scratch six months from now.

---

## R1. Why JSON, not protobuf / msgpack / capnp?

**Decided:** JSON.

**Why:**
- A MetaLog is small: its size is bounded by caps its producer
  declares — ~9 KB for a `stats`-only document at the recommended
  `top_k_size` of 64, among SPEC §11.4's worked ceilings. Encoding
  overhead is irrelevant.
- The buyers and integrators (SREs) already speak JSON. A new format
  would be a tax we can't afford.
- LLMs consume JSON natively. Phase 5 of the consumer pipeline
  (LLM-based explanation) becomes trivial.
- `jq` works.
- `curl | jq` works.

**Rejected:**
- *protobuf*: faster to parse, but requires schema distribution and
  generated code in every language. Hostile to the "just look at it"
  workflow that makes operators trust a tool.
- *msgpack/cbor*: marginal size win, opaque to humans.
- *capnp/flatbuffers*: zero-copy is a producer-side win nobody asked
  for. MetaLogs are produced once per window, not per message.

We will revisit if a single MetaLog ever exceeds 100 KB. Until then,
JSON.

---

## R2. Why SHA-256[:16] for `template_id`?

**Decided:** `"h:" + lower_hex(SHA-256(canonical_template_utf8)[0:16])`.

**Why:**
- SHA-256 is in **every** mainstream language standard library:
  Python `hashlib.sha256`, Go `crypto/sha256`, Rust `sha2`,
  Java `MessageDigest.getInstance("SHA-256")`, Node `crypto.createHash`,
  Web Crypto `crypto.subtle.digest('SHA-256', ...)`, every C/C++
  project that links openssl. Zero packaging friction for
  implementers — the single biggest factor in spec adoption.
- 128 bits of output gives a collision probability of ~10⁻¹⁹ at
  10⁹ distinct templates per producer — far below the relevant
  threshold.
- SHA-256 is a conservative choice that passes any security review
  without questions.
- Computational cost is irrelevant: `template_id` is computed once
  per *unique* template per producer (typically a few thousand
  total), not once per log line.
- The `"h:"` prefix reserves the namespace so future ID schemes
  (e.g. content + parameter mask, or learned embeddings) can coexist
  without breaking parsers.

**Rejected:**
- *Monotonic integer IDs*: the obvious choice, used by InSight
  internally. Fatal flaw: not portable across processes, restarts,
  or producers. Today's `EventID 17` is meaningless in tomorrow's
  MetaLog. Rejected for the *cross-implementation* requirement.
- *BLAKE3-128*: faster than SHA-256, with a strong security margin,
  but **not in any language standard library** and (as of v0.1.1)
  not in Conan Center. Adopting it requires every implementer to
  vendor or package BLAKE3 themselves. The packaging cost outweighs
  the perf win at template-creation rate. Originally chosen in v0.1.0
  draft, replaced in v0.1.1 after first-contact with the C++
  ecosystem revealed the gap. May be revisited if/when BLAKE3
  becomes universally packaged.
- *xxh3-128*: fastest of the three, but not cryptographic. SHA-256
  is conservative enough to never be questioned in a security
  review; xxh3 invites the question.
- *MD5*: cryptographically broken. Identification doesn't strictly
  need crypto strength, but defaulting to a broken primitive
  invites questions we don't want to answer in customer security
  reviews.
- *Full SHA-256 (32 hex chars)*: doubles the size of every
  `template_id` for no collision-resistance benefit at the relevant
  scale.

---

## R3. Why a fixed top-K + tail summary, not a full histogram?

**Decided:** `top_k` (default 64) + `tail_count` + `tail_unique`.

**Why:**
- The MetaLog **must** have a bounded size. A real production
  service has 1–5 K unique templates over 5 minutes. A naive full
  histogram blows the envelope budget.
- Top-K compression is information-theoretically optimal for the
  use case: the top 64 templates almost always cover ≥ 95% of
  observations in real log streams (Zipfian distribution).
- The tail summary preserves *that there is* a tail, which is
  enough for divergence detection (a sudden change in `tail_unique`
  is a real signal).
- Misra-Gries and SpaceSaving are well-studied streaming
  algorithms (~200 LoC each) that compute top-K in one pass with
  bounded memory. Implementable in any language.

**Why k = 64 specifically (and not 256 as in v0.1.0 draft):**
- 256 entries × ~150 bytes each = ~40 KB envelope. Over-shoots even a
  generous "tens of KB" budget.
- 64 entries × ~150 bytes = ~10 KB envelope. Comfortable, and the
  Zipfian coverage at 64 is already ≥ 95% on real logs.
- No size per line count follows from the choice of k, because a
  document's size does not depend on how many lines its window saw
  (SPEC §11.5). Until 0.10.0 this section also claimed a 4 KB target,
  reachable at k = 32 or in id-only mode. Even SPEC §11.2's lowest
  published costs put both routes above it, no implementation met it, and it was withdrawn
  ([ADR 0006](adr/0006-no-size-per-line-count.md)).
- v0.1.0 draft used 256 as the recommended default; v0.1.1 lowered
  it after the size-budget math (now spec §11) was made explicit.
- Misra-Gries and SpaceSaving are well-studied streaming
  algorithms (~200 LoC each) that compute top-K in one pass with
  bounded memory. Implementable in any language.

**Rejected:**
- *Full histogram*: doesn't fit. Defeats the point.
- *Bloom filter only*: tells you membership, not frequency. The
  frequency is the signal.
- *HyperLogLog only*: tells you cardinality, not which templates.
- *Reservoir sample of templates*: doesn't preserve frequency
  ordering, harder to diff between windows.
- *Variable top-K based on entropy*: producer-side autotuning
  destroys cross-window comparability. The K must be fixed within
  a producer's stream.

A MetaLog is **lossy by design**. We are not building a log
index. The lossiness is the product.

---

## R4. Why is `behavior` (sequence info) optional?

**Decided:** Optional. Producers without buffering may omit it.

**Why:**
- Sequence/transition information requires holding events in
  order across time, which not every producer can do (think:
  edge log shippers, embedded systems).
- The frequency `stats` block is enough for the headline use case
  (cost reduction, divergence detection).
- Forcing `behavior` would exclude useful low-resource producers.

**Rejected:**
- *Required*: would prevent edge / embedded producers entirely.
- *Required for "compliant" producers, optional for "lite"*: spec
  surface explosion. We don't need profiles yet.

When sequence detection becomes the differentiator (Phase 4
anomaly), `behavior` will be the input. Producers that want their
output usable for anomaly detection will populate it. Market
pressure handles the rest.

---

## R5. Why is `stability` cross-window, not absolute?

**Decided:** `stability` references the previous window.

**Why:**
- "Is the system behaving differently than 5 minutes ago?" is the
  primary operator question.
- Absolute stability ("how stable is this system?") has no
  reference point and degenerates into vendor-defined magic
  numbers.
- KL/JS divergence over template frequency vectors is well-defined,
  symmetric (JS), and computable in O(top_k).

**Rejected:**
- *Stability vs a long-term baseline*: requires storing baselines,
  which is consumer-side state. The spec stays stateless.
- *Stability vs all previous windows*: O(history) per MetaLog.
  Doesn't compose.

The producer chooses what "previous window" means (typically the
immediately preceding window of the same duration) and reports its
boundary in `previous_window_end`.

---

## R6. Why is `attribution` deferred to v1.0?

**Decided:** The field is reserved; the encoding is not yet pinned.

**Why:**
- Count-Min Sketch encoding has multiple reasonable choices
  (width × depth, hash family, byte order) that need to be pinned
  in writing before we promise interoperability.
- We don't have enough cross-implementation experience to pick
  defaults that won't be regretted.
- It's safer to ship without `attribution` than to ship a wrong
  encoding that becomes load-bearing.

This is honest scope management. v0 covers the wedge (frequency
+ behaviour + stability). v1 closes the loop with attribution.

---

## R7. Why no wire protocol?

**Decided:** Out of scope. MetaLogs are JSON documents; carry them
however you like.

**Why:**
- The observability transport landscape (Vector, Fluent Bit, OTel
  Collector, Kafka, S3) is solved. Adding another wire format
  fragments the ecosystem.
- A MetaLog is small and infrequent (one per window per source).
  HTTP POST works. Writing to a file works. Pushing to a Kafka
  topic works.

**Rejected:**
- *gRPC service definition*: overkill at MetaLog volumes. Adds a
  binding burden in every language.
- *OTLP extension*: we don't want to be governed by the OTel TC's
  process. Maybe later, after v1.0, as a *consumer* of MetaLog
  via OTel — never as the canonical transport.

---

## R8. Why CC-BY-4.0 for the spec text and MIT for schemas?

**Decided:** Spec text → CC-BY-4.0. JSON schemas and reference
encoders → MIT.

**Why:**
- CC-BY-4.0 is the standard for open specifications (W3C, IETF
  pattern). Allows any vendor to quote the spec in marketing,
  documentation, and product manuals.
- MIT on the schemas means anyone can vendor them into proprietary
  code without legal review. Removes adoption friction.
- Neither license restricts commercial use. The point is to make
  MetaLog a *standard*, not to extract rent from the spec itself.

The rent comes from running the best implementation, the
validation harness, and the hosted service — not from the spec.
The spec is a loss-leader.

**Rejected:**
- *Apache-2.0 with patent grant on the spec*: implies a patent
  exists. We don't have one and don't intend to file one.
- *Proprietary spec*: defeats the entire point. Datadog and Splunk
  already have proprietary log formats; the world doesn't need
  another.

---

## R9. Why publish v0.1 *before* the reference implementation ships v1?

**Decided:** Publish now. Stamp v1.0 when the InSight engine ships
its real Phase 3.

**Why:**
- Naming and category-defining matter more than ship-date polish.
  Whoever publishes the spec first owns the term "MetaLog" in the
  observability space.
- A draft spec lets early implementers (in any language) start
  building, surface real gaps, and feed those back before v1.0
  freezes the schema.
- The risk of *not* publishing is that an incumbent (Datadog,
  Splunk, Elastic, Grafana) ships a proprietary equivalent under a
  different name and we become a clone of their term. That risk is
  larger than the risk of publishing a draft we have to revise.

**Rejected:**
- *Wait for v1.0*: optimises for spec polish, loses the
  category-naming race.
- *Publish silently with no version stamp*: signals we're not
  serious. v0.1 + a CHANGELOG signals we are.
