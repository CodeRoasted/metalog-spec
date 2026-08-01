# metalog-spec — the MetaLog wire specification (spec text CC-BY-4.0 · schemas MIT)

The normative definition of the MetaLog format: a bounded-size, deterministic,
**vendor-neutral** fingerprint of a window of log behaviour. This repo is
**public** and dual-licensed — `SPEC.md` + prose under `LICENSE-SPEC`
(CC-BY-4.0), `schema/` under `LICENSE` (MIT). It is a published standard that
happens to be edited here, not a component of a product.

## Arrival

- No build, no tests, no `malf` — the artifacts are `SPEC.md`, `schema/*.json`,
  and the prose around them. Changing a schema means re-checking the example.
- `SPEC.md` is **normative**; `RATIONALE.md` holds the *why* behind settled
  choices; `adr/` holds decisions with their argument; `CHANGELOG.md` is the
  version record. `GOVERNANCE.md` rules what a change costs (editorial /
  additive / breaking / profile) and `CONTRIBUTING.md` is the outside door.
- The reference implementation is `insight-metalog`. It is the first
  conformance oracle and is **not authoritative over the spec text** — when the
  two disagree, the spec wins or the spec changes, never silently either way.

## Local traps

- **`adr/` HERE IS LEGITIMATE — never delete it under the workspace rule that
  "the only ADRs live in the CodeRoast superproject".** That is an *ownership*
  rule, and this repo is a **different owner**: an external implementer reading
  a CC-BY format cannot open a private superproject shelf, so a decision about
  the format must travel with the format. Deleting these once cost a live
  decision and was reverted. The reciprocal also holds: a decision about the
  *product* has no business here.
- **This is a PUBLIC, vendor-neutral surface — never name product internals in
  it.** Naming the reference implementation as a motivating consumer is ordinary
  standards practice; gating the format's own version on one vendor's internal
  delivery milestones is a category error, and publishing the names of private
  components is a leak. Both have happened here; check a new paragraph against
  "could a stranger implementing this format evaluate this sentence?".
- **These ADRs are `ADR 000N`, NOT the superproject's `ADR-n` registry form**,
  and nothing outside this repo cites them. Do not "canonicalize" them into the
  registry grammar: the number space is this repo's, and the two series are
  unrelated despite looking alike.
- The superproject's planning tiers (`WIP` / `ROADMAP` / `DONE`) do **not** extend here. <!-- docs-lint: allow names the tier only to disclaim it -->
  Spec work in flight is an issue or a PR, per `GOVERNANCE.md`.
