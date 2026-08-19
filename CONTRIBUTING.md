# Contributing to the MetaLog Spec

Thanks for considering a contribution. The spec is in its draft
(0.x) phase, which means we want feedback now more than ever and
we'd rather have a frank disagreement on an issue than discover
the same disagreement after v1.0 freezes.

## Ways to help, in priority order

### 1. Implement the v0 envelope in your favourite language

A second implementation, in any language, is the single most
useful contribution. It surfaces ambiguities in the spec text that
a single-implementation reading misses.

When you have something runnable, open a PR adding it to the
"Reference implementations" table in [`README.md`](README.md). We
ask for:

- A link to your repo
- The licence
- Which optional fields it emits / consumes
- A note on conformance status (does it validate against the
  shipped JSON Schema?)

### 2. Open issues with concrete log streams the spec fails

If you have a real log stream where the v0 schema cannot capture
something you'd want a MetaLog to express, open an issue with:

- A few representative log lines (redacted)
- What you wish the MetaLog could say about them
- What you tried to express via the spec and why it didn't fit

This is how the spec earns its keep. Please do this.

### 3. Argue with `RATIONALE.md`

Each design decision documents the alternatives that were
rejected. If you think a rejection was wrong, open an `rfc:` issue
(see [`GOVERNANCE.md`](GOVERNANCE.md)) with a specific scenario
where the rejected alternative would have served better.

### 4. Editorial fixes

Typos, broken links, unclear wording — open a PR directly. Editor
merges these on sight.

---

## What *not* to do

- **Don't add fields without an issue first.** New fields are
  additive changes and need a MINOR bump; we want the discussion
  in an issue before the PR.
- **Don't propose vendor-specific extensions in the core schema.**
  Use the `extensions` object with a reverse-DNS prefix.
- **Don't implement a transport layer in this repo.** MetaLogs
  are JSON; transport is out of scope (see [`SPEC.md` §1](SPEC.md#1-definitions)
  and [`RATIONALE.md` §R7](RATIONALE.md#r7-why-no-wire-protocol)).

---

## Process

1. Fork, branch, PR.
2. CI runs `conformance/metalog_validate.py --selftest` and then
   validates the example file against the shipped schema. Run both
   locally first — see [`conformance/README.md`](conformance/README.md).
3. Editor (or a reviewer) reviews. Additive changes get merged
   after one approval; breaking changes follow the RFC process in
   [`GOVERNANCE.md`](GOVERNANCE.md).
4. Merged changes update `CHANGELOG.md`.

---

## Code of conduct

Be civil. Argue with the design, not the person. Anyone making
this place hostile gets blocked, no appeals.
