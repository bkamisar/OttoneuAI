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

1. **Team aggregation** — per team: `optimizeHitterLineup` (12 active slots under
   a **PA budget**; ranked by `HIT_RANK_W` rate quality, not volume — see §3),
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
- Hitting rates blend by season-elapsed fraction `games/162`.
- **Hitting uses a PA budget per active slot** — the analog of the pitching
  innings budget. `PA_PER_SLOT × rosProrationFactor()` (full-season `PA_PER_SLOT`
  for Y1/Y2 passes, mirroring `ipBudget`). The **primary occupant is never
  capped**: a slot's hard capacity is `SLOT_CAP` games and one player cannot
  exceed it, so `PA_PER_SLOT` is the *expected* PA of a full-timer, not a
  ceiling. When injury or part-time usage leaves a slot short by more than
  `PA_MIN_SHARE`, bench bats absorb the remainder as scaled clones under derived
  keys (`C_2`, `OF4_3`; up to 3 contributors per slot). Assignment is two-phase —
  every primary first, then supplementation — so a scarce bench bat is not
  consumed by an earlier slot's shortfall. Hitters are ranked by `hitterRateValue`
  (`HIT_RANK_W`: obp 1.0, slg 0.905, hr/pa 2.34, r/pa 1.10), **not** `pa × OPS`
  and **not** raw OPS: volume is handled by the budget, and OPS ignores HR/R
  (~24% of a starter's rank score). Measured Aug 2026: 37 of 181 filled slots
  shared (20%).

## 4. Dynasty values (`calculateDynastyValues`)

`dynasty = Y0 + 0.90×Y1 + 0.81×Y2` (weights user-tunable, ~10%/yr discount).

- **Y2 fallback:** a player with Y1 but no Y2 line reuses Y1. Y2 files cover
  only ~54% of rostered players and almost no pitchers — without the fallback
  every ace lost a 0.81-weighted year AND the fixed pool spread over half as
  many claimants, inflating everyone else.
- **Dynasty cost — contracts are OPTIONS, not obligations.** Cutting is free at
  season's end, so a contract is priced at the best available holding plan, not
  a forced 3-year hold. `computeContractHorizon` evaluates three horizons and
  returns the winner's value, cost and surplus together, plus `holdHorizon`:

  | Horizon | Value | Cost |
  |---|---|---|
  | H0 "rental" | `y0` | `s0` |
  | H1 | `y0 + w1×y1` | `s0 + w1×(s0+2)` |
  | H2 "keeper" | `y0 + w1×y1 + w2×y2` | `s0 + w1×(s0+2) + w2×(s0+4)` |

  Ottoneu's +$2/yr base escalation still drives the cost side. Because holding
  costs +$2/+$4 while a flat player earns the same, **H2 only wins when next
  year's value exceeds salary by ≈$3** — that spread is the keep/cut bar.
  **Do NOT prorate the year-0 salary.** Y0 *stat lines* are rest-of-season, but
  Y0 *dollar values* are normalized to the full $4,800 pool regardless of date
  (verified: rostered Y0 values sum to exactly $4800 on Aug 2 with
  `rosProrationFactor` 0.30) — a player's Y0 value is his SHARE of that pool, so
  value and salary are already on the same scale. Prorating cost against
  unprorated value inflates every surplus and makes H0 win spuriously (it once
  priced Bobby Witt Jr. at $68 as a +$16 rental). Invariant #1 governs
  projection stat lines, not pool-normalized dollars.
- **Reading the `holdHorizon` split.** ~60% of rostered players resolve to H0,
  which sounds alarming and is not. About half of those are $1-3 fringe/deep-bench
  contracts whose churn nobody thinks of as "cutting someone"; meaningful cuts
  ($4+) are ~13 per team and real contributors ($16+) ~4.6 per team, matching the
  league's actual offseason behavior. The calls are decisive, not coin-flips —
  >90% of H0 wins beat H2 by more than $3. **`holdHorizon === 0` therefore does
  NOT mean "rental trade target"** — for most of that population it just means
  "cut candidate." Any consumer wanting rentals must also require meaningful Y0
  value.
- **Known simplification:** arbitration allocations add ~$4-8/yr more to star
  salaries; the +$2/+$4 understates star keeper costs slightly, and option-valuing
  raises surplus further, so dynasty surplus on stars reads a touch rich. If
  tuning: raise the +2/+4, don't touch the value side.
- **Prospect floor** (`prospectDynastyValue`): scouting-based expected value
  under `max(model, floor)`. Top-100 rank curve `PROSPECT_RANK_CURVE`
  (#1 $62 → #100 $15, interpolated) for ranked prospects; `FV_DYNASTY_FLOORS`
  (FV45 $4 → FV80 $55) for unranked; ×0.72 pitching prospects; ×0.85
  High/Extreme risk, ×1.12 Low. Calibrated to public surplus-value research +
  this league's market (Made $59, Basallo $45, De Vries $41). The floor never
  overrides a higher projection-based value (e.g. McLean $78). The floor applies
  to the **H2 value only** — a prospect's scouting-based worth is inherently
  long-horizon — so prospects resolve to `holdHorizon = 2` and the floor stays
  `max(model, floor)`, never additive.
- Values are present values of the **winning horizon**, not always 3 seasons.
  Compare only against other dynasty numbers or the matching `dynastyCost`.

## 5. Trade finder (targets.html)

- **Marginal value (`tradefinder.js`).** A player's worth is measured AGAINST A
  SPECIFIC ROSTER: re-optimize the lineup with him removed and score the delta in
  SGP-denominator units, converted at `TF_PTS_DOLLARS` ($15/point, matching
  `PTS_DOLLARS`). `tfBlockedness` = absolute Y0 value − marginal value to his own
  team, so a blocked 6th outfielder reads as a trade asset. `tfNeedGaps` compares
  each lineup slot's occupant against the league-median occupant of that slot
  (self-relative, like the SGP denominators). Compare blockedness against
  **`projValue`, never `dynastyValue`** — marginals derive from Y0 production; the
  dynasty lens enters later at the fairness/utility stage. Cost is trivial: 518
  marginals across 12 teams run in ~95ms.
  - Negative marginals are legitimate, not bugs. A **hitter** with empty PA can
    drag team OBP/SLG, so removing him raises the rate cats. A **pitcher** whose
    innings crowd better arms out of the capped budget likewise scores negative.
  - Marginals inherit the lineup model, so they are only as good as
    `optimizeHitterLineup`. The volume-bias flaw that once made Judge and Soto
    read as $0-marginal "blocked assets" is fixed (§3, §8) — they now start and
    carry $29.3 / $30.7. A player at zero marginal genuinely does not crack his
    lineup.
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
| `PA_PER_SLOT` | shared.js | 650 | full-season PA one lineup slot absorbs (prorated for Y0) |
| `PA_FULL_RATE_FULL` | shared.js | 150 | PA below which a hitter's rate is ramped down as a partial sample (scaled to budget) |
| `PA_MIN_SHARE_FULL` | shared.js | 100 | shortfall below which a slot is not supplemented (scaled to budget) |
| `HIT_RANK_W` | shared.js | obp 1.0 / slg 0.905 / hr-pa 2.34 / r-pa 1.10 | lineup ranking weights; `w=1/(T_PA·D_OBP)`, `0.9/(T_AB·D_SLG)`, `1/D_HR`, `1/D_R` — recompute if denominators shift a lot |
| `TF_PTS_DOLLARS` | tradefinder.js | 15 | $ per standings point; keep in sync with `PTS_DOLLARS` |
| `TF_BLOCK_MIN` | tradefinder.js | 5 | $ stranded before a player is a surplus asset |
| `TF_NEED_MIN` | tradefinder.js | 5 | $ below median before a slot is a hole |
| `TF_GAIN_MIN` | tradefinder.js | 5 | $ a player must gain by moving to be worth proposing |

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
9. Dynasty value and dynasty cost must ALWAYS report the same holding horizon.
   Reporting a 3-season value against a 1-season cost credits production that
   was never paid for. `computeContractHorizon` returns the triple together for
   exactly this reason — never recombine a `dynastyValue` from one horizon with
   a cost from another. This is also load-bearing for the trade finder: the
   fairness filter matches value-for-value, so a rental must carry his RENTAL
   value or no rental trade can ever clear.
10. Do not prorate salary against Y0 dollar values. Y0 dollars are normalized to
   the full $4,800 pool at any date, so salary and value are already on the same
   scale (see §4). Invariant #1's RoS-vs-full-season distinction applies to
   projection STAT LINES only.

## 8. Known limitations (accepted, documented)

- ~~`optimizeHitterLineup` volume bias~~ — **RESOLVED 2026-08-03** (§3). It ranked by
  `pa × (obp+slg)`, so injured stars were benched behind healthy mediocrities and
  dropped from team aggregation entirely: Judge (.971 OPS, 97 RoS PA) behind Rafaela
  (.711, 213 PA), Soto (.952, 136 PA) behind Varsho (.718, 187 PA) — 16 bad pairings
  across 3 of 12 teams. Two defects, measured on the Misiorowski Index roster:
  **misranking** (Judge beat Rafaela for the slot by 0.915 z ≈ $13.7, yet lost it) and
  the larger **either/or assumption** (letting both contribute was worth a further
  1.694 z ≈ $25.4). Fixed by rate-first ranking (`HIT_RANK_W`) plus PA-budget slot
  supplementation. After: both start, marginals $29.3 / $30.7, 20% of slots shared,
  Y0 pool still $4800, hitShare 52.2% → 53.9%.
- **§2 anchors need seasonal recalibration** (drift predates the lineup fix). They were
  set from July data; on Aug 2 the pool concentrates into fewer remaining PA/IP, so the
  top non-Ohtani hitter reads ~$72 (anchor band $55-65) and ~48% sit at the $1 floor
  (anchor ~35%). Both were already out of band *before* the PA-budget change, which
  moved them only 1-3%. Re-derive the bands rather than chasing them.
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
