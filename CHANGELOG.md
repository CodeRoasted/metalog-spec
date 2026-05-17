# Changelog

All notable changes to the MetaLog specification are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The spec follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice:** during the 0.x line, MINOR version bumps may
> still introduce incompatible schema changes. After 1.0, semver
> applies strictly.

---

## [0.3.0] — 2026-05-17

### Added
- **`stats.tail_summary`** (optional) — three-field block
  exposing the *shape* of the long tail in bounded space:
  `tail_template_count`, `tail_entropy_bits`, `tail_max_rate`.
  Adds ~60 bytes per window; preserves the 4 KB / 1 M-line
  envelope target. Lets consumers detect tail-mass concentration
  shifts that the existing `tail_count` / `tail_unique` pair
  cannot expose. SPEC §3.6, ADR
  [`adr/0002-stats-tail-summary.md`](adr/0002-stats-tail-summary.md).
- **§12.3.1 (informative)** — Multi-source n-gram noise. Documents
  the structural limitation that `behavior.top_ngrams`-derived
  signals (BranchingShift, NoveltyNGram, VanishedTemplate against
  n-gram pairs) carry interleaving-dependent noise on composed
  multi-source documents and SHOULD be treated by consumers as
  supporting evidence, not standalone alert sources.

### Changed
- None. Backwards compatible with 0.2.x. Consumers that do not
  understand `tail_summary` ignore it per §8 Conformance.

### Schema
- `schema/metalog.v0.schema.json` extended with the optional
  `stats.tail_summary` object (all three fields required when
  present). No existing field changes.

### Status
- `attribution` remains reserved for v1.0.
- v0.3.x is still draft; MINOR bumps may break compatibility
  until v1.0.

---

## [0.2.0] — 2026-04-27

### Changed (breaking)
- **`stats.top_k[i].template` is now OPTIONAL** (was required in
  0.1.x). Producers may emit template strings inline, in a
  top-level `templates` dedup map, or omit them entirely
  ("id-only" mode for bandwidth-bound transports). See
  [SPEC §3.4](SPEC.md#34-template-strings--id-only-mode-and-dedup-map).
  This was reserved for v0.2 in the 0.1.1 size-budget section
  and is now realised.
- **Schema field order** in `metalog.v0.schema.json` updated for
  the new optional fields. The old schema is retained at the same
  `$id` (overwritten); pinning to a specific version now MUST be
  done via `metalog_version` in the document, not the schema URI.

### Added
- **Top-level `templates` dedup map** (optional) — see SPEC §3.4.
- **`behavior.dominant_path`** formalised (was emitted by InSight
  but only present in the example, not the spec text). SPEC §4.1.
- **`behavior.branching`** array — per-node fanout, total outgoing,
  Shannon entropy. SPEC §4.2. Lets consumers identify decision
  points without retrieving the full transition matrix.
- **`behavior.sessions_observed`** and **`behavior.session_aware`**
  flags. SPEC §4.3 + §14.
- **§12 Composition (`compose(A, B) -> C`)** — defines associative
  merge semantics for sharded ingestion and time-axis rollup.
- **§13 `MetaLogDiff`** — separate JSON document type for
  pair-wise comparison; generalises `stability` to arbitrary
  pairs. New schema at `schema/metalog_diff.v0.schema.json`.
- **§14 Sessions** — opaque per-producer session keys; n-grams
  may be computed per-session and aggregated.
- **Top-level `provenance` array** — set by composers to record
  the inputs that fed a composed document. SPEC §12.4.
- **Schema:** `source.host` accepted (already used in
  `provenance` examples).
- **Schema:** sibling `schema/metalog_diff.v0.schema.json` for
  the new diff document type.

### Status
- `attribution` remains reserved for v1.0.
- v0.2.x is still draft; MINOR bumps may break compatibility
  until v1.0.

---

## [0.1.1] — 2026-04-24

### Changed
- **`template_id` hash function: BLAKE3-128 → SHA-256 truncated to 128 bits.**
  First-contact with the C++ ecosystem (Conan Center) revealed BLAKE3 is
  not universally packaged, while SHA-256 is in every mainstream language
  standard library (Python `hashlib`, Go `crypto/sha256`, Rust `sha2`,
  JS Web Crypto, openssl for C++). Implementer friction outweighs the
  perf win at template-creation rate (templates are hashed once per
  unique template, not per log line). See updated
  [RATIONALE §R2](RATIONALE.md#r2-why-sha-25616-for-template_id).
- **Default `top_k_size`: 256 → 64.** The size budget math (now
  documented in [SPEC §11](SPEC.md#11-size-budget)) made it explicit
  that 256 entries blow a reasonable envelope by ~10×. 64 covers
  ≥ 95% of Zipfian log streams in ~10 KB. Producers may still pick
  16 (edge), 32 (compact), or 256 (high-cardinality) explicitly.

### Added
- **§11 Size budget** (informative): per-entry cost table, envelope
  size by `k`, and an honest discussion of the 4 KB / 1M-lines target
  (reachable at `k ≤ 32`, or with a future v0.2 "id-only" mode).
- Updated example: `metalog_version: 0.1.1`, `top_k_size: 64`,
  template_ids are real SHA-256[:16] hashes of the example templates
  (verifiable by anyone with `hashlib`).

### Status
- `attribution` remains reserved for v1.0.
- v0.1.x is still draft; MINOR bumps may break compatibility until v1.0.

---

## [0.1.0] — 2026-04-24

### Added
- First public draft.
- Top-level envelope: `metalog_version`, `producer`, `window`,
  `source`, `stats`.
- Optional sections: `behavior`, `stability`, `attribution`,
  `extensions`.
- `template_id` definition: `"h:" + lower_hex(BLAKE3-128(canonical_template))`.
- Bounded `top_k` + tail-summary design (default `k = 256`).
- KL / JS divergence fields in `stability` for cross-vendor
  comparability.
- JSON Schema at `schema/metalog.v0.schema.json`.
- Worked example at `schema/metalog.v0.example.json`.
- `RATIONALE.md` documenting why each design decision was made and
  what was rejected.

### Status
- `attribution` is reserved but its sketch encoding is not yet
  pinned. Producers should not emit `attribution` in interoperable
  MetaLogs until v1.0.
