# Step 1: Hitter Tracking Score — Design (3b, plan B)

**Date:** 2026-09-27
**Status:** Approved in brainstorming
**Parent spec:** `2026-09-26-prospect-model-design.md` (3b). Plan A (`plans/2026-09-27-tracking-parity.md`) built the inputs.

## Why this step exists

The full model (3c) learns from prospects whose careers are known (2016–2023).
Exit velocity and the other tracking metrics were not recorded in AAA until
2022–23, so almost none of those prospects have them — the full model cannot
learn what "91 mph" is worth. MLB has tracking for every hitter since 2015 with
known next-season results, thousands of examples. So step 1 learns what tracking
metrics are worth **on MLB**, translates AAA readings onto the MLB scale, and
hands the full model a single **tracking score**. The full model then only has to
learn how much to trust that one number. (Earlier notes call this "the bridge.")

## Decisions

| Question | Decision |
|---|---|
| Deliverable | **Research only.** The validated step-1 code + report. No ratings file or UI; ratings come from 3c. The user can't pick anyone up for about a month. |
| Target | **Value at a regular's playing time:** next-season 4×4 SGP rescaled to 600 PA. Answers "how good when he plays"; *when* he plays is 3c's job (age, level). |
| Inputs | **Tracking metrics + age only.** Box-score stats join in 3c. Physics (EV) translates across levels; box scores (PCL inflation) do not. |
| Spray | **Test first on MLB with Savant's numbers.** No new download. |

## Part 1 — Learning on MLB

**Rows:** one per MLB hitter and season pair: metrics in season *t* → value in
*t+1*, for t = 2015–2025 (`cache/mlb_tracking.csv` → `cache/labels.csv`).

**Target:** `value(t+1) × 600 / PA(t+1)`. The label math is homogeneous in playing
time: scaling PA, R and HR by k while keeping OBP and SLG scales SGP by exactly k,
replacement term included (`labels.hitter_sgp`). So this comes straight from
`labels.csv` with no new data and no change to the parity-gated label code.
- A row requires **≥100 PA in t+1** (the spec's existing peak-eligible floor) and is
  **weighted by PA(t+1)**.
- **Useful** = ≥0.61 SGP at 600 PA (the starter-quality bar from the whiff test).
- A row requires **≥100 batted balls in t**, from the Savant exit-velocity board's
  batted-ball count, so metrics aren't noise.

**Inputs:** age in season *t* (from cached MLB season stats) plus 17 of the 18
parity-checked metrics, in groups:
- **Power:** exit_velocity_avg, avg_best_speed, max_hit_speed, hard_hit_percent, barrel_batted_rate
- **Launch profile:** launch_angle_avg, sweet_spot_percent, GB / LD / FB / popup %
- **Contact:** whiff_percent, iz_contact_percent, oz_contact_percent
- **Discipline:** swing_percent, oz_swing_percent, z_swing_percent
- **Spray (test group):** Savant pull / straightaway / opposite %, plus a pulled-air
  rate if Savant publishes one (verify; see Spray below). Distance is left out:
  it is mostly EV × launch angle.

**Tests** (reuse `psmodel/evaluate.py`: player-grouped 5-fold CV, 10 shuffles):
1. **Group adoption:** each group is tested as the family against a base of age
   + all *other* groups ("does it add beyond everything else?"). It is kept only
   if it improves out-of-sample rank accuracy without lowering the top-N hit rate
   in **≥8 of 10 shuffles** (the whiff-test rule, `evaluate.adopt`). Power and
   launch profile overlap, so if both fail alone, the pair is tested jointly
   against age + the rest and reported as "jointly adopted" if it passes.
2. **Ridge vs gradient-boosted trees:** keep the better model out-of-sample.
3. **Tracking vs box score (report only):** the same target predicted from MLB
   box-score stats in *t* (K%, BB%, ISO, OBP, SLG, HR/PA, age) vs box score +
   tracking. Answers whether tracking is worth the effort, on thousands of rows.
4. **Robustness (report only):** rerun excluding 2015 (Statcast's first year had
   spotty exit-velocity coverage) and excluding 2020 (60 games).

**Interaction report:** for the tree model, pairwise interaction strength
(Friedman's H) for the top 10 pairs. A pair is labeled a *finding* only if it
ranks top-10 in ≥8 of 10 shuffles; otherwise it is a *hypothesis*. Plain-language
lines, e.g. "power pays more with lift."

**Known bias:** the ≥100-PA floor in *t+1* drops hitters who were hurt or
demoted, so step 1 learns "how good when he plays." That is the intended
question; playing-time risk belongs to 3c.

## Part 2 — AAA translation, prospect check, handoff

**Translation:** learned from hitters with AAA and MLB readings in the **same
season, 2023–26** (`cache/aaa_tracking.csv` vs `cache/mlb_tracking.csv`). Each needs
a minimum sample at both levels (default ≥50 batted balls each). The plan's first
task counts how many qualify, and if the count is too thin for a metric, the plan
reports it. Per metric: a **flat offset** by default (e.g. AAA EV reads about
1 mph high → subtract it). A scaling factor is added only if its bootstrap
interval excludes 1 **and** it improves the fit on held-out players. Same player
in the same season, so selection largely cancels. Constant method biases
between our AAA code and Savant's (plan A) are absorbed by the offset.

**Prospect check (a gate, not the foundation):** AAA hitters from 2022 (PCL) and
2023 with ≥100 batted balls → translated → tracking score, compared with their
later MLB value at 600 PA (best season with ≥100 PA after the AAA season):
- **Gate:** Spearman(tracking score, later MLB value) among hitters who reached
  ≥100 MLB PA, with a **bootstrap 95% interval above zero**. If it fails, stop and
  report before 3c uses the score.
- Report only: the useful hit rate by score quintile; arrival rate (reached
  100 MLB PA) by quintile; the same check for a simple AAA box-score baseline
  (OBP, SLG, K%, BB%, age) to see whether the score adds anything.
- The 2024 cohort (only 2025–26 outcomes) is reported separately and does not gate.

**Spray:** if the spray group is adopted on MLB, check parity of our
coordinate-based version against Savant using the **MLB 2023–26 game records
already on disk** (no new download), with the plan-A bar of r ≥ 0.98. Pass → AAA
prospects get spray. Fail → spray is flagged "real in MLB, not measurable in
AAA" and excluded from AAA scoring, with the cost quantified (the MLB fit with vs
without spray). If Savant publishes no pulled-air rate, the pulled-air test falls
back to our own pulled-air computed from the 2023–26 MLB game records (~3
season pairs, reported as lower-powered).

**Handoff to 3c:**
- `psmodel/step1.py`: fit on the cached tables, translate AAA readings, and score
  any hitter-season. **Refit on demand** (seconds on a few thousand rows) rather
  than saving fitted models to disk: nothing serialized to load, nothing to go stale.
- `cache/aaa_translation.csv`: per-metric offsets (and any scale), n, interval.
- `cache/step1_report.txt`: group adoption, ridge vs trees, tracking vs box
  score, robustness, the interaction report, the translation table, the prospect
  check verdict, and the spray verdict.

## Data, network, security

- **Already on disk:** `mlb_tracking.csv`, `aaa_tracking.csv`, `labels.csv`, cached
  MLB season stats (age and box score), MLB game records 2023–26.
- **Network (small):** Savant leaderboards for the spray fields and the
  exit-velocity board's batted-ball count, 2015–2026, about 24 requests to
  `baseballsavant.mlb.com`. Check first which spray fields exist, especially a
  pulled-air rate. Content guards as in `savant.py`. **Security audit before
  it runs.**
- No bulk downloads (`feedback_downloads`); no new packages (numpy, scipy and
  sklearn are already used by `evaluate.py`).

## Out of scope

Pitchers (next, same pipeline); ratings and UI (3c); MLB game records for 2015–22
(fetch only if a test needs them); historic FV grades (3c, one-year join test
first).
