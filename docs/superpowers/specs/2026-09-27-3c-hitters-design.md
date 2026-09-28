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
| Trajectory | repeating the level; played ≥2 levels this season; PA at the level |

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

**Adoption (2-of-3), revised after the plan A review.** Rank accuracy is Spearman
for the rating and AUC for the yes/no "soon". A vantage counts as a **win only if
the rank gain is ≥1 standard error**, measured by a paired bootstrap over the test
players. A group is adopted if it wins at ≥2 of 3 vantages, **no vantage is ≥2 SE
worse**, and the average top-50 change is no worse than −0.04 (about 2 players).
A group with no real effect passes by chance about 7% of the time.
*Why revised:* the first version counted any positive change as a win (+0.001
kept "approach" on noise) and let 50/100-player top-N swings veto real gains (it
dropped "contact" despite z +2.7/+3.1/+1.7). The flaw was visible in the rule's
own mechanics. 2024 stayed sealed, so the final check is untouched by the change. Group importance uses drop-the-group-and-refit.
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

**Pulled-air parity RESULT (run 2026-09-27, n=1,602 MLB hitter-seasons 2023–26):
FAIL, and the first reading of it was wrong.** The raw product pull% × FB% hit
r 0.9823, apparently clearing the 0.98 bar. It doesn't: fly-ball rate varies more
between hitters than pull rate and we measure it almost exactly (r 0.9997), so it
dominates the product. Replacing our pull% with a **constant** still gives
r 0.8823, so most of that 0.98 was borrowed from fly balls, not earned on the
pulled part. FB% is already a model feature, so the only thing the term adds is the
pulled part — and with FB regressed out of both sides that is **r 0.919**,
matching pull% alone (0.925) and failing the bar. `pulled_air_parity.py` now makes
the residualized figure the verdict. **Pulled air stays a documented hypothesis,
not measurable in AAA.** General lesson: never judge a product term by the product's
own correlation when one factor is measured far better than the other.

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

## Plans

- **Plan A** (`plans/2026-09-27-3c-hitters-base.md`): the data extension, labels
  from 2013, as-of targets, the walk-forward harness, and the base-model backtests
  for both outputs.
- **Plan B** (`plans/2026-09-27-3c-hitters-final.md`): the as-of tracking layer,
  the pulled-air parity check, the sealed 2024 check, and `hitter_ratings.csv`.
- **Plan C: the consensus gate** (below). It runs after plan B and **must pass
  before the shopping list trusts the model.**

## Consensus gate: does the model beat just following FV? (user, 2026-09-27)

The NFLU test. If blindly following FanGraphs' rankings predicts outcomes as well
as the model does, the shopping list's "edge" column is noise.

**Test.** For each past cohort, rank the same FV-graded prospects three ways,
scored on the same targets, vantages and metrics as the backtests (rank accuracy
+ top-50/top-100 hit rate):
1. **FV alone.** Ties broken by overall rank, then org rank.
2. **Model alone** (plan B's production recipe, refit as-of each vantage).
3. **Model + FV.** Does the model add to consensus?

**As-of FV.** Cohort Y uses the Board list published for season Y+1 (preseason
Y+1, built from information through season Y).
- Rating vantages 2019/2021/2022 → lists 2020, 2022, 2023.
- "Soon" vantages 2021–2024 → lists 2022–2025.
- Five lists in all: **2020, 2022, 2023, 2024, 2025.**

**Reading the result:**
- **Model beats FV:** the shopping list leads with the model.
- **FV wins, but model + FV beats FV:** the model is a tiebreaker, used where it
  disagrees.
- **FV wins outright:** follow FV, and use the model only for hitters FanGraphs
  doesn't grade.

**Data.** Manual FanGraphs Board CSV exports by the user. Automated access returns
a Cloudflare 403, which is not to be bypassed. Saved under
`prospects-model/cache/fv/board_<year>.csv` (gitignored: third-party data, never
committed).
- **Export one year first (2023)** to settle the ID join. Check whether the
  export has an MLBAM id column (see "The FanGraphs ↔ StatsAPI id gap" in the
  parent spec). If it does, the join is exact. If not, the fallback is a name +
  birth-year + org match, with every ambiguous match listed for review, never
  guessed (the Witt → Witte lesson).
- Only then export the other four years.

## Plan A result (run 2026-09-27, reviewed on Opus)

**Data:** swing data exists from 2012 (`WHIFF_FIRST = 2012`), so the whiff features
are judged at all three rating vantages. Labels run 2013–2026, with 2026 refreshed
after the season's last games; the new replacement level moved top 2026 values by
about 0.2–0.3 SGP. 21,574 hitter-season-levels, 7,108 players, about 1,500 per
season.

**Rating** (best season in the next 4): **ridge** beat trees at all 3 vantages.
Kept (z = rank gain in noise-widths, 2019 / 2021 / 2022):
- **age/level**: +7.5 / +4.4 / +6.1
- **power**: +4.2 / +4.6 / +3.8
- **contact**: +2.7 / +3.1 / +1.7
- **speed**: +1.3 / +1.2 / +1.7 — small but consistent: speed pays a little
  through runs, even with no SB category.

Dropped: approach and trajectory (noise). Final model: Spearman 0.431 / 0.432 /
0.446, top-50 hit rate 0.54 / 0.52 / 0.54.

**Soon** (starter-quality season within 2): **logistic** beat trees at all 3
vantages. Kept: **age/level** (z +2.7 / +5.6 / +5.5) and **power**
(+4.0 / +4.5 / +2.1). **Contact + approach was adopted only as a pair, and
marginally** (+1.1 / −0.5 / +1.9, pooled z ≈ 1.4). It is one of 10 pair tests, so
it may be chance. **The sealed 2024 check (plan B) must test "soon" with vs
without it**; that out-of-sample verdict decides whether it stays. Final model:
AUC 0.884 / 0.921 / 0.935. The AUC is flattered by easy "no" cases (young
Single-A hitters); the top-50 hit rate, 0.38 / 0.50 / 0.34, is the honest
number. Calibration is good, with the top bucket slightly under (0.25 predicted
vs 0.28 actual).

**Contact vs the whiff test: consistent.** Whiff on top of K% adds a sliver here
too (rating z +0.4 / +2.4 / +0.8), matching 3a's "real but small". What clearly
matters is the contact group as a whole, and only for how good, not how soon.

**Tree patterns are leads, not findings.** Trees lost to the linear models at
every vantage for both outputs. Replicated in the trees' top 10 at all 3
vantages: **age × SLG** (both outputs, the strongest), age × level, age × HR/PA,
and **swinging-strike rate × SLG** (rating). The last is the whiff × power
question in another form. Plan B tests the top leads as explicit terms under the
same rule.

**Review corrections to the first run (recorded so they aren't repeated):**
- The original adoption rule counted +0.001 as a win and let top-N swings of 1–2
  players veto real gains; it kept approach and trajectory on noise and dropped
  contact (see the revised rule in Part 2).
- The first write-up called tree interactions "findings".

## Revisit trigger: Statcast into the base model

Tracking stays a layer until a fair as-of backtest can judge it as a base
feature: three test years whose training sets already contain at least two
tracked AAA cohorts (full-AAA tracking began in 2023). For "soon" (2-year answers)
that means vantages 2026–28, answerable around **2030**. For the rating (4-year
answers), vantages 2028–30, answerable in the **early 2030s**. Until then, the
layer's trust weight is re-estimated each year as cohorts mature. Tracking exists
only in AAA (below AAA, only a partial FSL sample), so the layer may remain the
right structure for AA and below even after that.

## Out of scope

Pitchers (their own tracking step first, then their full model); FanGraphs FV
grades (later add-on, one-year ID-join test first); dollars and
`prospects.html` (sub-project 4); other "soon" definitions.
