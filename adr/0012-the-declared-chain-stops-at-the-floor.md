# ADR 0012 — The declared chain stops at the schema floor, so a collapse is decidable on the wire

- **Status:** Proposed — accepted when the editor merges its pull request
- **Date:** 2026-11-15
- **Spec version affected:** 0.10.0 (unreleased at the time of writing)
- **Related:** SPEC §2.4 (the comparability gate), §13.6 (`cube_diff`), §16.2 (the collapse
  stamps), §16.3 (the WHERE chain and its floor), §16.10 (the budget collapse), ADR 0010 (every
  comparison a pair made impossible is stated)

## Context

§16.2 promises that *"a truncated granularity MUST NOT be mistakable for a full one"*, and
makes the collapse stamps the means: `band_floor` on the `level` axis, and `floor_depth` on a
chain axis, the window's effective retained depth, equal to the frozen schema floor when the cube
was not collapsed.

§16.3 let the schema floor be any depth up to `len(chain)`, and no document carries the floor.
So a cube whose chain is `["subsystem", "component"]` and whose `floor_depth` is 1 has two
readings: an uncollapsed cube whose producer froze its floor at 1, or a cube whose floor is 2 and
which §16.10 truncated by one level in this window. The bytes are the same. The promise could not
be kept on the wire by any producer that used the allowance, and a consumer reading
`floor_depth < len(chain)` as "truncated" was right for one reading only.

The same paragraph of §16.2 names `floor_depth` 0, "when the chain was dropped" by §16.10's last
WHERE step, and the schema's `minimum: 1` refused it: a producer that reached the drop wrote a
document the schema rejected.

## Decision

1. **The declared `chain` stops at the schema floor: `len(chain)` is the floor.** Levels below
   it are neither cubed nor declared. A producer whose hierarchy runs deeper declares the chain
   down to its floor and no further.
2. **A chain axis was truncated exactly when `floor_depth < len(chain)`**, decided from the
   document alone; `band_floor` already decides banding the same way.
3. **`floor_depth` admits 0** in both schema files, the dropped chain §16.2 always named.
4. **Two cubes whose floors differ declare different chains**, so §13.6 states the pair
   `cube_axes_differ`. §2.4 refuses such a pair before §13 whenever both inputs carry
   `retention_profile`, because the floor is a retention parameter; only an unstamped pair reaches
   §13.6.

## Alternatives considered

### A. Declare the schema floor in a new axis member

It keeps the allowance and decides the promise, at the price of a member whose only content is
the length of a chain the producer could have declared shorter. It adds a second place where the
floor lives, which a producer can set inconsistently with the cells it emits.

### B. Keep the allowance and weaken the promise

`floor_depth` would still say at which depth the cube holds counts, which is what a diff needs.
But "was this window collapsed" is itself information: a collapse means the window exceeded the
producer's cell budget, and a consumer watching for that could no longer see it. The promise
exists for that reader.

### C. Compare a floor-only difference at the smaller depth, as 0.10.0 drafted

Two cubes over one hierarchy at different floors are exactly comparable at the smaller depth,
because roll-up is prefix truncation. Under this decision such a pair is stated, not compared,
which withholds a comparison that could be made. The cost is bounded: the pair reaches §13.6 only
without `retention_profile`, and the same statement already applies to two chains that agree on
a common prefix, the same mathematical case. One rule for both is simpler than a carve-out for
one.

## Consequences

- A producer that declared levels below its floor becomes non-conformant and shortens its
  declared chain. A producer whose chain already stops at its floor is unaffected.
- A document stamping `floor_depth` 0 validates.
- No member is added, removed or renamed.
