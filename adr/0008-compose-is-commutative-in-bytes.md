# ADR 0008 — Compose is commutative in bytes

- **Status:** Proposed — accepted when the editor merges its pull request
- **Date:** 2026-10-24
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §12.1 (the compose clauses this ADR adds to), §12.2 (the commutativity
  property it rewrites), §12.4 (`provenance`), §3.7.2 (reservoir admission and its
  `template_id` tie-break), §3.8 (`component`'s count-then-lexicographic rule), §2.1
  (`producer`), §15.6 (replay bit-identity), GOVERNANCE §2

## Context

§12.2 said that `compose(A, B)` and `compose(B, A)` **MUST** *"agree on all required fields"*.
Read literally, that left a composer free to decide any optional member, and the order of any
array, by which operand it read first. A review of the reference implementation's compose found
four such choices, each legal under that text and each giving a different document for the
other operand order:

- **Per-template labels, first seen.** When `A` and `B` disagree on a template's `level`, its
  `structural_role` or the where-path of its `cube_coord`, the value of whichever input was read
  first was kept. `component` had no compose clause at all.
- **`provenance` in operand order.** §12.1 defines `C.provenance` as a union and says nothing of
  its order, and an array's order is part of a JSON document.
- **Equal-count ordering.** `top_k` and `top_ngrams` are *"ordered by count desc"*, with no rule
  for two entries of equal count — and at the `top_k_size` boundary that tie decides which
  template is retained at all.
- **`producer` copied from the left input.** §12.1 does not say whose `producer` block `C`
  carries.

Every required field agrees in each case, so §12.2 was satisfied, and still two conformant
composers — or one composer fed the same two windows in the other order — emit different bytes.
That defeats the property commutativity exists for: sharded ingestion merges per-host documents
in whatever order they arrive, and a consumer that hashes, diffs or replays the result (§15.6)
must not see the arrival order in it.

## Decision

`compose(A, B)` and `compose(B, A)` **MUST** be the same document: every member present in one
is present in the other with an equal value, and every array holds equal elements in the same
order. A producer that serialises deterministically therefore emits byte-identical output for
either order. **No member of `C` is taken from an input by its position.** Wherever the inputs
disagree, §12.1 resolves the value by a rule over the values themselves:

1. **A per-template label** (`level`, `component`, `structural_role`, the where-path of a
   `cube_coord`) takes the value of the input that contributed the **higher count** of that
   template, and the **lexicographically smaller** value at equal counts. A label present in only
   one input is carried.
2. **`top_k`, `reservoir` and `top_ngrams`** entries are ordered by their ranking value (`count`,
   `salience`, `count`) descending, then by `template_id` — or, for an n-gram, its key sequence —
   ascending. The same order decides the last retained slot at a size boundary.
3. **`provenance`** entries are sorted by `window.start`, an entry without bounds first, then by
   `window.end`, then by the byte order of their RFC 8785 canonical serialisations.
4. **`C.producer`** is the composer's own block, and `C.metalog_version` the version the composer
   writes: the composer produced `C`.

## Alternatives considered

**Declare these members order-sensitive instead.** The other reading of §12.2's *"required
fields"*: keep the text, and state that labels, `provenance` order and equal-count order may
depend on operand order. Rejected: it keeps the property in name and removes it in use. A
consumer could no longer compare two composed documents byte for byte, and an implementer
composing in the other order would be conformant while producing different output from the
reference implementation — the disagreement this specification exists to prevent.

**Resolve a label by a fixed order over its values — the most severe level, say.** It is both
commutative and associative, which the count rule is not (below). Rejected because the spec gives
no order to resolve by: `level` is a free string (§3.7.1), so a severity order would have to be
invented here, and a byte order over strings — the only order the spec already has — is
meaning-blind: it would pick `"DEBUG"` over `"ERROR"`. The count rule picks the label the merged
population most likely carries, and §3.8 already uses exactly this rule for `component` inside one
window, so a composer and a producer resolve a label the same way.

**Merge per-input labels into a list.** Rejected: it changes the type of four members, a breaking
schema change for every consumer, to carry a disagreement most consumers would collapse again.

## Consequences

- **Associativity is not made exact by this ADR.** The count rule is commutative, but under
  re-association a label can differ: with `A` carrying a template at count 5 as `INFO` and `B`
  and `C` each at 4 and 3 as `ERROR`, `compose(compose(A, B), C)` keeps `INFO` (9 against 3) while
  the merged population is 5 `INFO` against 7 `ERROR`. §12.2 already states associativity as
  best-effort (**SHOULD**), and this case is within it.
- **Breaking, by the letter.** A composer that reads a member from an operand by position becomes
  non-conformant. No document's validity changes: no member is added, removed or retyped, and the
  schema does not move.
- **The reference implementation follows the text.** Under GOVERNANCE §3 the spec wins a
  disagreement; until its compose sorts as above, it is non-conformant on these four points.
