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

> *What was this log stream doing in the last N minutes, in 4 KB or less?*

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

The observability industry stores logs at $0.50–$3 per GB ingested and
queries them with full-text search. This works at small scale and
collapses at large scale: companies routinely drop logs after 7 days
because retention is unaffordable, then have no incident forensics.

The industry response has been *more storage, more indexes, more
dashboards*. The MetaLog response is *compress the meaning, then store
that*. A MetaLog is bounded by the **structure** a window contains —
its top templates, its n-grams, its cube cells, each capped by a
declared size (`top_k`, §3.1; `top_ngrams_size`, §4; the cube's closure,
§16) — and **not** by how many lines the window carried. §11 sets the
design target that follows from it: **≤ 4 KB per MetaLog covering ≥ 1 M
log lines**. That is the value proposition: the artifact stops growing
where the stream does not.

> **That is a target and a bound, not a measured ratio, and no ratio is
> quoted anywhere in this spec.** A compression ratio is a measurement,
> and it means nothing without the population it was measured on. This
> spec has none to cite — which is exactly why §11 asks producers to
> report `envelope_bytes` "so consumers can track the compression ratio
> achieved on real workloads". An implementation that publishes a ratio
> should publish the corpus, the configuration and the run with it.

For this primitive to be useful across vendors — for an SRE to be
able to switch their log analyzer without re-training their
dashboards, alerts, and LLM prompts — the format itself must be
**open, versioned, and vendor-neutral**.

That is what this spec is.

---

## Documents

| File | Purpose |
|---|---|
| [`SPEC.md`](SPEC.md) | The normative specification. |
| [`RATIONALE.md`](RATIONALE.md) | Design decisions and the alternatives that were rejected. |
| [`schema/metalog.v0.schema.json`](schema/metalog.v0.schema.json) | JSON Schema for the v0 MetaLog envelope. |
| [`schema/metalog.v0.example.json`](schema/metalog.v0.example.json) | Worked example MetaLog. |
| [`conformance/`](conformance/README.md) | §8 clause 1, made runnable — validate your documents against the shipped schemas. |
| [`CHANGELOG.md`](CHANGELOG.md) | Versioned history of the spec. |
| [`GOVERNANCE.md`](GOVERNANCE.md) | How the spec evolves; who can propose changes. |
| [`adr/0001-v1-freeze-policy.md`](adr/0001-v1-freeze-policy.md) | Conditions for freezing the first stable MetaLog version. |

---

## Status of v0

This is a **draft** — v0.x — published to reserve the term, the
schema, and the design intent before incumbents publish a
proprietary equivalent. The format **will** change in incompatible
ways before v1.

The first stable version (v1.0) will land alongside the InSight
reference implementation when the `insight-metalog` producer and
downstream consumers have enough compatibility evidence
to freeze the schema. After v1.0, breaking changes follow semver and
[GOVERNANCE.md](GOVERNANCE.md).

---

## Checking your implementation

§8 says "there is no central conformance authority — the schema is the test".
[`conformance/`](conformance/README.md) is that test, shipped with the standard so
you can run it yourself:

```
pip install -r conformance/requirements.txt
python3 conformance/metalog_validate.py --selftest        # prove the tool has teeth
python3 conformance/metalog_validate.py my_metalogs.jsonl  # judge your documents
```

It reports schema violations separately from members that an *open* container
permits but no schema describes — the second is legal, and conflating the two
misprices both. It covers **§8 clause 1 only**; clauses 2–4 are not tested, and the
tool says so on every run.

---

## Reference implementations

| Implementation | Language | License | Status |
|---|---|---|---|
| **insight-metalog** ([repo](https://github.com/CodeRoasted/insight-metalog)) | C++23 | CodeRoast-owned package | Declares `metalog_version` **0.8.0** — producer, compose, and diff. Its **published documents meet §8 clause 1** — measured 2026-08-22 with [`conformance/`](conformance/README.md) over both published surfaces: the [determinism evidence](https://github.com/CodeRoasted/coderoast-hub/blob/main/determinism/metalog.determinism_golden.txt) (17 documents) and the two published diff documents — zero schema violations, zero undescribed members. The member that failed here before (`stats.top_k[].ordinal_histograms`, bare in a closed object) now rides in `stats.top_k[].extensions` under a reverse-DNS key, per §7: its bins ride an unfrozen ladder, so it stays vendor data until an RFC freezes the ladder. The producer's full wire can still emit two members no spec text describes — `run_outcome` (MetaLog root) and `reservoir_delta` (MetaLogDiff root); neither reaches a published surface today, and their disposition is decided in [`adr/0003`](adr/0003-undescribed-wire-members.md) (Accepted, 2026-08-22): both will be described in a 0.9.0 additive release. The two vendor-shaped members that ADR relocates — `ruleset` and `service_edge_delta` — now ride in `extensions` under reverse-DNS keys; the diff-root `extensions` container itself stays legal-but-undescribed until 0.9.0 grants that placement in §7's table. |
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
