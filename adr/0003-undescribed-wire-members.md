# ADR 0003 — Disposition of the four undescribed wire members

- **Status:** Accepted — editor (Emmanuel Prunet), 2026-08-22
- **Date:** 2026-08-22
- **Spec version affected:** none yet — acceptance lands as a 0.9.0 additive release
- **Related:** SPEC §7 (placement rule, v0.8.0), §2.4 (processing identifiers),
  §3.7 (reservoir), §3.8 (`component` — the adoption precedent), §13
  (`MetaLogDiff`), GOVERNANCE §2/§3

## Context

SPEC §7 (v0.8.0) makes `extensions` the **only** carrier of non-standard
members: a producer **MUST NOT** write vendor data as a bare member of a
standard object, at any depth, including objects the schema does not currently
close. The reference implementation's wire, measured 2026-08-22, can emit four
members that no spec text and no schema describe:

| member | where | what it carries |
|---|---|---|
| `ruleset` | MetaLog root | the identity of the analysis rule set active when the document was produced: a content hash (`semantic_identity`) plus a `packages[]` list of name/version pairs |
| `run_outcome` | MetaLog root | the terminal verdict of the run the window covers — `"success"` / `"failure"` / `"unstable"` / `"aborted"`, derived from the observed stream, omitted when no verdict was observed |
| `reservoir_delta` | MetaLogDiff root | membership change of the standard §3.7 reservoir: new/vanished rare-salient entries, plus severity-frontier crossings (a template moving into or out of `{ERROR, FATAL}`) |
| `service_edge_delta` | MetaLogDiff root | the pair-wise diff of a service-topology block the producer carries in root `extensions` |

**None of the four appears on a published surface today** — measured 2026-08-22
over the determinism evidence (17 documents) and the two published diff
documents: zero undescribed members. This ADR disposes of the wire *before* it
is published, not after. But every one of the four is emitted whenever its data
is populated, so the first published document from a run that has a verdict, a
rule set, or a reservoir change will carry bare members in violation of §7's
placement rule.

## The two branches

For each member exactly one of two dispositions is coherent with §7:

- **Adopt** — describe it in `SPEC.md` and the schema as an optional standard
  field. Additive under GOVERNANCE §2: MINOR bump, editor merges. This is the
  path `component` and `field_histogram_deltas` took in 0.8.0.
- **Relocate** — the member is vendor data; §7 already forbids the bare form,
  so the producer moves it under a reverse-DNS key in `extensions`. This is
  the path `ordinal_histograms` took after 0.8.0 granted the
  `stats.top_k[].extensions` placement.

The test this repository already applies (0.8.0 changelog; the README
implementation row): **adopt when the member's semantics can be frozen
vendor-neutrally today; relocate when it rides an unfrozen ladder or a
vendor-shaped model.**

## Decision

### 1. `run_outcome` — adopt (0.9.0)

A closed, low-cardinality verdict vocabulary for the run a window covers.
Vendor-neutral by inspection: `success` / `failure` / `unstable` / `aborted`
is the vocabulary CI systems themselves publish, and any producer fingerprinting
a CI or batch log can derive it. Same species as §3.8 `component`: a
categorical label the observed stream carries about itself, freezable now.

Normative points to write at adoption:

- **MUST** be derived from the observed events, never from producer state.
- **MUST** be omitted when no verdict was observed — there is no `"unknown"`
  wire value, so absence semantics are version-safe (absence = no verdict /
  pre-adoption producer).
- Consumers **MUST NOT** read absence as `success`.
- The enum is closed; a producer with a verdict outside it uses `extensions`.
- Diff relevance is first-class: whether two windows straddle a green→red
  boundary changes how every delta in a `MetaLogDiff` should be read.

### 2. `reservoir_delta` — adopt (0.9.0)

Not vendor data at all: it diffs the **standard** §3.7 reservoir, and §13
already carries a delta for every other `stats` block (`template_deltas`,
`tail_delta`, `field_histogram_deltas`). Without it, a §13 consumer cannot see
rare-salient membership change — structurally the same gap
`field_histogram_deltas` closed in 0.8.0. The severity frontier it reports
against (`{ERROR, FATAL}`) is already normative vocabulary in this spec.
Adoption is a new §13 subsection plus schema `properties` — additive, since
the diff root is open.

### 3. `ruleset` — relocate to `extensions`

The generic need — "these two documents are comparable only if produced under
the same processing contract" — is already owned by §2.4, whose mechanism is
deliberately an **opaque string**. The honest vendor-neutral form of a
rule-set identity would be exactly one more opaque identifier; everything this
member carries beyond that (a `packages[]` list of name/version pairs) is one
vendor's distribution model, and freezing it would standardise packaging
metadata no other implementer has. Disposition: `fr.coderoast.ruleset` in root
`extensions`. If a second implementer later demonstrates the generic need, the
additive path is a third §2.4-species opaque identifier — not this block.

### 4. `service_edge_delta` — relocate, which requires granting `extensions` at the `MetaLogDiff` root (0.9.0)

The data it diffs already lives in root `extensions` as vendor topology; a
diff of vendor data is vendor data. But the `MetaLogDiff` document type has
**no `extensions` member at all** — §7's placement table names only the
MetaLog document root and `stats.top_k[]`. This member is precisely the
evidence §7 says a placement grant must wait for: grant `extensions` at the
diff root (additive), and the producer relocates the block under
`fr.coderoast.service_edge_delta`. Until the grant lands, the member has no
legal home — which is this ADR's strongest argument for not deferring it.

## Alternatives considered

### A. Adopt all four

Rejected. `ruleset` freezes one vendor's packaging model into a neutral
standard, and its comparability role duplicates §2.4 with a second, structured
mechanism — two ways to say "same contract" is one too many.

### B. Relocate all four

Rejected. It moves standard-shaped data (`reservoir_delta` diffs a block this
spec owns) behind a vendor key, guaranteeing every future implementer invents
an incompatible spelling of the same delta — the exact failure `extensions`
exists to prevent for *vendor* data, inflicted on *standard* data.

### C. Leave the wire as it is and describe nothing

Rejected. §7's placement rule would then be a MUST the reference
implementation violates on first contact with populated data, and §8 clause 1
cannot catch it (both roots are open, so the members are legal-but-undescribed,
invisible to the schema test). A rule only prose can see must at least have
prose that names the known offenders' disposition.

## Consequences

- Acceptance is a **0.9.0 additive release**: describe `run_outcome` (§2.x)
  and `reservoir_delta` (§13.x) in spec + schema; grant `extensions` at the
  `MetaLogDiff` root (§7 table + diff schema).
- The reference implementation then updates its wire in one pass: `ruleset` and
  `service_edge_delta` move under `fr.coderoast.*` keys; `run_outcome` and
  `reservoir_delta` stay where they are, now described.
- Until 0.9.0, the four members remain unpublished-but-emittable; the README
  implementation row discloses this and points here.
- Nothing in this ADR changes v0.8.0 text; it can be accepted or amended
  without touching the cut.

## Open questions

- Should `run_outcome` adoption also define its interaction with `compose()`
  (§12) — two inputs with different verdicts? The conservative proposal:
  the composed document omits it unless all inputs agree.
- Does `reservoir_delta`'s `frontier_crossings` list belong inside the block
  or as a §13 sibling? Proposal: inside — it is derived from the same
  membership comparison.
