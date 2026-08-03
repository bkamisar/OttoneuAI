# Trade Finder Redesign — Design Spec

**Date:** 2026-08-02
**Status:** Approved design, pre-implementation
**League context:** 12-team Ottoneu 4×4 (R/HR/OBP/SLG · K/HR9/ERA/WHIP), $400 cap, dynasty.

## Problem

`targets.html` surfaces "trade my best players for their best players, filtered by
the categories I need." The proposals don't feel realistic and rarely suggest a deal
either owner would actually make.

## Diagnosis

**The simulation engine is not the problem.** `simulateTrade` already re-optimizes both
rosters and blends with actuals — that part is correct and stays untouched. Three
upstream defects starve it of sensible candidates.

### D1 — Candidate pool is truncated to the most expensive slice

[targets.html:617-673](../../targets.html) builds candidates as:

```
myOffers   = my roster,    sorted by value, .slice(0, 4)
theirChips = their roster, sorted by value, .slice(0, 5)
```

Rosters run 36-52 players (median 42). That's **20 of 1,764 possible 1-for-1s — 1.1% of
the space**, drawn entirely from the top by value. The fairness filter (`tradeTol` 30% +
`CONSOL_PREM`) then requires the two sides to match in value. Top-4 matched against top-5
by value ⇒ star-for-star is the only reachable outcome.

`isTradeable` compounds it: `p.hasProj && p.surplus > 0 && myDepth[p.type] >= 3` means
only already-good players can be offered — never redundant-but-blocked ones.

### D2 — Candidates ranked by absolute value, not marginal value

Ranking uses `projValue` / `dynValue` / `surplus`, all absolute. But trade motivation
lives in **marginal** value: what a player is worth *to a specific roster*. A 6th
outfielder who never cracks the 12 active slots has high absolute and near-zero marginal
value to his owner, and full value to a team with a hole. `simulateTrade` would measure
that correctly — those candidates just never reach it.

### D3 — Contracts priced as obligations, not options

[shared.js:689](../../shared.js):

```js
const dynastyCost = s0 + w1 * Math.max(1, s0 + 2) + w2 * Math.max(1, s0 + 4);
```

Every holder is charged three years of escalating salary (+$2/yr Ottoneu keeper
escalation, discounted w1=0.90 / w2=0.81). But holding is optional — cutting is **free at
season's end**. A productive-but-overpaid player therefore shows a deeply negative
`dynastySurplus` and is invisible (or toxic) to the finder, when his true floor is
"rent for the stretch run, cut in October."

This also hides a second bug: full-season `s0` is charged against a **rest-of-season** Y0
value, violating invariant #1. In August that bills a whole season's salary for a
fraction of a season's production.

### League rules that make the rental archetype real

- **In-season cut:** dead money penalty of **half the salary**.
- **End-of-season cut:** free.

So for a **buyer** (contender): take the full salary against the cap for the stretch run,
get the production, cut free in October — future liability genuinely zero. For a
**seller** (rebuilder): cutting mid-season costs half the salary, while trading moves the
entire salary off the books at no penalty *and* returns an asset. Trading is strictly
better than cutting. Both sides gain for stateable reasons — and the current model cannot
generate this trade at all.

## Goal

Proposals that are **motivation-realistic** first (an obvious reason both ways),
**value-realistic** second (they'd plausibly say yes), **scale-realistic** third (mid-tier
pieces, not only blockbusters).

---

# Phase 1 — Foundation

## Fix 1: Option-valued contracts (`shared.js`)

A contract is an option, not an obligation. Evaluate three holding horizons and report
the best. Let `ros = rosProrationFactor()`, `w1`/`w2` the existing user-tunable discounts,
and `s0 = Math.max(1, actualSalary)`.

| Horizon | Value | Cost |
|---|---|---|
| **H0** "rental" | `y0` | `s0×ros` |
| **H1** | `y0 + w1×y1` | `s0×ros + w1×max(1, s0+2)` |
| **H2** "keeper" | `y0 + w1×y1 + w2×y2` | `s0×ros + w1×max(1,s0+2) + w2×max(1,s0+4)` |

`surplus_k = value_k − cost_k`. Pick `k* = argmax(surplus_k)`. Then **the whole triple
reports the winning horizon**:

```
dynastyValue   = value_{k*}
dynastyCost    = cost_{k*}
dynastySurplus = surplus_{k*}
holdHorizon    = k*          // 0 = rental, 1, 2 = keeper
```

**Value and cost must describe the same horizon.** Reporting a 3-year value against a
1-year cost would credit three years of production against one year of salary. This is
also load-bearing for Phase 2: the fairness filter matches value-for-value, so a rental
must carry his *rental* value (~$12), not his 3-year value (~$40) — otherwise the filter
demands $40 of assets for a two-month rental and the archetype can never clear.

**Prospect floor (invariant #6):** apply `prospectDynastyValue` to the **H2 value only**
(`value2 = max(value2, floor)`) before choosing the horizon. Prospects carry low salaries
and high future value, so H2 wins for them naturally and the floor stays `max(model,
floor)` — never additive, never overriding a better projection-based value.

**Y2 fallback:** unchanged — a player with Y1 but no Y2 reuses Y1 (MODEL.md §4).

**Worked example.** Salary $30; RoS y0 $12; y1 $18; y2 $15; `ros = 0.45`.

- Today: value `12 + 0.90×18 + 0.81×15 = $40.35`; cost `30 + 0.90×32 + 0.81×34 = $86.34`
  → surplus **−$46.0**.
- H0: `12 − 30×0.45 = 12 − 13.5` → **−$1.5** ← wins
- H1: `28.2 − (13.5 + 28.8)` → −$14.1
- H2: `40.35 − (13.5 + 28.8 + 27.54)` → −$29.5

Result: −$46 → **−$1.5**, `holdHorizon = 0`. Roughly break-even as a rental, which is the
truth.

**Blast radius.** `dynastyValue`/`dynastySurplus` are computed in one place
(`calculateDynastyValues`) and read by five pages: `bid.html`, `prospects.html`,
`roster.html`, `targets.html`, `trade.html`. Two distinct effects, to be measured and
reported **separately** during verification:

1. **Proration correction** — affects everyone, roughly uniformly (raises surplus).
2. **Option floor** — affects overpaid-but-productive players specifically.

Good, fairly-paid players still resolve to H2 and are unchanged apart from (1).

## Fix 2: Marginal-value engine (`tradefinder.js`)

For team `T` with roster `R`, using the existing `optimizeHitterLineup` / `selectPitchers`
/ `computeTeamStats` machinery and SGP denominators:

```
baseline(T)          = teamSGPDollars(R)
marginalValue(p, T)  = baseline(T) − teamSGPDollars(R \ {p})     // lineup re-optimized
blockedness(p)       = projValue(p) − marginalValue(p, owner(p))
```

`teamSGPDollars` converts a team stat line to SGP via the existing per-category
denominators, then to dollars via the league $/SGP rate, so `blockedness` is in dollars
and comparable to player values.

**Units:** `blockedness` compares against **`projValue` (Y0, current-season dollars)**,
because `marginalValue` is derived from Y0 production. Do not mix `dynastyValue` into
this subtraction — the dynasty lens enters later, at the fairness/utility stage, which is
unchanged.

**Invariant #2:** `teamSGPDollars` must aggregate pitching under the 1,500 IP cap
(`selectPitchers` with the Y0 prorated budget). Removing a pitcher frees budget, so the
re-optimized remainder may absorb it — that is the correct marginal effect and must not
be short-circuited.

- **Surplus asset** (team T): `blockedness(p) ≥ BLOCK_MIN` (default **$5**) — value
  stranded on the bench.
- **Need** (team T, lineup slot): the slot's current occupant contributes materially less
  than the league median occupant of that same slot —
  `needGap(T, slot) = medianSlotValue(slot) − marginalValue(currentOccupant(slot), T)`,
  a need when `needGap ≥ NEED_MIN` (default **$5**). `medianSlotValue` is computed across
  the 12 teams' optimized lineups, so it needs no external baseline.

**Performance.** 12 teams × ~42 players ≈ 504 removals plus 12 baselines, each a lineup
re-optimization. Cache per team, invalidated when rosters/projections reload. If the full
sweep exceeds ~2s, compute lazily per opponent card (~42 removals when a card is opened)
rather than eagerly for all 12.

---

# Phase 2 — Archetype generator

Candidates are generated **by reason** rather than by slicing a value-sorted list. Each
carries an `archetype`, a human-readable `reason`, and its supporting numbers.

Let `gain(p, A, B) = marginalValue(p, B) − marginalValue(p, A)` — how much more p is worth
to team B than to his current team A.

1. **Logjam ↔ Hole**
   Trigger: my `p` with `blockedness(p) ≥ BLOCK_MIN` and `gain(p, me, them) ≥ GAIN_MIN`
   (default **$5**); reciprocally for their `q`.
   Reason: *"You're 5 deep at OF; they start a replacement-level OF."*

2. **Rental / salary dump**
   Trigger: their `q` with `holdHorizon === 0`, `marginalValue(q, me) > 0`, my status
   contender or fringe, their status rebuilder or fringe. I send a modest future asset
   (low current marginal value, positive dynasty surplus).
   Reason: *"They avoid $S/2 in dead money by trading rather than cutting him, and get an
   asset instead of nothing; you cut free in October."* (`S` = his salary.)
   Cap: post-trade salary checked against $400 (existing soft warning — Ottoneu allows
   loans).

3. **Buy-now ↔ sell-future**
   Today's `rel = 'buy' | 'sell'` logic, but fed marginal values instead of absolute ones.

4. **Consolidation**
   2-for-1 where I'm deep and need the roster spot or cap room. Existing `CONSOL_PREM`
   (15%/extra player) continues to price the bulkier side.

**Unchanged downstream:** every generated candidate still passes through the existing
fairness pre-filter (`tradeTol` 30% + `CONSOL_PREM`), then `simulateTrade`, then the
utility gate (`PTS_DOLLARS 15`, `MIN_UTILITY $1`, status weights). Those are correct; they
have simply been starved of sane input.

**UI:** each proposal displays an archetype badge, the reason string, and a
`holdHorizon` label ("rental" / "keeper") on the players involved.

---

## Code structure

| Piece | File | Role |
|---|---|---|
| Option-valued contracts | `shared.js` (`calculateDynastyValues`) | Surgical change to the cost/value/surplus triple + new `holdHorizon`. |
| Marginal value + archetypes | `tradefinder.js` **(new)** | Pure, unit-testable: `teamSGPDollars`, `marginalValue`, `blockedness`, `gain`, archetype matchers. |
| UI | `targets.html` | Consumes `tradefinder.js`; renders archetype badge + reason. Already 1,504 lines — no new logic added there. |
| Tests | `test.html` | Loads `tradefinder.js` alongside `shared.js`/`hotboard.js`. |

Mirrors the `hotboard.js` split: pure logic out of the page, testable in the existing
suite.

## Testing

**Phase 1 (option-valued contracts):**
- Good cheap contract ($5 salary, strong y0/y1/y2) → `holdHorizon === 2`.
- Overpaid but productive (the worked example) → `holdHorizon === 0`, surplus ≈ −$1.5.
- Genuinely bad contract (overpaid *and* unproductive) → negative at every horizon; max
  still negative.
- `dynastyValue`, `dynastyCost`, `dynastySurplus` all report the **same** horizon.
- Prospect with a floor above his model value → floor applied, `holdHorizon === 2`.
- Y0 cost term is prorated by `rosProrationFactor()` in all three horizons.

**Phase 1 (marginal value):**
- A blocked 6th OF scores near-zero marginal on a deep roster.
- A starter scores materially above his bench replacement.
- `blockedness` is high for the blocked player, ~0 for the starter.

**Phase 2 (archetypes):**
- Each matcher fires on a fixture that should trigger it and stays silent on one that
  shouldn't (logjam with no counterpart hole; rental where I'm the rebuilder).
- Reason strings include the supporting numbers.

## Verification & risk

- **MODEL.md anchors:** Y0 anchors (hitShare ≈ 50%, top hitter $55-65, aces $45-70, ~35%
  at the $1 floor) are untouched by this work — confirm they don't move. Dynasty anchors
  (Made $59, Basallo $45, De Vries $41) are prospects and should resolve to H2, so they
  should be stable; any drift there is a bug in the floor handling.
- **Report the two Phase-1 effects separately** (proration vs option floor) so drift is
  attributable.
- **Hard-refresh** when verifying `shared.js` changes (invariant #7).
- **MODEL.md updates:** §4 rewritten for option-valued contracts + `holdHorizon`; §5
  rewritten for archetype generation; new invariant — *value and cost must always report
  the same holding horizon*; §6 knob table gains `BLOCK_MIN`, `NEED_MIN`, `GAIN_MIN`.

## Implementation phasing

Two separate implementation plans, executed in order:

- **Plan 1 — Foundation.** Fix 1 (option-valued contracts, `shared.js`) and Fix 2
  (marginal-value engine, `tradefinder.js`) plus their tests and the MODEL.md §4 update.
  Independently valuable and verifiable: dynasty numbers become correct across all five
  pages, and blocked players become identifiable. Ship and sanity-check the anchors
  before touching the generator.
- **Plan 2 — Generator.** Archetypes, `targets.html` rewiring, reason display, MODEL.md
  §5 update. Depends on both Phase 1 fixes.

Splitting here matters because Plan 1 changes numbers suite-wide. Landing it alone makes
any drift attributable to the valuation change rather than tangled with new trade-
generation behavior.

## Non-goals

- **Not** changing the +$2/+$4 arbitration escalation in this pass. MODEL.md §4 notes it
  understates star keeper costs; option-valuing pushes surplus up further. Changing both
  at once makes drift unattributable — revisit after the anchors are re-checked.
- **Not** changing `simulateTrade`, the fairness pre-filter, or the utility gate.
- **Not** changing Y0 valuation (`calculateAllValues`) in any way.
