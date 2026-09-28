# Post-Build Queue: Audit, Tracking Probe, Tool-Grade Test — Design

**Status:** approved by the user 2026-09-28. Run after the shopping list
(`plans/2026-09-28-prospect-shopping-list.md`) in this order:

1. **A: plumbing audit.** Fix any real bug it finds before anything else uses the
   data.
2. **B: tracking probe.** Independent of A.
3. **C: tool-grade test.** Run after A, so it scores clean data.

**Plans:**
- `plans/2026-09-28-pipeline-audit.md`
- `plans/2026-09-28-minors-tracking-probe.md`
- `plans/2026-09-28-toolgrade-test.md`

**Why these three:** the user asked for a full audit once the shopping list is
built, and questioned how little Statcast and interactions added. These answer
with facts and one fixed test, not by re-mining seasons we've already seen.

## A. Plumbing audit: does the pipeline compute what we think?

`audit_pipeline.py` runs scripted checks over the real cached data and prints
PASS/FAIL with details to `cache/audit_report.txt`. It fixes nothing: each FAIL
goes to Opus. A real bug gets fixed and the chain rerun (`model3c_base.py` →
`model3c_final.py` → `consensus_gate.py` → `build_shopping_list.py`). A bug fix
is legitimate; changing features or rules because of results is not.

**The checks:**
1. **Raw rows:**
   - no 2020 rows, and levels 11–14 only;
   - one row per player-season-level;
   - no Mexican League rows;
   - counting stats consistent (AB ≤ PA, H ≤ AB, HR ≤ H, SO and BB ≤ PA);
   - swing data consistent (whiffs ≤ swings ≤ pitches);
   - no zero-whiff rows with 100+ swings (a sign of missing advanced data);
   - swing-data coverage by season (information).
2. **Model rows:**
   - every row traces to one raw row with 150+ PA;
   - no established hitters (300+ prior MLB PA);
   - one row per player-season-level;
   - level flags match the level;
   - 2021's previous season is 2019;
   - repeat-level and multi-level flags recompute;
   - **every feature equals its raw stat z-scored within level-season,
     re-derived for all rows.** This checks the wiring end to end.

   The stat definitions themselves were reviewed by reading on 2026-09-28:
   K% = SO/PA, ISO = SLG − AVG, whiff = whiffs/swings, swinging-strike rate =
   whiffs/pitches, swing = swings/pitches.
3. **Labels:**
   - one label per player-season;
   - hitter ranks run 1..n per season with the best value first;
   - the rank-value curve at 2019/2022/2026 uses no later season;
   - 2020 is excluded from the curve;
   - label PA matches StatsAPI MLB PA on 60 random hitter-seasons;
   - the top 5 seasons for 2019/2023/2026 are printed for an eyeball check.
4. **As-of discipline:**
   - At every decision vantage (plus soon 2024), recomputing each training row's
     answer with only MLB seasons ≤ the vantage gives the same answer, and no
     test-class player is in training.
   - Production training uses only cohorts whose answers are known.
   - 2024 refuses to open without `unseal`.
5. **Outputs:**
   - `hitter_ratings.csv` has one row per player;
   - rating percentiles fall as the rating falls;
   - odds are within [0, 1];
   - every rated hitter has a 2026 model row;
   - no established hitters are rated;
   - in `prospect_model.json`, graded keys are unique board hitters and ready ranks
     run 1..n;
   - graded and ungraded are disjoint and together cover every rated hitter.
6. **Test coverage:** modules without a test file (information).

## B. Minor-league tracking probe: what exists below AAA?

The step-1 tracking score uses **AAA only** (2022 PCL, 2023+ all). Our fetcher's
notes say the **Florida State League (Single-A) has carried exit velocity and
launch angle since 2021**, and we never used it. Other lower-minors leagues may
have gained tracking since. Nothing below AAA is on disk.

**Probe:** `probe_minors_tracking.py`.
- For each season 2021–2026, each level (AA, High-A, Single-A) and each home
  league, it fetches **4 complete game records spread across the season**. That's
  about 216 requests, roughly 4 minutes at the shared 1 request/second throttle,
  cached under the gitignored `cache/pbp_live/`.
- For each sampled game it counts the balls in play (pitch codes X/D/E) that carry
  exit velocity.
- **Rule (set in advance):** a league-season **has tracking** if ≥ 3 of its 4
  sampled games have EV on ≥ 80% of balls in play.
- Output: `cache/minors_tracking_probe.json` and a table.

**What it decides:** availability only.
- **None found below AAA (or only FSL):** the question closes. The spec records
  that lower-minors tracking isn't available at scale in game records.
- **Several league-seasons found:** Opus writes a follow-up design (parity check
  vs MLB, offsets, extending the step-1 score). One honest caveat: usefulness is
  gated by outcome history. A 2021 Single-A class's 4-year rating answer arrived
  only in 2025, so even real data would be thin until about 2028.

**Security audit first**, as for every network step:
- stdlib plus installed packages only;
- the only host is `statsapi.mlb.com`;
- no credentials;
- `git ls-files prospects-model/cache` is empty.

## C. Tool-grade test: pre-registered, run once

**Hypothesis:** for this league's fantasy value (4×4: R, HR, OBP, SLG), FanGraphs'
**bat grades** rank graded hitters better than FV. FV also prices defense,
position and speed, which score nothing here.

**Fixed rules, written before anyone looks:**
- `bat = (Hit future + Game Power future) / 2`, from the same Board row as FV.
  Ties are broken by FanGraphs' order (`+ fv_score / 100`, which never crosses a
  2.5-point grade step).
- **The population is plan C's graded group:** class Y's prospects matched to list
  Y+1, one row per player, complete on the model's features. Players missing
  either tool grade are dropped from both rankings, so both rankings score
  identical players.
- **Classes:**
  - Rating: 2019 / 2021 / 2022.
  - Soon: 2021 / 2022 / 2023. Soon 2024 is information only.
- **Scoring:** head-to-head against FanGraphs' order (`consensus.head_to_head`),
  judged by **plan C's adoption rule** (≥ 1 SE at 2 of 3 classes, none ≤ −2 SE,
  mean top-50 change ≥ −0.04).
- **One formula, one run.** No alternative weightings after seeing the result.

**Snapshot check first:** tool grades must be per-list snapshots, like FV. Across
consecutive lists, some players' Hit future grades must change. If any list pair
shows zero changes, the run stops.

**Consequences (set in advance):**
- **Rating passes:** the shopping list's "Best prospects" lens gains an optional
  **"Bat grade" sort**, labeled provisional. FV stays the default until a future
  class confirms.
- **Soon passes:** nothing changes now. Opus may pre-register "bat grade in the
  blend" for future classes.
- **Neither passes:** closed. FV stands.

Seasons already seen make any pass weaker evidence than plan C's. That's why a
pass earns an optional, labeled sort and not a new default.

## Results (run 2026-09-28 overnight on Sonnet, reviewed on Opus)

### A. Plumbing audit: 0 FAILs

All six sections passed (`cache/audit_report.txt`):
- The feature re-derivation matched every row exactly (max difference 0).
- No as-of leak or train/test overlap at any of the eight vantage checks.
- Label PA matched StatsAPI on all 60 sampled hitter-seasons.
- Swing data covers 100% of 150+ PA rows in every season.
- Every `psmodel` module has a test file.

The eyeball check reads right: the 2019 top 5 are Trout, Bellinger, Yelich, Bregman
and Rendon, and 2023's are Acuña, Olson, Ohtani, Betts and Freeman.

**What a clean audit does not prove:**
- Two checks reuse the pipeline's own functions. The feature check confirms the
  wiring and the standardization, not the stat definitions; those were reviewed by
  reading. The PA check confirms the season and player join, not the SGP arithmetic.
- The SGP valuation itself was not re-derived independently.

**SGP follow-up (same night, Opus): closed.** The review first said the SGP
arithmetic had never been checked against the site, and that was wrong.
- **Formula:** `parity/compare.py` already runs `shared.js`'s own `calcPlayerSGP`
  in Node on 10 fixed cases. Rerun against today's `shared.js`: **PASS, max
  difference 0**.
- **Inputs:** checked by reading, line for line. `context.hitter_replacement` and
  `pitcher_replacement` follow `computeFABaselines`' future-year rule: the same 100
  PA / 30 IP floors, the same `valProxy` ranking, the same 8 / 10 cohorts, and the
  same skip-the-rostered-count step.
- **Deliberate, documented differences:**
  - Denominators come from the real standings spread and are held fixed across
    years. The live site uses its projected lineups, which collapse in late
    season.
  - No positional offsets (`labels.py` header).
- **One small drift:** the rostered counts are fixed at 295 hitters / 231 pitchers
  (measured 9/26), against 292 / 227 today. That moves the replacement cohort by
  about 3 ranks, which is negligible. The SGP chain is audited end to end.

**Found outside the audit, in the review:** the shopping-list page's sort
comparator was inverted. It came from the 2026-06-27 rework and is not a model
bug. `sortDir = -1` sorted ascending while the arrow said descending, so "Best
prospects" opened on the lowest FV grades and the Ungraded view on the weakest
model reads. Fixed in `eaa04de`. `targets.html` has the identical pattern, and a
separate task was offered for it.

### B. Tracking probe: only the Florida State League (question closed)

6 of 54 league-seasons are tracked, and all 6 are home league 123, the Florida
State League (Single-A):
- It showed exit velocity on 93–100% of balls in play in every sampled game, every
  season 2021–2026.
- Every other league showed exactly 0% in all four sampled games, every year: AA
  (Texas 109, Southern 111, Eastern 113), High-A (South Atlantic 116, Midwest 118,
  Northwest 126) and Single-A (California 110, Carolina 122). The result is
  unambiguous.

**Rule applied as set in advance ("only FSL → closes"):** lower-minors tracking
isn't available at scale, and the Statcast question is closed for now. The FSL
goes on the 3c revisit list (about 2028, once three FSL classes have rating
answers).

### C. Tool-grade test: FV stands (closed)

The snapshot check passed: Hit future grades changed for 35–64% of players between
consecutive lists, so they are per-list grades like FV. Bat grades lost to FV
everywhere:

| Output | 2019 | 2021 | 2022 | 2023 | Wins |
|---|---|---|---|---|---|
| Rating | z −1.0 | z −2.7 | z −2.5 | — | 0/3 |
| Soon | — | z −1.9 | z −0.2 | z +0.4 | 0/3 |

Soon 2024 (information only): z +0.7.

Per the rule, this is **closed**, with no shopping-list change.

The hypothesis behind it, that FV's weight on defense, position and speed
misprices hitters for 4×4, looks wrong: the bat-only grade was clearly *worse*
for "how good".

**One plausible reading, not tested:** defense and position buy playing time, and
counting stats and qualifying PA come from playing time. FV also folds in risk and
proximity. Either way, "follow FV" for ceiling stands, now with a second
independent confirmation.

## Out of scope

Pitcher model. Any new features or interactions on seen seasons. Bulk downloads.
