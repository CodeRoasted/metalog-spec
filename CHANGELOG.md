# Changelog

All notable changes to the MetaLog specification are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The spec follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice:** during the 0.x line, MINOR version bumps may
> still introduce incompatible schema changes. After 1.0, semver
> applies strictly.

---

## [0.9.0] — unreleased

**Additive** under [`GOVERNANCE.md`](GOVERNANCE.md) §2 — new optional fields only.
No existing field changes type, becomes required, or is removed; **no conformant
0.8.0 document becomes invalid**, and a 0.8.0 producer stays legal.

### Added

- **`stats.reservoir_size`, `behavior.branching_size`, `cube.cell_budget`**
  (uint, optional) — the cap a producer applies to `stats.reservoir` (§3.7),
  `behavior.branching` (§4.2) and `cube.cells` (§16.10). `stats.top_k_size` and
  `behavior.top_ngrams_size` already declared theirs; these three blocks were
  bounded in the prose and undeclarable in the document, so a consumer could
  neither price them nor check them. `retention_profile` (§2.4) does not cover
  this: it is opaque, and it answers comparability, not size.

  **`behavior.branching` is the one block this spec still places no cap on.**
  §4.2 gains the field but keeps the posture explicit: **omitting it means the
  producer declares no cap**, which is legal, and a size-constrained consumer
  must read the omission that way rather than assume a default.

- **`MetaLogDiff.extensions`** — the §7 container, granted at a **third
  placement**: the `MetaLogDiff` document root. The diff document type carried no
  `extensions` member at all, so vendor data on a diff had **no legal home** — §7
  forbids the bare member at any depth, and the only placements its table named
  were on the other document type. Two consequences were already live in the text:
  §13.2 tells producers they **MAY** report a truncation cap in
  `extensions.org.metalog.deltas_truncated_at` **at this root**, a MAY naming a
  placement the spec had not granted; and a producer with any per-diff vendor datum
  had to choose between a bare member (forbidden) and dropping the datum.

  The grammar is **duplicated** into `metalog_diff.v0.schema.json`'s `$defs`
  rather than `$ref`-ed across files. Both schema files are independently
  consumable — §8 invites downloading one alone — and a cross-file reference
  cannot be resolved offline.

  **What this does not do, stated because a grant reads like enforcement.** The
  diff root is **open** (it declares an `additionalProperties` that constrains
  nothing), so a bare vendor member *beside* the
  container still validates; the grant fixes where vendor data **belongs**, not
  what the schema **detects**. Making §7's placement rule decidable at a root means
  closing that root, which is a *breaking* change under `GOVERNANCE.md` §2 and is
  not in this release.

- **`run_outcome`** (string, optional, MetaLog root) — the terminal verdict of the
  run a window covers, described in the new **§2.5**: a **closed** enum of
  `success` / `failure` / `unstable` / `aborted`. This is an **adoption, not a
  relocation** — the member is standard-shaped and stays exactly where it is. Same
  species as `level` and §3.8's `component`: a low-cardinality label the observed
  stream carries *about itself*, freezable vendor-neutrally today because a
  terminal verdict is what CI and batch systems publish about their own runs.

  Normative points worth reading before emitting it. It **MUST** be derived from
  the **observed events**, never from producer state or an out-of-band control
  plane — a field sourced from outside the window's bytes is not re-derivable from
  them. It **MUST** be **omitted** when no verdict was observed: there is **no**
  wire value for "unknown", which is exactly what makes absence mean the same
  thing in every version of this spec, including documents written before this
  one. Consumers **MUST NOT** read absence as `success`. Under `compose()` (§12) a
  composed document **MUST NOT** carry a verdict unless every input that carries
  one carries the same value — a window spanning a green run and a red one has no
  single verdict, and omitting is the safe direction precisely because absence
  asserts nothing.

  `aborted` is the value with a consequence attached: it says the observed stream
  is **truncated**, so every count in that document is a count over a stream that
  stopped early, and a template that appears to have vanished may simply never
  have been reached.

  **The values are lower-case and case-sensitive**, like every other vocabulary
  this spec *mints* (`sketch_type` §6, `cube.axes[].kind` §16.2) and deliberately
  unlike `level`, whose values are the observed stream's own tokens and are not
  minted here.

- **`MetaLogDiff.reservoir_delta`** (object, optional, diff root) — rare-salient
  membership change between the two documents' `stats.reservoir` blocks, described
  in the new **§13.7**. The second **adoption**, not a relocation: it diffs a block
  this spec owns (§3.7), and §13 already carries a delta for every other `stats`
  block — `template_deltas` for `top_k`, `tail_delta` for `tail_summary`,
  `field_histogram_deltas` for the per-slot histograms. Without it a consumer
  cannot see change in the block that exists precisely to keep the
  rare-but-important **single**: a lone fatal that starts appearing, or stops, moves
  no count large enough to surface anywhere else in a diff. Structurally the same
  gap `field_histogram_deltas` closed in 0.8.0.

  Three optional lists — `new_salient`, `vanished_salient`, `frontier_crossings` —
  each omitted when empty, the block omitted when all three are, every list sorted
  by `template_id`.

  **The rule worth reading before implementing it: membership is decided over
  `top_k` ∪ `reservoir`, never over `reservoir` alone.** A template that was
  frequent enough for `top_k` in one window and only salient enough for the
  `reservoir` in the other has not appeared or disappeared — it moved between two
  retention mechanisms. Differencing the reservoirs alone reports that migration as
  a birth *and* a death, and both are false. The two blocks are disjoint by
  construction (§3.7.1), so the union needs no precedence rule.

  `frontier_crossings` reports a template present on **both** sides whose `level`
  crossed the `{ERROR, FATAL}` failure frontier — the same absolute frontier §16.10
  forbids banding across. Frontier membership **MUST** be a **set test**, never an
  ordinal compare against `ERROR`: a `level` ladder with any value above `FATAL`
  would otherwise classify it as a failure by accident of ordering. `direction`
  (`up` / `down`) is oriented `previous` → `current` and is **polarity-mute** — a
  template leaving `ERROR` because its code path stopped running is not a repair,
  and this spec cannot tell the two apart, so the escalation/recovery reading stays
  the consumer's.

  `count` and `salience` **MUST** be copied from the document the entry comes from,
  never re-derived at diff time; `salience` is comparable across the pair only
  because §2.4's gate already requires a matching `retention_profile`. And §3.7.2.1
  applies in full: across a template-text change the delta is **re-selection, not
  signal**, and consumers **MUST NOT** read it as changed behaviour.

- **`MetaLogDiff.cube_diff.axes[].band_floor`** — the ordinal-axis collapse stamp,
  **standard in `metalog.v0.schema.json` since v0.8.0** and absent from the diff
  schema's mirror of `$defs/cube_axis`. A schema lag (`GOVERNANCE.md` §3), and a
  live one: §13.6 requires `cube_diff.axes` to **equal** both inputs' `cube.axes`,
  and §16.10 stamps a collapsed cube's axes with `band_floor` — so a diff of two
  collapsed cubes was **rejected by the diff schema while both of its inputs
  validated**. Measured against the shipped v0.8.0 pair: the axis
  `{"name": "level", "kind": "categorical", "band_floor": 2}` is accepted by
  `metalog.v0.schema.json` and rejected by `metalog_diff.v0.schema.json` on
  `additionalProperties`. Nothing becomes invalid — the mirror only begins
  admitting what its source already admits — and no published document hit it,
  because no published diff carries a `cube_diff`.

### Changed

- **§11 Size budget is now a formula, not a table of numbers** (informative
  section, no normative effect). The previous table priced `stats.top_k` alone
  and indexed the whole envelope on `k`, which under-counted every document
  carrying another block — a `reservoir` entry costs 1.5–2.5× a `top_k` entry,
  and the cube's closed-cell budget dominates every other term combined. §11 now
  gives the per-entry costs measured on
  [`schema/metalog.v0.example.json`](schema/metalog.v0.example.json), the sum
  over blocks that prices a document, and worked examples at three
  configurations. Any single figure published here would be a figure for one
  producer's configuration, and would rot the first time that configuration
  moved.
- **§11.5 scopes the "≤ 4 KB per MetaLog covering ≥ 1 M log lines" target to the
  `stats`-only document** — no `reservoir`, no `behavior`, no `cube`. The target
  is unchanged and still reached at `top_k_size ≤ 32` inline or `≤ 64` id-only;
  what changes is that its scope is now stated instead of implied.
- **§8 clause 4 generalised from `top_k` to every declared cap**, and its
  testability stated: the clause is *not* reachable from the schema —
  `maxItems` takes a constant, while the bound is the value of a sibling field —
  but it is decidable from the document alone.
- **§13.2's satisfying set gains `reservoir_delta`.** The clause requires a diff to
  carry at least one signal field, and the new member is one — omitting it would
  have made a diff whose only finding is a reservoir membership change formally
  non-conformant. The enumeration is loosened, never tightened, so no document
  changes verdict. It stays a hand-kept list and still lags the schema by three
  members (`stability_score`, `field_histogram_deltas`, `cube_diff`) — that
  correction belongs with the clause's rewrite, not with this adoption.
- **§7's claim about what enforces its placement rule is corrected.** The
  paragraph said a bare vendor member "is a conformance failure §8 clause 1
  detects". That holds inside a **closed** object and is false at either
  **document root**: both are **open**, so a bare member there
  validates, and `conformance/metalog_validate.py` reports it as
  *legal-but-undescribed* — a report, not a verdict. §7 now separates the two
  cases and names closing a root as the breaking change it would be. **No
  normative effect:** the MUST is unchanged; what changes is the spec's claim
  about what enforces it.
- **§3.5.2's wire-emission note was half wrong, and the wrong half was the one a
  reader prices a document by.** It said the reference producer computes
  `param_histograms` but does **not emit them on the wire**. It does — the block is
  serialised inside every `top_k` entry with tracked slots whenever the producer's
  per-template slot-tracking cap is above zero, and the shipped batch configurations
  set it there, so published documents carry it. The note also gated emission on a
  magnitude-aware ordinal metric arriving first; that concern was answered by routing
  declared-ordinal slots to a different carrier, not by withholding the block, and a
  status note in this spec should not be gated on any one implementation's delivery
  schedule in the first place. §11's own size budget already priced
  `param_histograms` as a live wire cost, so the two sections disagreed. The other
  half stands and is now stated separately: `MetaLogDiff.field_histogram_deltas` is
  computed on every diff and **not** serialised — a conformant choice, since §13.2
  makes the member optional. **No normative effect:** the key-sorted `value_counts`
  MUST is unchanged and no field's status changes; what changes is the spec's
  description of what the reference producer puts on the wire.

### Conformance tooling

- **`conformance/metalog_validate.py` now decides §8 clause 4** (`CAP-EXCEEDED`,
  exit 1), which it previously declared unchecked on every run. The cap/array
  pair set is **derived from the schema** — an integer `<x>_size` whose sibling
  `<x>` is an array — so a pair added tomorrow is checked on arrival;
  `cube.cell_budget` is the single declared exception, named for §16.10's BUDGET
  rather than for its array. Objects under `extensions` are skipped: vendor space
  is not this standard's to adjudicate.
- New self-test control **`declared-cap-violation`**, with a fixture that is
  **schema-valid and cap-violating** — the case a schema-only validator reports
  CONFORMANT. It carries violations at two locations (`stats` and `behavior`) so
  that a `top_k`-only checker reds, and a vendor `shard_size`/`shard` pair under
  `extensions` that must **not** be reported.
- New self-test fixture **`invalid/unprefixed_extension_key.diff.json`** for the
  diff-root grant, proving it in both directions inside one document: an
  unprefixed key *inside* `extensions` is rejected (the container's grammar is
  enforced at this root now that the root describes it), a reverse-DNS key beside
  it validates, and a bare vendor member at the root itself is reported
  legal-but-undescribed — the limit the grant does not close. Measured: reverting
  the grant reds **exactly this fixture, 1 of 14**, in all three directions;
  granting the property without wiring it to `$defs/extensions` reds it too.
- **Two self-test fixtures for the two adoptions**, each proving its member in both
  directions and each mutation-measured at 1 of 16.
  `invalid/run_outcome_vocabulary.metalog.jsonl` carries two documents because one
  document carries one verdict: `failure` must validate and must not be reported
  undescribed, `SUCCESS` must be rejected. It is the only fixture in the set that
  exercises an `enum` violation at all — every other finding here is
  `additionalProperties`, `required` or `pattern` — and `SUCCESS` is not an invented
  mistake but exactly what the reference implementation emits today.
  `invalid/reservoir_delta_direction.diff.json` puts a fully conformant
  `new_salient` entry beside a `frontier_crossings` entry spelling `direction` as
  `increased`, so the report must discriminate rather than reject the block.
  Measured on all four ways a wrong adoption could look right: removing either
  property, or granting it as an unconstrained `string`/`object`, reds exactly the
  matching fixture and nothing else.
- **`--selftest` now asserts the two schemas' shared `$defs` agree**, before any
  fixture runs. Both files are independently consumable and the validator resolves
  only in-document pointers, so a grammar both need is *duplicated* rather than
  cross-referenced — and a duplicate that can drift publishes one name with two
  meanings, invisibly to whoever downloaded a single file. Every name present in
  both files must agree in every keyword but `description` (excluded so a copy can
  name its source); the set is derived from the artifacts, never enumerated. A
  drift is **exit 2**, not exit 1: the standard's own artifacts disagree, and no
  verdict about anyone's documents is honest until they don't. Run against the
  shipped v0.8.0 pair, it reds — which is how the `band_floor` lag above was found.
- **`--selftest` now requires every object position in both schemas to declare its
  own closure**, immediately after the `$defs` mirror check and before any fixture
  runs. Three dispositions are legal and there is no fourth: `additionalProperties:
  false`, a **constraining** value schema (a map — closed over its values, never
  over its key set), or `{"description": "<why it is open>"}`. An **absent**
  `additionalProperties` is a defect, because absence is not a disposition:
  `provenance[].source` and `attribution.sketch_params` are byte-identical
  `{"type": "object"}` and mean opposite things — the first is a standard object
  whose members §12.4 names, the second a map whose keys are data. Nothing in the
  schema separates them; only the prose does, so the census of what is open cannot
  be maintained by reading the schema and is enforced instead. A bare `true` is
  refused because it is the one spelling with nowhere to put the reason, and
  accepting a **node-level** `description` in its place would have passed both
  document roots on sentences that describe the document type and say nothing about
  its openness. Position set derived from the artifacts; in-place applicators
  (`if`/`then`/`else`/`not`, `allOf`/`anyOf`/`oneOf` branches) are excluded because
  they constrain the position they sit in rather than being one — closing an `if`
  would change the condition. Run against the shipped v0.9.0 pair before the
  declarations below, it reds at **7 of 49** positions. Exit 2, like a `$defs`
  drift.

- **All seven positions now declare their closure, and nothing closes.** Both
  document roots, `provenance[].window`, and the diff's `current.window` and
  `previous.window` were spelled `additionalProperties: true` and now carry the
  same openness with its reason attached; `attribution.sketch_params` declares that
  it is a **map** (§6 makes the parameter set depend on `sketch_type`, and
  `additionalProperties: false` on it would admit only the empty object while §6
  makes the field **required** — every document carrying `attribution` would become
  invalid); `provenance[].source` declares that it is a standard **object** whose
  members are not yet declared here, so closing it bare would forbid the `service`
  and `host` that §12.4's own example carries. **No conformant document changes
  validity:** `{"description": ...}` and `true` are the same schema in Draft
  2020-12, and an absent `additionalProperties` already meant open.

- **The undescribed walker now reads what an open declaration MEANS, not whether
  the keyword is spelled out** — and this correction is what makes the declarations
  above safe. It decided "unconstrained by design" from the *absence* of every
  object keyword, so writing an openness down instead of leaving it absent armed the
  walker against the author: measured on `valid/rich.metalog.jsonl`, spelling
  `attribution.sketch_params` and `provenance[].source` open produced **six invented
  findings on a fully conformant document**, while `additionalProperties: {}` — the
  same schema — produced none. The mirror-image defect was live in the other
  direction: any non-empty value schema was treated as *describing* the extras, so
  moving the two roots from `true` to `{"description": ...}` would have silenced the
  legal-but-undescribed species at both of them. Both halves are mutation-measured:
  reverting the first reds `valid/rich.metalog.jsonl` with the six findings,
  reverting the second reds `undescribed/open_containers.metalog.jsonl` and
  `invalid/unprefixed_extension_key.diff.json` by going **quiet**.

- **`valid/rich.metalog.jsonl` now carries the two positions it claimed to
  exercise.** Its manifest entry named "sketch-shaped free objects" while the
  document had no `attribution` block at all, and its `provenance[]` entry carried no
  `source` — so the `undescribed-false-positive` control was blind to exactly the
  two positions whose disposition this release had to rule on. It now carries
  `attribution` with §6's three sketch parameters and a `provenance[].source` with
  §12.4's `service`/`host` plus `fleet`.

- **`--pointer` can now address every element of an array**, with one token added
  to RFC 6901: `-` in an **array** position selects **every** element, and each
  selected element is judged and counted as its own document
  (`--pointer /raw/-/diff`). The token is safe to give that meaning because RFC
  6901 §4 already gives it exactly one in an array — *the element after the last* —
  and that element never exists, so no pointer that used to resolve can start
  resolving differently. In an **object** position it stays a literal member name,
  exactly as RFC 6901 says.

  **The reason this is not a convenience.** An envelope carries one document per
  comparison its producer performed, so a real CI report's `raw` is a **list**. A
  pointer that resolves to one document judges the first and prints the same
  verdict over the rest — not a smaller check, a green covering a subject nobody
  chose. Measured on a four-entry envelope whose violation sits at entry 2:
  `/raw/0/diff` reads **exit 0, CONFORMANT**; `/raw/-/diff` reads **exit 1** and
  names `report.json/raw/2/diff`. Both readings are pinned as fixtures in the same
  manifest, so the contrast is executable rather than remembered.

  **Nothing moves for a single-document subject.** A pointer without the token
  selects exactly one node and labels it by FILE, unchanged — verified by
  re-running the three live invocations of this tool before and after: identical
  exit codes and identical findings, the only difference being a per-file document
  count added to the `corpus` line.

  Two failures are refusals rather than verdicts, and both are exit 2: a pointer
  written for a wire shape the envelope no longer has, and a pointer that resolves
  onto an **empty** array. The second is the shrink no exception-shaped guard can
  see — every path taken is correct and the subject is nothing.

  **Report shape:** the document count is now printed **per corpus file** as well
  as in the total, so a file that stopped carrying what it used to is visible
  without a roster. In `--json`, `corpus` is correspondingly a list of
  `{path, documents, expanded}` rather than a list of paths — one key with one
  meaning, rather than a second key repeating the first.

- **Three new self-test controls**, each derived from a mutation that the previous
  fixture set passed: `pointer-array-every-element` (the four-entry envelope above,
  with its single-document twin), `pointer-empty-selection` (an array present,
  well-formed and empty), and `pointer-token-literal-in-object` (an envelope
  carrying a member spelled `-`, so an implementation that wildcards the token
  everywhere judges two documents where one was addressed). The manifest gains two
  demands it derives from a fixture's own shape rather than from a list: a fixture
  whose pointer expands must say **which element** each finding came from, and a
  fixture expecting a refusal on a pointer must say **which refusal** — exit 2 is a
  class, not a reason. Ten mutations red the suite; the unmutated control passes
  **22/22**.

- `conformance/README.md` catches up with the fixture set it describes: twenty-two
  fixtures, ten of them carrying eight distinct `control` tags, and
  `declared-cap-violation` — added in this release's tooling entry above — gains
  the control-table row it never got. The instrument's declared limits gain the
  one this release makes relevant: a bare vendor member at either **document
  root** is reported, never failed. `--pointer` gains a section of its own.

---

## [0.8.0] — 2026-08-19

**Additive** under [`GOVERNANCE.md`](GOVERNANCE.md) §2 — new optional fields only.
No existing field changes type, becomes required, or is removed; **no conformant
0.7.0 document becomes invalid**, and a 0.7.0 producer stays legal (governance
requires only the MAJOR to match).

Four of the five members below were **already true of the format and merely
undescribed**. Two were normative in the prose and absent from the schema (a
schema lag, `GOVERNANCE.md` §3); two are new descriptions of a real member the
schema had no way to express. The distinction matters to an implementer: a schema
lag means the schema was wrong, not the producers.

### Added

- **`stats.top_k[].component` and `stats.reservoir[].component`** (string,
  optional, `minLength: 1`) — the dominant functional source (logger / module /
  unit / subsystem / build job) of a template's occurrences, defined once in the
  new **§3.8** and carried by both entry shapes. Same species as `level`: a
  low-cardinality categorical label the observed stream carries about itself.
  Normative points worth reading before emitting it: it **MUST** be derived from
  the observed events and never from producer state; it **MUST** be omitted rather
  than emitted empty when the format carried no component; and multi-component
  ties **MUST** break lexicographically so the field is replay bit-identical.
  It is a **label, not a key** — equality across documents is not evidence of a
  shared deployment.
- **`$defs/cube_axis.band_floor`** (integer ≥ 1, optional) — the ordinal-axis
  collapse stamp, **normative in §16.2/§16.10 prose since 0.6.0** and missing from
  the schema. A schema lag: the prose already required a collapsed cube to be
  self-describing, and the schema rejected the very stamp that makes it so.
- **`MetaLogDiff.field_histogram_deltas`** — **normative in §3.5.2 prose since
  0.3.0**, shown in the §13.1 example, and absent from the diff schema's
  `properties`. The second schema lag, and the more consequential one: it survived
  only because the diff root is open, so the schema neither described it nor
  rejected it.
- **`field_histogram_deltas[].previous_sample_count` / `.current_sample_count`**
  (integer ≥ 0, optional) — each side's `param_histograms[].total`, i.e. the
  number of observations the distribution was estimated from. New in this release
  because encoding `field_histogram_deltas` forced the question and the honest
  answer is that `js_divergence` is **not interpretable without a sample size**:
  a JS of 0.9 over eleven observations and over eleven thousand are different
  claims, and only the second is a regime shift. A producer emitting
  `js_divergence` **SHOULD** emit both; consumers **SHOULD** apply a
  minimum-sample floor.
- **`stats.top_k[].extensions`** — the §7 container, granted at a second
  placement. See below.

### Changed

- **§7 gains a normative *placement* rule, and the schema gains
  `$defs/extensions`.** The §7 grammar (reverse-DNS keys, closed to everything
  else) was defined inline at the document root; it is now defined **once** in
  `$defs` and referenced, so a second placement cannot drift from the first.
  The rule itself: `extensions` is **the only** carrier of non-standard members,
  and a producer **MUST NOT** write vendor data as a bare member of a standard
  object *at any depth, including objects the schema does not currently close*.
  Because vendor data is often **per-row** and a document-level container cannot
  carry a per-row value without inventing a join key, the container is granted
  per object, and §7 now carries the list (root since 0.1.0; `stats.top_k[]` from
  0.8.0).
  The list is **deliberately short and grows on evidence**. Granting the container
  everywhere in advance would be unwithdrawable — removing a placement is a
  *breaking* change — while adding one is *additive* and costs a single reviewer.
  A producer that needs one elsewhere is not stuck and is not silent: §8 clause 1
  detects the bare member, so the shortfall reports itself.
  Granting the container **does not re-open the object**. A misspelled standard
  member is still a violation, because it is not inside `extensions` — which is
  precisely why the extension point is a named container rather than a key prefix.

### Not in this release

- **The diff document's `additionalProperties: true` root**, the open
  `provenance[].window` / `current.window` / `previous.window`, and encoding
  §13.2's "at least one signal field" **MUST** are all **breaking** and require an
  `rfc:` issue with a 14-day comment window (`GOVERNANCE.md` §2). They are not
  bundled here, because the reference producer must first stop relying on the open
  root; closing it in the same release would make the reference implementation
  loudly non-conformant for the length of the comment window.
- Encoding §13.2 also needs its satisfying set corrected first. It is a
  hand-kept enumeration of eight fields that has already drifted from the schema
  beside it: `cube_diff` and `stability_score` are in the schema and not in the
  enumeration, and `field_histogram_deltas` (added above) is in neither. A
  document whose only signal is a field-histogram shift is **correct** and would
  be rejected by the enumeration as written.

---

## [0.7.0] — 2026-08-03

### Added

- `behavior.dropped_ngram_observations` (integer, optional, omitted when zero) —
  the count of n-gram **observations** discarded by a producer's accounting bound
  on distinct keys. Distinct from `top_ngrams` truncation, which is a ranking cut
  over entries that were counted; this bound refuses a key **before it is ever
  counted**, so an n-gram that would have ranked first can be absent purely
  because it arrived late. Reported rather than inferred, on the same principle
  as `dropped_edges`.
- The noun is normative: **observations, never distinct keys**. Distinct-key loss
  is not knowable without retaining exactly the set the bound refuses.
- Absence is disambiguated by `metalog_version`: in a 0.7.0+ document an absent
  field means no drop; in an earlier document it means unknown. Consumers MUST
  NOT read a missing field in a pre-0.7.0 document as zero.
- `compose()`: the field sums across inputs (absent counts as zero) and is
  omitted when the sum is zero.

Additive and omitted-when-zero, so **no existing document changes** and no
producer is obliged to emit it. A 0.6.0 producer stays legal against this spec
(governance requires only the MAJOR to match).

---

## [0.6.0] — 2026-06-16

> **Version → 0.6.0 (Draft) — the cube (EXPERIMENTAL).** Adds the intra-window
> **joint categorical condensation** to the format. The cube is **additive,
> provisional, and removable in a single revert** (§16.8): it is integrated now as
> the test rig for the upcoming causal (do-operator) verdict, not because the
> standing BGL evidence justified it (that leaned *ornament*, mono-axis). The format
> is v0.x with zero external consumers, so the landing is explicitly reversible and a
> future 0.x **MAY** remove it. A **pre-registered kill-criterion** governs the
> keep/kill decision (recorded in the internal cube spec, not here).

### Added (0.6.0)
- **§3.7.2.1 reservoir comparability is byte-scoped** — the `template_id` tie-break is
  content-derived but **meaning-blind** (SHA-256 over the template string), so a
  semantically neutral rename re-orders **equally-ranked** candidates and changes which
  tied template holds the last reservoir slot. Reproducibility for byte-identical input
  is unchanged and is *why* the tie-break exists. New: consumers **MUST NOT** attribute a
  reservoir-membership difference to behaviour when template texts differ, and the
  comparability predicate now names **stable template text** beside a matching
  `retention_profile`. Clarification only — **no schema, encoding or field change**.
  Measured on the showcase-sample build: a project-token rename moved a regression pair
  13 → 12 significant changes, with a same-length control ruling out a length effect.
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

---

## [0.5.0] — 2026-06-01

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
