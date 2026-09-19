# Standings Finish Odds — Design

**Date:** 2026-09-19
**Status:** Approved in brainstorming; awaiting spec review
**Page:** `standings.html` (new "Finish Odds" panel)

## Goal

Turn the standings projector's single best-guess finish into probabilities:
each team's chance to finish 1st, 2nd, 3rd (and top 3), plus a data-driven
explanation of how a trailing team gets to 1st or into the top 3.

Two modes on one engine:

- **This Season** — the ~17 games left (145/162 played, 1251/1500 IP thrown
  as of 2026-09-19), layered on current actual standings.
- **Next Season** — a full 2027 season from current rosters on ZiPS Y1
  projections.

## Decisions made in brainstorming

- **Team-level Monte Carlo** (not player-level, not analytic). Noise is added
  to each team's projected category stats; ranking uses the existing
  `buildStandings`. Player-level re-optimization per run was rejected as slow
  and heavy for little gain; an analytic approach can't produce overall
  finishing-place odds across 8 rank-scored categories without simulating
  anyway.
- **No recent-form (7/15/30-day) tuning.** Short-window results carry little
  predictive signal beyond a good projection; Steamer RoS already updates daily
  from full-season stats. Blending in streaks would add noise and a `hot.json`
  dependency. Recorded here so it isn't re-litigated.
- **Paths are conditional averages over the simulated runs**, not hand-built
  scenarios.
- **Both "path to 1st" and "path to top 3"** are included.

## Architecture

### `standingsim.js` (new, pure functions — mirrors the `tradefinder.js` pattern)

```
simulateStandings(teams, opts) → result
```

**Input `teams`:** `[{ name, curr, proj }]`
- `proj` — team stats in the shape `computeTeamStats` returns
  (`OBP SLG HR R ERA WHIP HR9 SO _ip _totPA`).
- `curr` — a `parseCurrStandings` row, or `null`. In `ros` mode a team with
  `curr === null` is simulated on its projection alone (matches the existing
  table's fallback).

**`opts`:**
- `mode`: `'ros'` (blend with actuals via `blendStats`) or `'full'` (projection
  is the whole season; no blend).
- `n`: runs (default 10000).
- `seed`: integer for the seeded RNG (tests pass a fixed seed; the page passes
  one too, so a given data set gives stable numbers on reload).
- `errorMult`: scales the projection-error term (see Noise model).
- `luckMult`: scales the luck term (default 1). Tests set both multipliers to
  0 to get a deterministic run.

**One run:**
1. For each team, draw noise for all 8 categories and apply it to `proj`.
2. `ros`: `blendStats(curr, noisyProj)`. `full`: use `noisyProj` directly.
3. `buildStandings` → category points and total points.
4. Assign finishing places with **tie splitting** on total points: teams tied
   across places k..k+m each get `1/(m+1)` credit for each of those places.
5. Accumulate place credit and path statistics (below).

**Baseline:** one zero-noise pass through the same steps is the "most likely"
standings. It must equal what the existing Rest-of-Season / projection table
shows for the same inputs.

**Output:**
```
{
  n,
  baseline,                    // buildStandings result of the zero-noise pass
  teams: {
    [name]: {
      place: [p1, …, p12],     // probabilities, sum to 1
      top3,                    // p1 + p2 + p3
      avgPts,
      paths: { first: Path|null, top3: Path|null }
    }
  }
}
Path = {
  odds,                        // P(condition)
  gains:  [{ cat, delta }],    // this team's biggest mean category-point gains vs baseline
  rivals: [{ team, cat, delta }], // who gives ground, and where
}
```

### Noise model

Every category's noise is `luck + projection error`, drawn as normals and
added to the projected value for the simulated period.

**Luck** — sampling variance over the playing time being simulated. For `ros`
this is the remaining sample; the pitching sample is the *effective* remaining
IP after the IP-cap throttle `blendStats` applies (`min(proj._ip, IP_MAX −
curr.ip)`), so noise is never sized on innings that won't count.

| Cat | SD of the simulated-period value |
|---|---|
| HR | `√(D_HR · λ)` |
| R | `√(D_R · λ)` |
| SO | `√(D_SO · λ)` |
| OBP | `√(p(1−p) / PA)` |
| SLG | `SLG_AB_SD / √AB`, AB ≈ `0.89 · PA` |
| ERA | `9 · ERA_IP_SD / √IP` |
| WHIP | `WHIP_IP_SD / √IP` |
| HR9 | `√(9 · HR9 / IP)` |

`λ` = the projected count for the period; PA = `proj._totPA`; IP as above.

Starting constants (named, top of `standingsim.js`):
`D_HR = 1.0`, `D_R = 2.0` (runs cluster within innings), `D_SO = 1.0`,
`SLG_AB_SD = 0.88` (per-AB total-bases SD at a ~.420 SLG),
`ERA_IP_SD = 0.9` (runs allowed per inning), `WHIP_IP_SD = 1.15`
(baserunners per inning).

**Projection error** — the projection's talent estimate being wrong. Sized as a
one-SD *full-season team* miss, then scaled by mode:

| Cat | Full-season 1-SD miss |
|---|---|
| HR | 10% of λ |
| R | 6% of λ |
| SO | 7% of λ |
| OBP | ±0.008 |
| SLG | ±0.015 |
| ERA | ±0.30 |
| WHIP | ±0.035 |
| HR9 | ±0.12 |

- Counting misses are a percentage of the simulated period's λ (so they shrink
  with remaining volume); rate misses are absolute on the period's rate (a
  talent miss doesn't shrink with sample — its effect on the final line is
  diluted by `blendStats`' season-elapsed weighting instead).
- **Correlation:** within one run, each team draws one shared hitting factor
  and one shared pitching factor. Each category's error is
  `e · (√ρ · z_shared + √(1−ρ) · z_cat)` with `ρ = 0.6`, signed so a positive
  shared draw is *better* in every category of that side (lower ERA/WHIP/HR9,
  higher everything else). Luck terms stay independent.
- **Mode multipliers** (`errorMult`): `ros` = **0.75** (RoS projections have
  already absorbed five months of data); `full` = **1.5** (a full season adds
  injuries and in-season roster churn a static projection can't see).

All of these are assumptions. They live in named constants and are documented
in MODEL.md with the reasoning above, so they can be tuned deliberately.

### Path analysis

For each team T and condition C ∈ {first, top3}, over the runs where T meets C
(weighted by tie-split credit):

- **gains** — T's mean category-point change vs the baseline, per category.
  Report the top 3 with mean delta ≥ **0.3** points.
- **rivals**:
  - *first*: the **baseline leader's** biggest mean category-point drops
    (top 3, ≥ 0.3). Skipped for the baseline leader itself.
  - *top3*: the baseline top-3 team T most often displaces, with that team's
    biggest drops. Skipped for teams already in the baseline top 3.
- **Threshold:** a path is reported only if `odds ≥ 1%` (≥ 100 qualifying runs
  at n = 10000). Below that the path is `null` and the UI says "no realistic
  path" — too few runs to average honestly.

Accumulation cost: per run, only the (≤ 4) teams meeting a condition add a
12 × 8 delta block. Cheap.

### Tie handling

- **Total points:** split credit (above). Guarantees every team's `place` sums
  to 1 and every place sums to 1 across teams.
- **Category values:** `buildStandings` gives strict positions; with
  continuous noise exact ties are negligible. The zero-noise baseline inherits
  `buildStandings`' existing tie behavior unchanged.

### RNG

Seeded `mulberry32` + Box–Muller normals, in `standingsim.js`. No
`Math.random` in the engine.

## Page — `standings.html`

New **Finish Odds** panel below the existing table.

- **Toggle:** This Season / Next Season.
  - This Season hidden when `ottoneu_curr_standings` is absent.
  - Next Season hidden when no roster player has `proj_y1`.
  - If neither is available, the panel is hidden.
- **Odds table:** Team · %1st · %2nd · %3rd · %Top 3 · Avg Pts, sorted by
  %1st then %Top 3. The user's team row is highlighted (existing `.mine`
  class). Nonzero percentages under 1% render as `<1%`; exactly zero renders
  as `—`.
- **Expandable rows:** clicking a row reveals its path(s):
  - *Path to 1st* (if T isn't the baseline leader), e.g. "In the 9.8% of runs
    you finish 1st: +1.8 pts OBP, +1.2 HR, +0.7 R. Leader: −0.9 R, −0.8 SLG."
  - *Path to top 3* (if T isn't in the baseline top 3).
  - "No realistic path" when the path is `null`.
- **Footer:** run count and a one-line assumption note — projection error
  included; for Next Season, "current rosters as they stand — offseason cuts
  and auctions not modeled."
- Simulation runs after the main table renders, inside a `setTimeout`, so the
  table never waits on it. Rendering uses `textContent` only (existing
  convention — no `innerHTML` with data).

### Building the inputs

- **This Season:** exactly the `projStatsArr` the page already builds for the
  Rest-of-Season mode, paired with each team's `currByName` row. Reusing it is
  what guarantees the baseline matches the table.
- **Next Season:** clone rosters onto Y1 projections with `cloneForYear(…,
  'proj_y1')`, then per team `optimizeHitterLineup(hitters, PA_PER_SLOT)`,
  `selectPitchers(pitchers, IP_MAX)`, `computeTeamStats(...)` — the same
  full-season budgets `calculateAllValues` uses for future years. Requires
  `attachYearProjections` on the merged roster (as `roster.html` does).

## `shared.js` change

Lift `cloneForYear` (and its helper `yearProjP`) out of
`calculateDynastyValues` to top level, unchanged, so Next Season reuses the
same Y1 cloning — including the two-way pitching line (Ohtani) — instead of a
copy. `calculateDynastyValues` keeps calling it exactly as before.

## Error handling

- Missing current standings → This Season hidden (see Toggle).
- Missing Y1 → Next Season hidden.
- Team absent from `standings.csv` → projection-only in `ros` mode.
- Engine guards: zero PA/IP in the period → that side's luck term is 0 (no
  division by zero); non-finite noisy values are clamped to 0 for counts and
  skipped for rates.

## Testing (`test.html`, fixed seed)

1. **Zero noise ≡ `buildStandings`:** with `luckMult = errorMult = 0`, each
   team's place probability is 1.0 at its `buildStandings` place.
2. **Conservation:** every team's `place` sums to 1; every place sums to 1
   across teams.
3. **Dominant team:** a team better in all 8 categories by a wide margin wins
   ~100%.
4. **Symmetry:** 12 identical teams each win ≈ 1/12 (within sampling tolerance).
5. **Tie split:** a constructed two-way tie for 1st gives each team 0.5.
6. **Luck shrinks with sample:** noise SD → 0 as remaining PA/IP → 0.
7. **Path correctness:** a constructed race where one close category decides
   1st — the trailing team's path-to-1st `gains` lists that category first.
8. **Threshold:** a team under 1% odds gets `paths.first === null`.

## Build order

1. `standingsim.js` engine + tests 1–8.
2. This Season on the page.
3. Hoist `cloneForYear`; Next Season on the page.
4. MODEL.md section: noise model, constants, rationale, limitations.

## Limitations (to document)

- Constants are assumptions, not fitted to this league's history.
- Innings and PA volume aren't randomized (managers control volume near the
  cap).
- Next Season uses current rosters; offseason cuts, auctions, and trades are
  not modeled. Prospects without Y1 projections contribute nothing.
- `standings.csv` Games/IP are uniform across teams (existing data
  limitation), so the season-elapsed weighting is the same for every team.
