# 3c-hitters: Full Hitter Prospect Model — Design

**Date:** 2026-09-27
**Status:** Approved in brainstorming
**Parent spec:** `2026-09-26-prospect-model-design.md` (sub-project 3, "Model and backtest").
**Builds on:** the whiff test (3a) and step 1 (`2026-09-27-step1-tracking-score-design.md`).

## What this is

The prospect rating for **minor-league hitters**. Two outputs per hitter:
1. **Rating:** expected best season value over the **next 4 seasons**.
2. **Soon:** the chance of a **starter-quality MLB season within 2 seasons**.

The user's goal is players who produce well *and soon*. That is why there are
two numbers and why the horizon is 4 years, not a career. Pitchers come later:
the whiff test found their box scores carry little signal, so they need their own
tracking step first. FanGraphs FV grades are a later add-on test.

## The governing rule: as-of

**Every backtest trains only on what was known at the vantage year V**, as NFLU
does. "As-of V" covers:
- **Labels:** a cohort is used for training only if its answer was complete by V.
- **The "useful" bar:** computed from MLB seasons ≤ V.
- **Normalization:** within level-season, so it is inherently as-of.
- **The step-1 MLB model:** refit on MLB rows with outcome season ≤ V.
- **The AAA→MLB offsets:** from same-season pairs in seasons ≤ V.
- **Player isolation:** any player in the test cohort is removed from that round's
  training, because a player's rows share one outcome.

Step 1's gate had a mild version of this leak (its MLB model saw seasons through
2025). 3c refits step 1 as-of each vantage, so **the step-1 gate is re-run
honestly here**.

## Part 1: data and targets

**Rows:** one per minor-league hitter × season × level. Levels are AAA, AA,
High-A and Single-A, identified by sportId and never by league name (leagues
changed levels in 2021). Seasons are **2012–2019 and 2021–2025** for learning,
plus **2026 for scoring only**. There was no 2020 minor-league season, so a 2021
player's previous season is 2019. Each row needs ≥150 PA at that level. Excluded:
the Mexican League, and players already established in MLB (≥300 MLB PA before
the season).

**Features**, normalized within level-season. They are grouped so that
near-duplicates share a group; otherwise each would hide the other when dropped
(r(whiff, K%) = 0.90 in the whiff test):

| Group | Features |
|---|---|
| Age/level | age relative to level-season average, level |
| Contact | K%, whiff rate, swinging-strike rate |
| Approach | BB%, OBP, swing rate |
| Power | ISO, HR/PA, SLG |
| Speed | SB/PA (no SB category exists; whether speed pays through runs is a finding) |
| Trajectory | repeating the level; played ≥2 levels this season |

**Targets.** Both use total season SGP from `labels.csv`, because an 80-PA
call-up doesn't help a fantasy roster:
- **Rating** = best season value in seasons Y+1…Y+4 with ≥100 PA, floored at 0,
  and 0 if no such season. Known once Y+4 ≤ V.
- **Soon** = 1 if any season in Y+1…Y+2 reaches the useful bar, else 0. Known
  once Y+2 ≤ V.

**Swing data before 2016:** the first plan task checks whether StatsAPI
`seasonAdvanced` has minor-league swing and whiff counts for 2012–2015. If it
doesn't, the whiff features exist only from 2016. The contact group is then
judged only at vantages whose training includes 2016+ cohorts, and the report
says so.

## Part 2: model and backtest

**Candidates:**
- **Rating:** ridge vs gradient-boosted trees.
- **Soon:** logistic regression vs gradient-boosted trees.

The simpler model wins unless the other wins at least 2 of the 3 vantages.
ElasticNet and random forests are dropped: they are near-duplicates, and ridge
won both earlier tests.

**Walk-forward vantages (test cohort Y = vantage V):**
- **Rating:** Y ∈ {2019, 2021, 2022}, trained on cohorts ≤ Y−4 (2012–2015,
  2012–2017, 2012–2018). If swing data is missing before 2016, the whiff features
  are testable only at 2021 and 2022.
- **Soon:** decisions on Y ∈ {2021, 2022, 2023}, trained on cohorts ≤ Y−2.
  **2024 is sealed**, trained on cohorts ≤ 2022, and opened once at the very end
  as the honest final check.

**Adoption (2-of-3):** a group, model choice or combination is adopted only if it
wins at ≥2 of the 3 vantages on **Spearman rank accuracy without lowering
top-50 or top-100 precision**. Group importance uses drop-the-group-and-refit.
If two groups each fail alone, they are tested jointly. **Top-25** is reported
but never decides anything: about 25 players per cohort is too noisy.

**Also reported:**
- **Calibration for "soon":** in each predicted-probability decile, the
  predicted rate vs the actual rate on test cohorts. It will be shown as a
  percentage, so it has to mean one.
- **Interaction search:** tree pairwise strength (unnormalized Friedman's H,
  `psmodel/interactions.py`). A pair is a *finding* if top-10 at ≥2 of 3
  vantages; otherwise a *hypothesis*. Includes the rematch of the whiff × power
  question.
- **The phantom-feature guard** (`evaluate.guard_features`) on every fit.

## Part 3: tracking layer and outputs

**Tracking adjustment:** applies to AAA hitters with ≥100 batted balls (2022+).
The step-1 tracking score is rebuilt as-of V. The adjustment is the part of the
score that the base prediction doesn't already explain, times a **trust weight**
estimated separately per output:
- **Soon:** fit on AAA cohorts whose 2-season answers were known at the
  vantage. The sealed check fits on 2022 and tests on 2024. The production fit
  uses 2022–24 (~1,000 hitters).
- **Rating:** only 2022 has all four seasons played. The production fit uses 2022
  plus 2023–24, each weighted by the share of its window observed (3/4 and 2/4).
  There is no later complete cohort to check against, so it is labeled
  **provisional**. If its bootstrap interval includes 0, the rating uses no
  tracking.

**Pulled air balls (the user's hypothesis, top-50 signal in step 1):** check
whether our coordinate-based pull% × FB% matches Savant's pull% × FB% on the
**2023–26 MLB game records already on disk**, with plan A's bar of r ≥ 0.98.
Pass → one test of adding it to the tracking layer, judged on top-50 precision
for "soon". Fail → it stays a documented hypothesis. Expect a fail: plan A
capped coordinate-based pull at r ≈ 0.96. The check is cheap, so it runs.

**Outputs (gitignored `cache/`):**
- `hitter_ratings.csv`: every 2026 minor-league hitter not already established,
  with name, player_id, level, age, **rating** (SGP and percentile), **P(useful
  within 2 seasons)**, whether tracking was used, and provisional flags. A player
  at two levels gets one row, from the higher level.
- `model3c_report.txt`: both backtests (including the sealed 2024 check), group
  importance, interaction findings vs hypotheses, calibration, both trust
  weights with intervals, the as-of step-1 gate, and the pulled-air verdict.

No dollars and no UI: those belong to sub-project 4 (`prospects.html`).

## Data, network, security

Each answers the download rule (`feedback_downloads`): what it's for, why now,
smallest source.
- **Minor-league season totals + `seasonAdvanced`**, 4 levels: 2012–2015 (new
  history), High-A/Single-A 2016–2026, AA/AAA 2021–2026 (AA/AAA 2016–19 cached
  from the whiff test). Season-level endpoints are the smallest source; about
  300 requests to `statsapi.mlb.com`, a few minutes.
- **MLB season stats 2005–2014:** 2013–14 labels (outcomes for the 2012 cohort)
  and MLB PA history for the established-player exclusion. Today's labels start
  in 2015, so the whiff test's 2016 cohort could not see MLB PA from before 2015.
  This fixes that too. About 20 requests. **`build_labels.py` must still pass the
  `parity/compare.py` gate** after extending its first season.
- **Refresh 2026 MLB labels after the season is final.** The cached 2026 season
  stats predate the last games, and `http.fetch_text` never refetches a cached
  URL, so the plan must bypass or replace that cache entry deliberately.
- **Already on disk:** `labels.csv` (2015–2026), the step-1 tables, and MLB game
  records 2023–26.
- **Security audit before every network step.** Stdlib + installed packages
  only; hosts `statsapi.mlb.com` and `baseballsavant.mlb.com`; cache untracked;
  no credentials. No bulk downloads.

## Out of scope

Pitchers (their own tracking step first, then their full model); FanGraphs FV
grades (later add-on, one-year ID-join test first); dollars and
`prospects.html` (sub-project 4); other "soon" definitions.
