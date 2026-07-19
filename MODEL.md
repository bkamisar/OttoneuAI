# MODEL.md — How the Ottoneu Tool Suite Computes Everything

Reference for maintaining `shared.js` and the trade tools. Read this before
changing any valuation math. Last full audit: 2026-07-04 (league-wide output
audit; every section below was verified against live league data that day).

League context: 12-team Ottoneu **4×4** (R / HR / OBP / SLG · K / HR9 / ERA /
WHIP), $400 cap per team, 1,500 IP season cap, dynasty (keep-forever) format.
Because it's 4 hitting + 4 pitching categories, scoring opportunity is split
~50/50 — do not "fix" hitShare toward the 5×5 folk value of 60-65%.

---

## 1. Data feeds

| File | Source | Cadence |
|---|---|---|
| `data/proj_hitting.csv` / `proj_pitching.csv` | Google Apps Script → FanGraphs Steamer **rest-of-season** (`steamerr`) | daily ~8:57 ET |
| `data/standings.csv` | Apps Script → Ottoneu `standingsMeter` AJAX | daily ~7:32 ET |
| `data/roster.csv` | Apps Script → Ottoneu `rosterexport?csv=1` | daily (trigger) |
| `proj_*_y1/y2.csv` | manual upload (full-season projections) | occasional |
| `data/prospects.csv` | manual (FanGraphs The Board export) | occasional |

Key fact that shapes everything: **Y0 projections are REST-OF-SEASON** (what's
left, not the full year), while **Y1/Y2 files are full-season**. Several past
bugs came from conflating these.

Pages load CSVs via `autoLoadFromRepo()` (retries transient failures; stamps
real last-commit time via the GitHub commits API, cached 30 min). Manual
browser uploads of repo-managed files get overwritten on next page load — keep
the repo fresh instead.

`standingsMeter` returns ONLY the 8 category totals. Per-team Games/IP are
calendar-estimated and uniform (a known approximation; don't chase real
per-team values — the endpoint doesn't have them).

## 2. Y0 player valuation (`calculateAllValues`)

SGP model: a player's value = standings-gain-points above replacement × $/SGP.

1. **Team aggregation** — per team: `optimizeHitterLineup` (12 active slots),
   `selectPitchers` under an innings budget. **The Y0 budget is
   `IP_MAX × rosProrationFactor()`** (the league cap's remaining share,
   ~694 IP in early July). Without this cap the team-SO stdev was 191.6 (vs
   HR's 17.4) because rosters hold 655–1,172 RoS IP, and strikeouts became
   nearly worthless in SGP terms. Y1/Y2 passes use the full 1,500.
2. **SGP denominators** — stdev of each category across the 12 aggregated
   teams (`calcSGPDenoms`). Small-sample noisy but self-consistent.
3. **Replacement level** — `FA_BASELINES`: the averaged stat line of the top
   free-agent cohort (8 hitters ≥100 PA / 10 pitchers ≥30 IP, ranked by
   `valProxy`). "Replacement = best freely available alternative." Computed
   per projection year. Fallback: weakest roster quartile (unit tests).
4. **Player SGP** (`calcPlayerSGP`) — marginal vs an FA filling the SAME
   playing time: counting stats compare against the baseline **pro-rated to
   the player's PA/IP** (`paRatio`/`ipRatio`); rate stats scale by
   `pa/avgPA` (or `ip/avgIP`). Both halves now use consistent volume. (Before
   this, a 184-PA catcher ate a full-time FA's HR/R totals as a penalty →
   Will Smith valued $1 while 156-PA Judge got $24.)
5. **Dollars** — reserve $1 × rostered players (~$480), distribute the rest of
   the $4,800 pool by SGP share. The hit/pitch **split** comes from *starter*
   SGP only (lineup + capped pitcher pool) — rosters hold more pitching volume
   than the cap allows on the field, and using all rostered SGP tilted the
   split. **Rates** still divide by all positive SGP so the pool is conserved.
   Every rostered player WITH a matched projection gets a $1 floor; FAs don't
   (no roster spot), and unmatched (`noProj`) rostered players get no entry at
   all — they are also excluded from the $1 reserve, which is what keeps the
   pool conserved (2026-07-19 audit, finding 3).
6. **Two-way players** (type `H` with `projP` ≥ 30 IP): pitching SGP added on
   top of hitting SGP. Valid because hit/pit $-rates are close by construction.

Sanity anchors (July 2026 data): hitShare ≈ 50%, top hitter (non-Ohtani) ≈
$55-65 (~1.2% of pool), aces $45-70, elite K-relievers $15-30, ~35% of
rostered players at the $1 floor. Diagnostic: `[values]` console line.

## 3. Rest-of-season standings blend (`blendStats`)

Used by standings.html RoS mode and targets.html (weak-cat detection, trade
simulation, status auto-detect).

- Counting stats: `current actuals + RoS projection` (projection is already
  "remaining" — never subtract).
- Pitching respects the innings cap: remaining IP = `min(proj._ip, IP_MAX −
  innings thrown)`; SO scales by that ratio; rates weight by actual IP shares.
  (Without this, staff-hoarding teams got up to +352 phantom K.)
- Hitting rates blend by season-elapsed fraction `games/162`. Hitting needs no
  volume cap (one hitter per active slot).

## 4. Dynasty values (`calculateDynastyValues`)

`dynasty = Y0 + 0.90×Y1 + 0.81×Y2` (weights user-tunable, ~10%/yr discount).

- **Y2 fallback:** a player with Y1 but no Y2 line reuses Y1. Y2 files cover
  only ~54% of rostered players and almost no pitchers — without the fallback
  every ace lost a 0.81-weighted year AND the fixed pool spread over half as
  many claimants, inflating everyone else.
- **Dynasty cost:** `s0 + 0.90×(s0+2) + 0.81×(s0+4)` — Ottoneu's +$2/yr base
  escalation. **Known simplification:** arbitration allocations add ~$4-8/yr
  more to star salaries; the +$2/+$4 understates star keeper costs slightly,
  so dynasty surplus on stars reads a touch rich. If tuning: raise the +2/+4,
  don't touch the value side.
- **Prospect floor** (`prospectDynastyValue`): scouting-based expected value
  under `max(model, floor)`. Top-100 rank curve `PROSPECT_RANK_CURVE`
  (#1 $62 → #100 $15, interpolated) for ranked prospects; `FV_DYNASTY_FLOORS`
  (FV45 $4 → FV80 $55) for unranked; ×0.72 pitching prospects; ×0.85
  High/Extreme risk, ×1.12 Low. Calibrated to public surplus-value research +
  this league's market (Made $59, Basallo $45, De Vries $41). The floor never
  overrides a higher projection-based value (e.g. McLean $78).
- Values are 3-season present values — they run to ~$330 (Ohtani); that scale
  is intentional, compare only against other dynasty numbers or dynastyCost.

## 5. Trade finder (targets.html)

- **Team status:** auto from blended standings (top/bottom third = contender/
  rebuilder), user-overridable per team (persisted). Status sets each team's
  **valuation lens**: contenders price players at current value, rebuilders at
  dynasty value. That asymmetry is what makes buy-now/sell-future trades work.
- **Candidate generation:** package combos (≤3 players), cheap fairness
  pre-filter first: receiving side must be covered in the *counterparty's*
  lens within `tradeTol` (30%), plus a consolidation premium (`CONSOL_PREM`
  15% extra per additional player on the bulkier side — no 3-scrubs-for-a-star).
- **Simulation:** survivors get a full standings re-run (`simulateTrade`,
  both rosters re-optimized, blended with actuals). This also auto-enforces
  "trade from strength" — dealing a needed player shows up as a points loss.
- **Acceptance:** each side computes dollar utility:
  `PTS_DOLLARS(15) × (ptsΔ + zΔ) × PTS_WEIGHT[status] + dynastySurplusΔ ×
  FUTURE_WEIGHT[status]`, accept at ≥ $1 (`MIN_UTILITY`). Weights: contender
  1.0/0.25, fringe 0.6/0.6, rebuilder 0.15/1.0. `zΔ` (continuous category
  movement in stdevs) counts at FULL point weight — with 12 teams, 1 stdev ≈ 1
  expected rank; discounting it starves the finder because integer roto points
  rarely move on a single trade. Future gains use dynasty **surplus** (net of
  escalating cost), not gross value.
- **Cap check:** post-trade salary totals vs $400; over-cap → warning on the
  option (soft — Ottoneu allows loans). Full salaries, matching Ottoneu cap
  accounting.
- Expected behavior: FEW results is correct. Nobody sells their ace to a
  rival; superstars are unaffordable; marginal trades die at the utility gate.

## 6. Tunable knobs (safe to adjust; keep this table current)

| Knob | Where | Current | Meaning |
|---|---|---|---|
| dynasty weights | Data Hub UI | 0.90 / 0.81 | future-year discounts |
| `PROSPECT_RANK_CURVE`, `FV_DYNASTY_FLOORS` | shared.js | see §4 | prospect market anchors |
| pitcher/risk multipliers | `prospectDynastyValue` | 0.72 / 0.85 / 1.12 | prospect adjustments |
| `PTS_DOLLARS`, `PTS_WEIGHT`, `FUTURE_WEIGHT`, `MIN_UTILITY` | targets.html | 15 / table / table / 1 | trade acceptance |
| `tradeTol`, `CONSOL_PREM` | targets.html | 30% / 15% | fairness window |
| `FA_COHORT_H/P`, `FA_MIN_PA/IP` | shared.js | 8/10, 100/30 | replacement baseline |
| dynasty cost bumps | `calculateDynastyValues` | +$2 / +$4 | keeper escalation (see §4 caveat) |

## 7. Invariants — do not re-break

1. Y0 projections are RoS; Y1/Y2 are full-season. Any blend/cap logic must
   respect which one it's handling (`yearKey`).
2. The 1,500 IP cap must be honored anywhere team pitching totals are
   aggregated (valuation budget AND standings blend — two separate sites).
3. Counting-stat handling in `calcPlayerSGP` is asymmetric ON PURPOSE:
   HITTER HR/R pro-rate the replacement to the player's PA (part-time bats are
   a fixed role; don't penalize them vs a full-time total — the Will Smith fix).
   PITCHER strikeouts do NOT pro-rate — SO is pure volume, so a low-inning
   reliever is correctly docked for contributing fewer raw K's. Do not
   "unify" these; pro-rating pitcher SO re-inflates relievers to ~47% of
   pitching value. Rate stats (OBP/SLG, ERA/WHIP/HR9) are IP/PA-weighted, so
   low-volume arms' good ratios already earn proportionally less.
4. Name matching is type-separated everywhere (hitter names look up hitting
   projections only) — prevents Ohtani/name-collision clobbering.
5. ~50% hitShare is CORRECT for 4×4. Don't tune toward 5×5 intuition.
6. Prospect floors are `max(model, floor)` — never additive, never overriding
   a better projection-based value.
7. Browser caching: shared.js changes may not appear until a hard refresh;
   verify with an isolated fetch-eval before debugging "unchanged" behavior.
8. FA baselines derive from the ROSTERED_IDS/ROSTERED_NAMES snapshot captured
   by `matchPlayers` — never from the array passed to `attachYearProjections`.
   It is safe to attach year projections to any player array (FA pools,
   prospects); before this rule, attaching to the FA pool redefined "the
   roster" as the FA pool, turning the Y1/Y2 replacement baseline into the
   league's rostered stars (ERA 3.18) and inflating elite FA relievers to
   $200+ dynasty while zeroing FA hitters' future value.

## 8. Known limitations (accepted, documented)

- Arbitration not modeled beyond +$2/+$4 (star keeper costs slightly light).
- Positional scarcity IS modeled for hitters now (`computePositionalOffsets` /
  `hitterSGP`): per-position HR/SLG/OBP offsets vs the slot-weighted average,
  each hitter graded at his best eligible position; nets ~0 on the pool
  (redistribution only). FAs carry no position data → general baseline, so the
  bid advisor / FA finder aren't position-adjusted. In THIS league catchers are
  OBP-rich, so the effect is a power-scarcity credit (C/2B/SS up on HR/SLG,
  1B/corners down), not on-base.
- Games/IP in standings.csv uniform across teams (source has no better data).
- SGP denominators from a 12-team stdev are noisy year to year.
- Prospect floors are expected values; the true outcome distribution is huge.
- Roki Sasaki-type cases: the model reflects pessimistic projections, not
  market hype — divergence there is an input opinion, not a bug.
- **Seasonal edges (2026-07-19 audit, finding 2)**: after Sept 28
  `rosProrationFactor()` = 0, so Y0 runs at a 150-IP budget on stale RoS
  files — Y0 values are unreliable ALL OFFSEASON (use dynasty/Y1/Y2). In
  September the `FA_MIN_PA=100` role floor exceeds max RoS PA, so the FA
  hitter baseline silently flips to the weakest-quartile fallback (arms
  follow via `FA_MIN_IP=30`). Queued fix: prorate the floors.
- **Two-way FREE AGENTS lose pitching value** (2026-07-19 audit, finding 1):
  the `extraPlayers` path has no projP block and `getFreeAgents` dedupe
  keeps only the hitting entry. No live case today; fix before an Ohtani-
  type reaches waivers. Full audit: docs/2026-07-19-shared-js-math-audit.md.
