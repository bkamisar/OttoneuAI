# Roto category scores for prospects (design, 2026-10-09)

Designed on Opus with the user; approved in conversation 2026-10-09. Everything
here is fixed BEFORE any result. A change needs a new dated section that says
what was already seen.

## Why

- **The finding behind it:** FV is hard to beat as one "how good" number
  (3c rating, P-F, FV+ rating). It says nothing about **which roto categories**
  a player will help.
- **The goal:** a score per 4x4 category that predicts a prospect's
  contribution there, in the league's own SGP units, validated by a walk-up
  ladder.
- **Out of scope here:** tying scores to the user's team needs, and prices.
  Both are later steps.

## What is predicted

For each prospect at vantage V (the end of season V), each category's **total
SGP contribution over seasons V+1 .. V+4**, with non-arrivals counted as 0.

- **Hitters:** HR, R, OBP, SLG.
- **Pitchers:** K, ERA, WHIP, HR/9.
- **Actual outcomes:**
  - Each MLB season's per-category term from `psmodel/labels.py`
    (`hitter_sgp` / `pitcher_sgp`, split into their four terms), using that
    season's replacement level and the league's fixed denominators, exactly as
    `build_labels.py` does for the total.
  - Summed over the 4 seasons.
  - Terms can be negative: below-replacement production hurts in roto.

## The model: two parts

**Part 2: category rates when he plays** (data-rich; the shape)
- **Training rows:** minor-league player-seasons from 2012 on (the existing
  hitter and pitcher row builders, league-season normalized) whose player
  reached **>= 200 MLB PA (hitters) or >= 50 IP (pitchers)** in seasons
  V+1..V+4.
- **Targets: his MLB rate over that window.**
  - Hitters: HR/PA, R/PA, OBP (PA-weighted), SLG (AB-weighted).
  - Pitchers: K/IP, ERA, WHIP, HR/9 (IP-weighted).
- **Features:** the existing continuous minor-league features, age and level
  flags.
  - Hitters: the `cohorts.GROUPS` features.
  - Pitchers: the `pcohorts.GROUPS` features plus ground-out share z (`fvplus.gb_z`).
- **Model:** ridge per category. No model race.
- **As-of:** fit at vantage V only on cohorts whose window is complete by V
  (`asof.rating_known`). Test players are removed from training.
  - Test vantages are **2019, 2021 and 2022**, the 3c rating vantages.
  - The test population is players with >= 200 PA / 50 IP in their window.
- **"Trustworthy" (pre-registered):** Spearman(predicted rate, actual rate)
  has a 95% player-bootstrap interval above 0 at >= 2 of the 3 vantages.
  - For information only, each category's Spearman is compared with the raw
    minor-league rate alone (no model), to show what the model adds.

**Part 1: playing time** (thin data; FV helps here)
- **Target:** total MLB PA (hitters) or IP (pitchers) over V+1..V+4, with
  non-arrivals as 0.
- **Graded players: a pre-registered race on the 2021 and 2022 classes.**
  - It uses FV+'s strict as-of setup: lists 2017+ paired with class V, training
    on classes with complete windows, >= 300 training players, test players
    removed.
  - The candidates:
    - (a) **FV alone:** `fv_score`;
    - (b) **FV + stats:** ridge on `fv_score` plus the adopted 3c/P rating
      groups (hitters: age_level, contact, power, speed; pitchers: age_level,
      strikeouts).
  - (b) is used only if its pooled Spearman gain over (a) is >= 1 SE
    (pooled z >= 1) with no class at or below −2 SE. Otherwise (a) is used.
  - In production, (a) needs a scale: PA or IP is predicted from `fv_score` by
    ridge on the training classes.
- **Ungraded players:** ridge on the same rating groups, trained on all
  minor-league rows (as-of), with no race.

**The score per category:**
- The expected playing time and the expected rates form an expected stat line.
- The line is 4-season totals: PA or IP is the 4-year total, and counts are
  rate x total.
- It is valued with that category's `labels.py` term at the latest as-of
  season's replacement level, applied to those totals.

## The verdict: walk-up ladders (pre-registered)

- **Population:**
  - graded players of the 2021 and 2022 classes (the Part 1 race classes);
  - separately, ungraded players at vantages 2019, 2021 and 2022.
- **Buckets:** per category, players are split into 5 equal buckets by score.
  Each bucket's mean ACTUAL 4-year contribution in that category is reported,
  with counts.
- **A category's ladder PASSES if all three hold:**
  - the buckets rise with at most one adjacent inversion;
  - the top-minus-bottom difference has a 95% player-bootstrap interval above
    0;
  - it survives Holm across the 8 categories (two-sided p from the bootstrap
    z, alpha 0.05), for graded and ungraded separately.
- **For information only (graded):** the score's Spearman with each category's
  actual contribution vs FV alone's. It shows whether the category score adds
  to FV for that category.
- **Each category is labelled for the user:**
  - "trustworthy" (Part 2 trustworthy AND its ladder passes);
  - "level only" (the ladder passes but Part 2 does not, so the score is mostly
    playing time);
  - "not predictable".

## What is already seen (declared)

- Category rates and category contributions have never been examined in this
  project.
- Total value at 4 years (the 3c rating target) and FV vs stats for it HAVE
  been; Part 1 is close to that.
- All classes with answers have been seen in some form. Results are
  provisional until the 2025 class's 4-year window completes (after the 2029
  season).

## Result (run 2026-10-09 on Opus; `category_run.py`, report `cache/category_report.txt`)

**Plumbing checks:**
- The graded test counts equal the FV+ class counts (hitters 331+312, pitchers
  317+345).
- Every ladder bucket is the same size.
- Production covers 1,431 hitters and 1,717 pitchers, matching the ratings
  CSVs.
- Spot-checks:
  - the top HR scores are power bats (Montes, Fischer, S. Jones);
  - the top OBP scores are on-base types (Arias, Jenkins, Clark, Lara);
  - per-PA HR and OBP scores are uncorrelated among the top-150
    playing-time hitters (0.02), so the scores separate profiles.

**Part 2 (MLB rates when he plays): all 8 categories trustworthy** (CI above 0
at 3 of 3 vantages).
- HR rate is strongest (rho 0.55-0.58), then K (0.43-0.49), SLG (0.32-0.43),
  R (0.27-0.37), HR/9 (0.32-0.37), OBP (0.27-0.31), ERA (0.29-0.33) and WHIP
  (0.22-0.27).
- The model beats the raw minor-league stat in most cases, and by far for the
  ratios (raw ERA rho about 0).

**Part 1 (4-year playing time):** FV + stats beat FV alone for hitters (pooled
z +2.93) and pitchers (z +3.05). FV + stats is used.
- This is notable next to FV+ rating, where stats did not help on total value:
  they DO help on playing time.

**Walk-up ladders:**
- **Graded hitters: all 4 categories PASS with zero inversions.** The score
  ranks each category better than FV alone:

  | | score rho | FV rho |
  |---|---|---|
  | HR | 0.40 | 0.11 |
  | R | 0.20 | 0.15 |
  | OBP | 0.11 | 0.03 |
  | SLG | 0.16 | 0.11 |

- **Graded pitchers:** K passes (score rho 0.27 vs FV rho −0.14). **ERA, WHIP
  and HR/9 fail** (2 inversions each).
- **Ungraded:** HR, R, OBP, K and WHIP pass; SLG, ERA and HR/9 fail.
  - The ungraded SLG failure is two tiny inversions among buckets that are
    mostly non-arrivals (means within ±0.01 of 0). The top bucket is clearly
    positive (z +4.8), but the pre-registered rule stands.

**Labels:**

| category | graded | ungraded |
|---|---|---|
| HR | trustworthy | trustworthy |
| R | trustworthy | trustworthy |
| OBP | trustworthy | trustworthy |
| SLG | trustworthy | not predictable |
| K | trustworthy | trustworthy |
| ERA | not predictable | not predictable |
| WHIP | not predictable | trustworthy |
| HR/9 | not predictable | not predictable |

**Reading (Opus):**
- For hitters, the category scores do what FV cannot: they say which roto
  categories a prospect will feed. HR especially (0.40 vs FV's 0.11).
- For pitchers, prospects mostly HURT the ratio categories over their first 4
  seasons:
  - Nearly every bucket's mean ratio contribution is negative.
  - FV correlates NEGATIVELY with ERA and HR/9 contribution, because
    higher-FV arms pitch more innings at below-replacement ratios.
  - Ratio rates are somewhat predictable, but "who hurts you least" is not a
    stable ranking.
  - **Strikeouts are the category where pitching prospects reliably help.**

## Deliverables

- **`cache/category_scores.csv`:** for 2026 players (graded via the site board,
  and ungraded), each of the 4 category scores, expected PA/IP, the Part 1 path
  used, and each category's label.
- **`cache/category_report.txt`:** Part 2 trust results, the Part 1 race, the
  ladders, the FV comparison and the labels.
- **No page change in this project.** Display and team-needs matching are later
  designs.

## Execution

- Built and run on Opus, inline, from a written plan.
- Long steps checkpoint per phase (per-phase JSON, skip completed phases,
  `--force`).
- No network: MLB season stats, replacement inputs, labels, boards and
  standings are all cached.
