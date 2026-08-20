# MetaLog Spec — Governance

> While the spec is in its `0.x` draft phase, governance is light and
> the editor (currently the InSight project maintainers) has final say
> on changes. This document describes how that evolves.

---

## 1. Roles

- **Editor** — Maintains the spec text, the JSON schema, and the
  changelog. Has final merge authority during 0.x. Currently the
  InSight project maintainers.
- **Implementer** — Anyone shipping a producer or consumer of MetaLog
  documents. Implementers may open issues and PRs.
- **Reviewer** — A trusted contributor (added by editor consensus)
  who may approve PRs but not merge breaking changes alone.

[`MAINTAINERS.md`](MAINTAINERS.md) records the current review **areas** and the
project responsible for each. **It names no individual reviewer, and there is no
reviewer roster today** — the spec is edited by a single editor. §2 states what
that means for each change type; a reader should not have to infer it.

---

## 2. Change types and process

| Change type | Examples | Process during 0.x | Process at 1.0+ |
|---|---|---|---|
| **Editorial** | Typo, wording clarification, additional example | Editor merges. | Editor merges. |
| **Additive** | New optional field, new enum value, new extension prefix | Editor merges. MINOR bump. **The 1-reviewer approval below activates once a reviewer roster exists.** | Editor merges after 1 reviewer approval. MINOR bump. |
| **Breaking** | Remove a field, change a field type, change `template_id` algorithm | Editor merges after RFC issue + 14-day comment window. MAJOR bump (or MINOR during 0.x). | Requires RFC + 30-day comment window + at least 2 reviewer approvals. MAJOR bump. |
| **Profile** | "Streaming MetaLog", "Edge MetaLog" subset profiles | Same as breaking. | Same as breaking. |

An **RFC issue** is a GitHub issue tagged `rfc:` containing:

1. The problem being solved, with at least one concrete example.
2. The proposed change, expressed as a diff against `SPEC.md`.
3. Alternatives considered (link to or summarise prior discussions).
4. Migration impact for existing implementations.

---

## 3. Reference implementation conformance

The InSight reference implementation is the **first conformance test
oracle** but is not authoritative over the spec text. If the spec
and the reference implementation disagree, the spec wins, and the
reference implementation is treated as buggy.

A future test suite (`test/golden/`) will provide language-agnostic
input → output golden pairs that any implementation can run.

---

## 4. Trademark and naming

"MetaLog" as used in this spec is a generic technical term. The
spec is licensed under CC-BY-4.0 specifically so any vendor may
implement and market a "MetaLog producer" or "MetaLog consumer"
without permission.

The editor will **not** pursue trademark on the term "MetaLog" in
the observability space. If a third party attempts to do so, the
editor will publish prior-art evidence (this spec, the InSight
implementation, the GitHub commit history) to defend the term as
generic.

---

## 5. How to escalate disagreement

1. Comment on the relevant PR or issue.
2. If unresolved, open an `rfc:` issue with the alternative
   proposal.
3. If still unresolved after the comment window, the editor decides
   and documents the rationale in the merged PR.

There is no appeal process during 0.x. After 1.0, a steering
committee structure will be defined here if the implementer base
warrants it.

---

## 6. Versioning policy recap

- `0.x.y` — draft. MINOR may break.
- `1.0.0` — first stable. SemVer applies strictly thereafter.
- `1.x.y` — additive only. Any breaking change waits for `2.0.0`.
- The MAJOR field of `metalog_version` in the schema must equal
  the MAJOR of the spec.
