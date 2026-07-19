# Changelog

All notable changes to the MetaLog specification are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The spec follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice:** during the 0.x line, MINOR version bumps may
> still introduce incompatible schema changes. After 1.0, semver
> applies strictly.

---

## [Unreleased]

> **Version → 0.6.0 (Draft) — the cube (EXPERIMENTAL).** Adds the intra-window
> **joint categorical condensation** to the format. The cube is **additive,
> provisional, and removable in a single revert** (§16.8): it is integrated now as
> the test rig for the upcoming causal (do-operator) verdict, not because the
> standing BGL evidence justified it (that leaned *ornament*, mono-axis). The format
> is v0.x with zero external consumers, so the landing is explicitly reversible and a
> future 0.x **MAY** remove it. A **pre-registered kill-criterion** governs the
> keep/kill decision (recorded in the internal cube spec, not here).

### Added (0.6.0)
- **§16 `cube` block** — a closed cube over a small fixed set of low-card
  categorical axes (`level × structural_role × where`-chain). Condensed by closure
  (lossless where the data correlates), an **attributor/projector** not a detector.
  Axis set is **fixed, frozen, axis-generic** (a future `status` axis is a config
  addition, not a schema reshape). `template_id` **MUST NOT** be an axis.
- **§16.3 WHERE-chain** — a single-parent prefix-tree with a schema-frozen
  `floor_depth`; roll-up = prefix truncation (count-monotone). Forward-compatible
  with a future runtime dimensional-shrink (floor shrinks, **no** schema change).
  The WHICH-leaf below the floor is the (high-card, legitimate) matching key, not
  cubed.
- **§16.5 two hard MUSTs** — WHERE = single-parent tree (a DAG breaks border
  monotonicity); emergence = **absolute thresholds, never a growth ratio**.
- **§13.6 `cube_diff`** — the emerging border as an order-convex **(lower, upper)
  border pair** (`upper` = the minimal-generator headline), plus the `vanishing`
  dual. Emitted only when both inputs carry a cube with **equal axes**.
- **§16.6 reservoir→cell cross** — `reservoir[*].cube_coord`, a **LOCATION-only,
  read-only, one-way** annotation restoring the WHERE of a salient item the capped
  border never surfaced. Hard firewall: no salience flows into the cube; valid only
  in the fixed-window regime (D9).
- **§16.7 two scales** — the **intra-window** cube draws WHERE from canon
  `component`; the **compose** cube draws WHERE from the per-document `source`.
- **§12.1 `C.cube` re-close** — counts compose by addition (SIMD-friendly) but the
  **closure does not distribute** → composer expands, adds, and **re-closes**
  (recompute is the deterministic default).
- **§16.8 clean-kill isolation** — the cube is additive; the "marginals become
  cube projections" reorganization is **deferred** until a keep decision, keeping
  removal a one-line revert and the size cost cleanly additive.
- Schema: `cube` (top-level), `cube_axis`/`cube_cell`/`cube_coord` (`$defs`) in
  `metalog.v0.schema.json`; `cube_diff` + cube `$defs` in
  `metalog_diff.v0.schema.json`. One `canonicalization_version` bump
  (`component` now propagates into the metalog) + `retention_profile` bump (axis/
  floor config), with the golden cascade in the same pass.

> **Version → 0.5.0 (Draft).** Phase-3 spec formalization **complete in
> scope** (still Draft; v1.0 freeze gated on broader criteria).
> 0.5.0 contracts the salience-epic shape end-to-end: §3.7 reservoir, §2.4
> processing identifiers + compose/diff gating, §15 re-derivation coordinate
> (raw/composed XOR), and §12.1 reservoir-carry + compose-visible field
> histograms.

### Changed
- **§15.2 raw / composed XOR (refined during 0.5.0 Draft).** A coordinate is now
  explicitly **either** a *raw* coordinate (`source_ref`+`bounds`) **or** a
  *composed* coordinate (`children`), mutually exclusive — never both, never
  neither. Composed coordinates **MUST NOT** emit sentinel values for
  `source_ref`/`bounds`; consumers discriminate by `children.present`. Resolves
  the ambiguity earlier 0.5.0 drafts had between required `source_ref`/`bounds`
  and "address-is-the-children" composition.

### Added
- **§3.5 / §12.1 compose-visible field histograms.** `param_histograms` are
  **carried** through `compose()` (previously dropped — the F8 / F2-value gap).
  Per `(template_id, param_index)` pair present in both inputs: merge
  `value_counts` (union + sum, top-N truncate to cap), sum `total`, recompute
  `entropy_bits`; `approximate_cardinality` MAY use sketch-union or
  `max(A, B)` as a conservative lower bound. One-input-only histograms MAY be
  carried unchanged (`total` reflects partial coverage) or omitted. Per-slot
  value-distribution shifts now remain visible against composed (pyramid-
  baseline) documents, not only at raw scale.
- **§2.4 Processing identifiers (`canonicalization_version`,
  `retention_profile`)** — two opaque top-level strings naming the
  *producer-side processing contract*: the canonicalization rules and the
  retention parameters under which the document was generated. Independent of
  `metalog_version`. **Comparability gate (normative):** when both inputs to
  `compose()` (§12) or to `MetaLogDiff` (§13) carry one of these identifiers,
  the values **MUST** be equal; mismatch **MUST** fail or be signalled as
  incompatible. Recapped in §9; enforced explicitly in §12.1 (compose) and §13
  (diff). The `retention_profile` is the field that §3.7 references for
  reservoir weights/size/caps.
- **§12.1 reservoir-carry under `compose()`** — composition now lists
  `C.stats.reservoir` explicitly: salience **re-derived** over merged counts,
  `structural_surprise`/`novelty` carried as **max**, entries excluded from the
  tail (§3.7.3). Resolves the multi-scale rare-salient memory gap (composed
  baselines previously had no reservoir).
- **§3.7 reservoir** (formalisation of the shipped reservoir): see §3.7.
- **§15 Re-derivation coordinate** (optional): `source_ref` (opaque resolvable
  handle + resolver-kind) + event-time `bounds` `{start_tick, end_tick}` make any
  window re-derivable to source (`raw = replay(source, bounds)`),
  canon-version-independent (guarantee 1); optional `canonicalization_version` +
  `config_hash` reproduce the fingerprint (guarantee 2). Window-level mandatory;
  optional bounded per-reservoir `within_window_ordinal`; composed = set of child
  coordinates. **Event-time-only bounds MUST** — replay resolvers prefix-monotone
  in the target, fetch resolvers stable event-time selection (replay form
  verified). Descriptive metadata; never feeds deterministic-content; recovered
  raw re-enters the bounding gate.
- §14 retained as a **Reserved tombstone** (formerly Sessions) so §15+ references
  stay stable.

### Removed
- **§14 Sessions** and the two `behavior` fields `sessions_observed` /
  `session_aware` — premature. Session-awareness is deferred to the planned
  `CORRELATION_ID` classification (salience epic §4.1); the bespoke session_key
  was an unsourced specialization and has been ripped from the implementation
  (insight-canon, insight-metalog). N-grams remain computed over the global event
  stream until session-scoping rides classification.

---

## [0.4.0] — 2026-05-24

### Added
- **`MetaLogDiff.tail_delta`** (optional) — the pair-wise difference of
  two documents' `stats.tail_summary` blocks, completing the 0.3.0
  tail-shape work: 0.3.0 added the per-window tail signal, 0.4.0 adds
  its diff. Each `tail_summary` field is reported as
  `previous_`/`current_`/`*_delta`. Emitted only when **both** inputs
  carry a `tail_summary`. A concentrating (`tail_entropy_bits_delta` < 0)
  and louder (`tail_max_rate_delta` > 0) tail is the signature of a
  chronic error emerging below `top_k` — invisible to `template_deltas`
  alone. Structured evidence, not a standalone alert. SPEC §13.5;
  `diff_version` → `0.4.0`.

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
