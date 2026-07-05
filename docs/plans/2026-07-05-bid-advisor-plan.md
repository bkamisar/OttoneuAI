# Implementation Plan: Waiver Bid Advisor (`bid.html`)

Execute mechanically — all design decisions are pre-answered. Follow existing
page patterns (fa.html is the closest skeleton). Do NOT modify shared.js
valuation logic; everything needed is already exported/global. Read MODEL.md
before starting if any formula below seems surprising.

## Purpose
For any free agent, answer: "how much should I bid?" given (a) simulated
impact on MY lineup/standings, (b) my remaining cap space, (c) dynasty value
going forward. Ottoneu context: winning bid = the player's salary permanently
(+$2/yr keeper escalation), cap is $400 total salaries, loans exist.

## Page skeleton
- New file `bid.html`, cloned structurally from fa.html: same head block
  (inline styles + `<link rel="stylesheet" href="theme.css">`), same nav (add
  `<a href="bid.html">Bid Advisor</a>` to THIS page's nav marked active).
- Add the `Bid Advisor` nav link to all 7 other pages' navs (index, standings,
  roster, trade, fa, prospects, targets) — one `<a>` line each, before or
  after "FA Finder".
- Data load: `autoLoadFromRepo()` then read localStorage keys exactly as
  fa.html does (roster, proj hitting/pitching, Y1/Y2, weights, curr standings,
  prospects, my team). Error states copied from fa.html.

## Data pipeline (init once, cache in page globals)
1. `merged = matchPlayers(roster, projHit, projPitch)`; attach Y1/Y2 via
   `attachYearProjections` (both years, same order as targets.html).
2. `rostered = merged where team && team !== 'Free Agent'`;
   `allRosters` grouped by team.
3. `faPool = getFreeAgents(projHit, projPitch, merged)` — then attach Y1/Y2 to
   faPool too (call `attachYearProjections(faPool, hitY1, pitY1, 'proj_y1')`
   etc. — it works on any player array with `name`/`type`).
4. `dynMap = calculateDynastyValues(allRosters, weights, faPool)` — gives every
   FA `projectedValue` (Y0 RoS $) and `dynastyValue` (incl. prospect floors).
5. My team context:
   - `myPlayers = rostered where team === myTeam`
   - `mySalary = Σ salary`; `capRoom = 400 − mySalary`
   - Base standings context: same simCtx pattern as targets.html — per team
     `optimizeHitterLineup` + `selectPitchers` + `computeTeamStats`, blended
     with `blendStats` when curr standings exist; `basePoints` from
     `buildStandings`; `denoms = calcSGPDenoms(...)` for the zDelta helper.
     Copy `blendedStatsFor` + `zDelta` helpers from targets.html verbatim.

## Core computation: `bidAdvice(fa)` → object
For a selected FA player:

1. **Lineup simulation** — `simulateAdd(fa)`:
   - `newRoster = myPlayers.concat([fa])`
   - newStats = blendedStatsFor(newRoster, myTeam); rebuild standings array
     with only my team's stats replaced; `ptsDelta = newPts − basePts`;
     `zD = zDelta(baseStats[myTeam], newStats)`.
   - `impactPts = ptsDelta + zD` (same convention as targets.html benefitFor).
   - Displacement: after `optimizeHitterLineup(newRoster hitters)` (or
     `selectPitchers` for P under the Y0 prorated budget
     `IP_MAX × Math.max(rosProrationFactor(), 0.1)`), diff the selected set
     vs the base lineup selected set → `displaced` = name pushed out, or null
     ("bench/streaming depth" if none).

2. **Three bid ceilings** (all in $, floor each at 0):
   - `valueNow = dynMap[key].projectedValue` (generic RoS value).
   - `myImpact$ = 15 × impactPts` (same PTS_DOLLARS=15 as targets.html).
   - `keeperBreakEven`: largest B where dynasty value ≥ dynasty cost of a
     player salaried at B. Using stored weights w1, w2 and shared.js's cost
     shape `cost(B) = B + w1×(B+2) + w2×(B+4)`:
     `keeperBreakEven = (dynastyValue − 2×w1 − 4×w2) / (1 + w1 + w2)`.

3. **Recommendation**:
   - `winNowMax = Math.max(valueNow, myImpact$)` — a contender may rationally
     pay up to his impact on THEIR team even above generic value.
   - `recommend = Math.round(Math.min(winNowMax, Math.max(keeperBreakEven, 0.6 × winNowMax)))`
     (never pay more than win-now justifies; lean toward keeper-safe unless
     the win-now case is strong). Clamp to ≥ 1 when valueNow ≥ 1, else 0
     ("don't bid").
   - Bands: `bargain ≤ 0.7×recommend` · `fair ≤ recommend` ·
     `stretch ≤ min(winNowMax, keeperBreakEven×1.15)` · beyond = overpay.
   - Cap guardrails: if `recommend > capRoom` show hard warning "exceeds your
     $capRoom cap room — needs a loan or cut"; if `recommend > capRoom − 10`
     soft warning "leaves under $10 of season flexibility".

4. Output object: `{ valueNow, dynastyValue, myImpact$, impactPts, displaced,
   keeperBreakEven, recommend, bands, capRoom, capAfter: capRoom − recommend,
   keeperNote }` where `keeperNote` = "Keeper-friendly up to $X" or, when
   `keeperBreakEven < 1`, "Rental only — don't plan to keep at any real salary".

## UI (top to bottom)
1. Header card: "My cap: $X spent · $Y room" (+ roster count of `myPlayers`).
2. Search box with dropdown (copy `makeDropdown` pattern from targets.html)
   over faPool sorted by `projectedValue` desc; show `$now / $dyn` on rows
   (reuse the dual-value convention).
3. On select → advice card:
   - Big number: "Recommended bid: $R" with band strip (bargain/fair/stretch
     labels at their thresholds).
   - Three ceiling rows with one-line explanations: "This year (league-wide):
     $valueNow" / "This year (your lineup): $myImpact$ — {+0.8 pts, displaces
     Jake Bauers | adds bench depth}" / "Keeper math: break-even bid $K".
   - Cap line: "After a $R bid: $capAfter room" + warnings per guardrails.
   - Dynasty line: dynastyValue with FV badge if `prospectMap[name]` exists
     (copy badge pattern from targets.html).
4. Below search: "Top targets on the wire" table — top 20 faPool by
   `Math.max(valueNow, 15×impactPts)` (compute impact lazily is NOT needed —
   run simulateAdd for only the top 30 by valueNow, it's ~30 sims, fine).
   Columns: Name / Pos(type) / $now / $dyn / Your impact (pts) / Rec bid.
   Row click = same as selecting in search.

## Constants (top of script, tunable)
`SALARY_CAP = 400`, `PTS_DOLLARS = 15`, `CAP_SOFT_BUFFER = 10`,
`REC_KEEPER_LEAN = 0.6`, `STRETCH_FACTOR = 1.15`, `TOP_TABLE_N = 20`,
`SIM_POOL_N = 30`.

## Edge cases (handle explicitly)
- FA with no projection (`!fa.proj`): exclude from pool entirely.
- Two-way FAs: fine — `calculateAllValues` extras path handles type; sim adds
  them as their `type`.
- `capRoom ≤ 0`: header shows red "over cap"; every advice card says bids
  require a loan/cut first.
- No curr standings loaded: sim still works (pure projections, blend skipped —
  `blendedStatsFor` already falls back). No special casing needed beyond what
  targets.html does.
- No Y1/Y2 files: `dynastyValue === projectedValue`; keeperBreakEven formula
  still works with w1=w2=0 → equals dynastyValue; keeperNote suppressed.

## Verification checklist (do all before claiming done)
1. `python -m http.server` preview → bid.html loads with real data, no console
   errors (check with cache-busted URL — shared.js caches aggressively).
2. Search "": dropdown shows top FAs with sane $now values (compare vs
   fa.html's list — should match its Y0 values).
3. Select a mid-tier FA starter (e.g. a 4.2-ERA innings eater): recommend
   should be low single digits; select the best FA on the wire: recommend
   should be roughly his fa.html value ± lineup fit.
4. Pick an FA at a position where my lineup is stacked → `myImpact$` should be
   well BELOW `valueNow` (fit discount visible). Prospect-type FA (in
   prospects.csv with FV) → dynastyValue reflects the floor, keeperNote sane.
5. Cap numbers: mySalary must equal the sum of my roster's salary column
   (spot-check against roster.csv by hand for 2-3 players).
6. test.html still 90/90 (nothing in shared.js should have changed — if it
   did, STOP and reconsider).
7. Nav link present on all 8 pages, theme.css applied (green/gold look).
8. Commit: bid.html + 7 nav-touched pages, message describing the tool.

## Explicitly OUT of scope (do not build)
- Auto-detecting other teams' likely bids / game-theoretic bid shading.
- Cut suggestions from my roster (v2 — mention in a code comment only).
- Prorated-cap subtleties and loan modeling beyond the warnings above.
