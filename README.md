# MetaLog Specification

> A compact, deterministic, vendor-neutral fingerprint format for
> bounded-size summaries of log streams.

**Status:** Draft — the `0.x` line. [`SPEC.md`](SPEC.md) declares the current version on its
first line and is normative; [`CHANGELOG.md`](CHANGELOG.md) is the dated release history.
**Editor:** the InSight project (reference implementation: `insight-metalog`)
**License:** Spec text — [CC-BY-4.0](LICENSE-SPEC). Reference schemas — [MIT](LICENSE).

---

## What is MetaLog?

A **MetaLog** is a bounded-size statistical and structural fingerprint
of a window of log behaviour. It answers a single question:

> *What was this log stream doing in the last N minutes — in a document
> bounded by the caps it declares, not by how many lines the stream carried?*

A MetaLog is **not** a log, **not** a metric, and **not** an alert.
It is a new primitive that sits between raw logs (high entropy, low
signal, expensive to store) and pre-defined metrics (low entropy, lossy,
defined ahead of time):

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Raw logs       │    │    MetaLog       │    │     Metrics      │
│   (GB / hour)    │ ─▶ │  (KB / window)   │ ─▶ │  (B / sample)    │
│  high entropy    │    │  defined by      │    │  defined ahead   │
│  defined nowhere │    │  the data itself │    │  of time         │
└──────────────────┘    └──────────────────┘    └──────────────────┘
       observable             compressible           queryable
```

A MetaLog is **derivable from raw logs** (one-way), **composable across
sources and windows**, **diff-able between consecutive windows**, and
**small enough to feed to humans, dashboards, alerting rules, and LLMs
without further reduction**.

---

## Why a spec?

A raw log stream grows with every line it carries, and so does what it
costs to keep and to search. The MetaLog response is *compress the
meaning, then store that*. A MetaLog is bounded by the **structure** a
window contains — its top templates, its salient tail, its n-grams, its cube cells, its
branching — each capped by a size the producer fixes before the window
starts and writes **in the document itself** (§11.1): `stats.top_k_size`
and `behavior.top_ngrams_size` in every document that carries their
block, the reservoir cap in every document of a producer that keeps a
reservoir (§3.7.2), the cube's budget and the branching cap where the
producer reports them (§16.10, §4.2) — and **not** by how many lines the
window carried. §11 makes that bound computable rather than quoted: §11.3's
formula prices a document from the caps it declares, and a document
that also carries `behavior` or `cube` pays for those blocks by the same
arithmetic. No size is published per line count, because a document's
size is set by its caps, its template mode and the content its entries
carry, and not by its line count (§11.5).
That is the value proposition: for every block whose cap the document
declares, the artifact stops growing where the stream does not. A block
whose cap it does not declare is bounded by nothing a consumer can read —
§4.2 places no cap on `behavior.branching` unless `branching_size`
declares one, and §11.5 names what no cap reaches.

> **That is a bound, not a measured ratio, and no ratio is quoted
> anywhere in this spec.** A compression ratio is a measurement,
> and it means nothing without the population it was measured on. This
> spec has none to cite — which is exactly why §11.5 asks producers to
> report their actual `envelope_bytes`, the only exact figure. An
> implementation that publishes a ratio should publish the corpus, the
> configuration and the run with it. **This spec learned that at its own
> expense:** until 0.10.0 it published a size target — *≤ 4 KB per
> MetaLog covering ≥ 1 M log lines* — that no implementation met, and it
> withdrew it ([`adr/0006`](adr/0006-no-size-per-line-count.md)).

For this primitive to be useful across vendors — for an SRE to be
able to switch their log analyzer without re-training their
dashboards, alerts, and LLM prompts — the format itself must be
**open, versioned, and vendor-neutral**.

That is what this spec aims to be, and today it is two of the three. It is
**open**: the text is published under CC-BY-4.0 and the schemas under MIT.
It is **versioned**: [`SPEC.md`](SPEC.md) declares its version, and the `0.x`
line may still break ([`GOVERNANCE.md`](GOVERNANCE.md)). It is vendor-neutral
by **design**, its fields describing log behaviour rather than any product, but
not yet in **practice**: it has one editor and one implementation. It will
claim neutrality outright once a second, independent implementation is
listed here.

---

## Documents

| File | Purpose |
|---|---|
| [`SPEC.md`](SPEC.md) | The normative specification. |
| [`RATIONALE.md`](RATIONALE.md) | Design decisions and the alternatives that were rejected. |
| [`schema/metalog.v0.schema.json`](schema/metalog.v0.schema.json) | JSON Schema for the v0 MetaLog envelope. |
| [`schema/metalog.v0.example.json`](schema/metalog.v0.example.json) | Worked example MetaLog. |
| [`schema/metalog_diff.v0.schema.json`](schema/metalog_diff.v0.schema.json) | JSON Schema for the v0 `MetaLogDiff` document (§13). |
| [`conformance/`](conformance/README.md) | §8 clauses 1, 4 and 6, and clause 2 over §2.2's `window`, made runnable — validate your documents against the shipped schemas. |
| [`CHANGELOG.md`](CHANGELOG.md) | Versioned history of the spec. |
| [`GOVERNANCE.md`](GOVERNANCE.md) | How the spec evolves; who can propose changes. |
| [`adr/`](adr/) | Decisions about the format, each with its argument and the alternatives rejected. |
| [`adr/0001-v1-freeze-policy.md`](adr/0001-v1-freeze-policy.md) | Conditions for freezing the first stable MetaLog version. |

---

## Status of v0

This is a **draft** — v0.x — published to reserve the term, the
schema, and the design intent before incumbents publish a
proprietary equivalent. Any MINOR release before v1.0 may break
compatibility (§9, [`GOVERNANCE.md`](GOVERNANCE.md) §6); 0.10.0 did, and
its [`CHANGELOG.md`](CHANGELOG.md) entry lists every break.

The first stable version (v1.0) is frozen only when the five conditions of
[`adr/0001`](adr/0001-v1-freeze-policy.md) hold, each verifiable by a third
party from this repository alone — among them two independent
implementations that interoperate, and published conformance vectors that
cover `compose()` and `diff()`. No implementation's delivery schedule is one
of them. After v1.0, breaking changes follow semver and
[GOVERNANCE.md](GOVERNANCE.md).

---

## Checking your implementation

§8 says "there is no central conformance authority. The schema is the test for
clause 1." [`conformance/`](conformance/README.md) is that test, shipped with the
standard so you can run it yourself, with checks for three more clauses that a
document decides on its own:

```
pip install -r conformance/requirements.txt
python3 conformance/metalog_validate.py --selftest                 # prove the tool has teeth
python3 conformance/metalog_validate.py my_metalogs.jsonl           # judge your MetaLogs
python3 conformance/metalog_validate.py --kind diff my_diffs.jsonl  # judge your MetaLogDiffs
```

It decides §8 clause 1 (the schema, which since 0.10.0 is closed, so a bare vendor
member fails it at any depth), clause 4 (every array and map whose cap the same
document declares, against that cap, and observed text against `max_text_bytes`),
clause 2 over §2.2's `window` only, and, on a `MetaLogDiff`, clause 6 (§13.2's
witness rule). It reports each kind of finding on its own and never adds them into
one number. It does **not** test clause 3, clause 5 or the rest of clause 2, and
every run prints the scope it covered.

---

## Reference implementations

| Implementation | Language | License | Status |
|---|---|---|---|
| **insight-metalog** ([repo](https://github.com/CodeRoasted/insight-metalog)) | C++23 | CodeRoast-owned package | Declares `metalog_version` **0.10.0** and `diff_version` **0.10.0** — producer, compose, and diff. Both stamps read one constant ([source at `17089a1`](https://github.com/CodeRoasted/insight-metalog/blob/17089a1d7aa715a36fdc615c249f96ed9c4cf25d/api/metalog.api.cppm#L990)), as §13.1.1 requires. Its **published documents meet §8 clauses 1, 4 and 6, and clause 2 over §2.2's `window`** — measured 2026-11-15 with [`conformance/`](conformance/README.md) at v0.10.0 over the [determinism evidence](https://github.com/CodeRoasted/coderoast-hub/blob/9bccc655e6971b71a208e5417acc6259be242b55/determinism/metalog.determinism_golden.txt) published for producer version 1.10.12: 35 MetaLog and 10 `MetaLogDiff` documents, zero schema violations, zero cap or text-cap violations, every `window` consistent, every `comparison_outcome` agreeing with its witness. Clauses 3 and 5 were not tested. The `diff_version` `0.6.0` stamp that §13.1.1 made non-conformant ([`adr/0004`](adr/0004-diff-version-is-the-spec-version.md); measured 2026-09-02 on 9 of 9 published diffs) is gone: all 10 published diffs declare `0.10.0`. Its vendor data rides in `extensions` under reverse-DNS keys, at both document roots and in `stats.top_k[]` — `ordinal_histograms`, `ruleset` and `service_edge_delta` among it (§7, [`adr/0003`](adr/0003-undescribed-wire-members.md)) — and since 0.10.0 closed both roots, §8 clause 1 decides that placement rather than leaving it to §7's MUST. It spells `run_outcome` in §2.5's lower-case vocabulary ([source at `17089a1`](https://github.com/CodeRoasted/insight-metalog/blob/17089a1d7aa715a36fdc615c249f96ed9c4cf25d/src/stats/wire_format.cpp#L138)); no published document carries the member yet. |
| *Your implementation here* | — | — | PRs welcome |

The spec is deliberately implementation-agnostic. Any language that
can serialise the JSON envelope and compute the required statistics
can produce conformant MetaLogs.

---

## Non-goals

To avoid scope creep and to keep the spec implementable, the
following are **explicitly out of scope** for MetaLog:

- **Log storage or retention.** MetaLog says nothing about where raw
  logs live. It is a derived artifact.
- **Log routing or transport.** Use Vector, Fluent Bit, OTel
  Collector, etc. MetaLog is what you produce *from* a log stream,
  not how you move logs around.
- **Alerting policy.** A MetaLog enables alerting; it does not
  prescribe alerts. Wire your own rules on top of MetaLog fields.
- **Querying raw logs.** A MetaLog is lossy by design. If you need
  the original log lines, keep them; MetaLog is not a replacement
  index.
- **Anomaly detection algorithms.** A MetaLog is the *input* to a
  detector. The detector itself is not part of this spec.
- **A wire protocol.** MetaLogs are JSON documents. Move them with
  HTTP, Kafka, files, object storage, or any transport that fits your system.

---

## How to contribute

This spec is in the *reserve-the-term* phase. The most useful
contributions right now are:

1. **Implement the v0 envelope in your favourite language** and
   open a PR adding it to the [reference implementations](#reference-implementations)
   table.
2. **Open issues** with concrete log streams where the v0 schema
   does not capture something you'd want a MetaLog to express.
3. **Argue with [`RATIONALE.md`](RATIONALE.md)**. Every rejected
   alternative is documented; if you think one was wrong, say so on
   the issue tracker with a specific scenario.

Process and review rules live in [`GOVERNANCE.md`](GOVERNANCE.md).

---

## Trademark / naming note

"MetaLog" is used here as a generic technical term for the artifact
described by this spec. Any vendor may produce or consume
spec-conformant MetaLogs and describe their tool as "MetaLog
producer" or "MetaLog consumer". The spec is permissively licensed
precisely so this term can become standard usage.
