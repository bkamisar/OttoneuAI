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

**Targets — REVISED after plan B (see "Plan B result"): rank-based, so they
mean the same thing in every season.** Each MLB hitter-season is ranked within
its year by total SGP (1 = best).
- **Soon** = a **top-144** season in Y+1…Y+2. Exactly 144 hitters qualify every
  year, the literal 12 teams × 12 slots.
- **Rating** = the best season in Y+1…Y+4 with ≥100 PA, valued at the **typical
  value of its rank**: the median SGP at that rank across seasons 2013…V (2020
  excluded), computed as-of. It is floored at 0 and is 0 if there's no such
  season. That keeps SGP units and star-vs-starter magnitude without a narrow
  year like 2026 shrinking everyone. "Useful" for top-N = the typical value of
  rank 144.
- **The 2024 decisions stay frozen:** contact+approach kept, tracking-for-soon
  not used. They were made once, under the first labels. The rerun reports new
  2024 numbers for information only.

*Original definitions (superseded, kept for the record):* both targets used total
season SGP from `labels.csv`, because an 80-PA call-up doesn't help a fantasy
roster:
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
- **ID join SETTLED (2026-09-28, from the 2026 export):** the CSV carries only
  FanGraphs' own `playerId` (`sa…` minor-league ids and numeric ids), with **no
  MLBAM id**. Plan C matches on name + age + org, and lists every non-clean match
  for the user to confirm. Exports come as **two files per year**, saved as
  `cache/fv/board_<year>_hitters.csv` and `board_<year>_pitchers.csv`. The CSV
  keeps every column separate; a web-page copy runs them together, making ranks
  ambiguous, so it is not usable. 2026 is on file (not needed for the test).
- **The Board's `Age` column is computed as of a date that varies by list**
  (corrected — the first note said "export time", which the user disproved with
  Eury Pérez at 20.29 on the 2023 list, i.e. his age around late July 2023). The
  median gap for the same player: 2023→2024 +0.99 yr, 2024→2025 +0.69, 2025→2026
  +0.00. So the 2023/2024 lists carry mid-season ages of their own year, and the
  2025 and 2026 lists share one date (around spring 2025). **Never use it as
  as-of age.** The model's age comes from StatsAPI; name matching allows ±1 year
  of slack. Each file's year is verified by its top prospects (2023: Elly De La
  Cruz / Eury Pérez; 2024: Jackson Holliday / Paul Skenes; 2025: Roman Anthony /
  Roki Sasaki).
- **The "normal" Board lists ARE preseason lists; graduates are deleted from
  them afterward** (verified 2026-09-28, correcting a same-day misread that called
  them in-season snapshots). No list contains its own summer's draftees (Skenes and
  Crews absent from 2023, Bazzana from 2024, Willits from 2025), and every list has
  the previous summer's picks, so the grades predate that year's draft. Players who
  graduated during the list's season are gone (Witt/Julio from 2022,
  Carroll/Henderson from 2023, Chourio from 2024). **Use the normal boards, never
  the "updated" (mid-season) ones**, which would know part of the season. So:
  - **No leak:** list Y+1 is a true as-of consensus for cohort Y.
  - **Survivorship remains:** the fastest graduates are missing from list Y+1.
    Plan C reports the head-to-head both on the players list Y+1 grades and with
    missing early graduates restored from their latest earlier list (list Y,
    one year stale, flagged).
  - Lists needed: 2020, 2022–2025 (**on file: 2020–2026**, each verified
    preseason by the draftee test). 2019 and earlier help learn the model + FV
    blend. 2021 supplies list-Y grades for early graduates (e.g. Witt: FV 60, #17
    on 2021).
  - **Deletions aren't perfectly consistent:** Andrew Vaughn is absent from both
    2020 and 2021, though he graduated in 2021. Plan C reports, per cohort, how many
    players have no grade on any list.
  - **2018 is on file but THIN**: 285 hitters and 241 pitchers (vs 430–600 per
    type from 2019 on), with only 66 Top-100 players left after graduate
    deletions. Royce Lewis is missing entirely. It also codes unranked as `0`
    rather than blank. Use it for blend-learning only, flagged. **2017** (the Board's first list) is
    similar: 321 hitters (53 ranked) and 306 pitchers (39 ranked), verified
    preseason. Same flag. **Collection complete: 2017–2026.**
  - **Use only these columns:** name/org/pos (for matching) and FV / Top 100 / Org
    Rk (the consensus being tested). The Board's stat columns are ignored: they
    aren't as-of, and the user notes the Board can't show stats before 2020. All
    model stats come from StatsAPI.
- *(Original plan:)* **Export one year first (2023)** to settle the ID join. Check whether the
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

## Plan B result (run 2026-09-27, reviewed on Opus)

**Tree leads rejected as explicit terms, for both outputs.** Age × SLG actively
hurt the rating (z −2.6 / −1.6 / −2.9). Swinging-strike × SLG did nothing
anywhere. **The whiff × power question is settled: no interaction beyond the
additive effects improves prediction.**

**Pulled air: FAIL** (see "Pulled-air parity RESULT" above).

**Sealed 2024, opened once (rules fixed in advance):**
- Contact + approach **kept** for "soon" (2024 AUC gain z +1.6).
- Final "soon" on 2024: **AUC 0.870**. Within-cohort ranking held up.
- **Calibration and top-N collapsed:** the top bucket predicted 27% vs 12%
  actual, and top-50 fell to 0.16 (0.34–0.50 in the decision years). Cause below.
- **Tracking for "soon": not used.** Trained on 82 AAA-2022 hitters, w +2.73
  [+0.90, +4.43]; on 344 AAA-2024 hitters it added nothing (AUC 0.843 → 0.842).
  The pre-set rule rejected it. Read this as **untested, not refuted**: the 2024
  test had few positives (see below), so it had little power. The production fit
  on 822 AAA hitter-seasons gives w +1.24 [+0.65, +1.79]. **First thing to
  revisit when the 2025 cohort's "soon" answers arrive (after the 2027 season).**

**Step-1 gate, as-of: PASS**, Spearman +0.416 [+0.280, +0.538] among 171
arrivals (the first run, which leaked slightly, gave +0.391).

**Production (as of 2026):**
- Rating: ridge, tracking applied (**provisional**), w +0.167 [+0.099, +0.246].
- "Soon": logistic, no tracking.
- `cache/hitter_ratings.csv` holds 1,431 hitters. The top 15 are all AA/AAA,
  ages 19–25.

**Review finding: the SGP scale swings between seasons, and the targets inherit
it.** The 144th-best hitter season, about the starter-quality line, is worth 0.93
SGP in 2013, 0.16 in 2014, 0.76 in 2024, 0.45 in 2025 and 0.23 in 2026. 2026 is a
complete season (135 hitters with 500+ PA), so this is a real low-spread year,
like 2014. Against a fixed bar, only 82 hitters were "starter-quality" in 2026
instead of about 144. The 2024 cohort's answers come from 2025–26, which is why
its calibration and top-N collapsed.
- **What survives:** ranking *within* a cohort. Everyone in a cohort faces the
  same future seasons, so AUC and Spearman are fair. The model's *order* is
  trustworthy.
- **What doesn't:** absolute levels. "P(useful within 2)" is calibrated to an
  average-spread future, so it should be read as a relative tier, not a literal
  percentage. Training also mixes eras with different spreads, which adds noise.
- **The proper fix:** make "starter-quality" rank-based per season (the top 144
  hitters of *that* season, the league-grounded meaning of 12 teams × 12 slots).
  Put the rating on a spread-normalized scale, converted back to SGP at the
  current spread for display. Both are label changes. **No untouched cohort is
  left for a clean final check after such a change**, so the honest checks become
  plan C (the consensus gate) and future cohorts as their answers arrive.

## Rank-target rerun result (run 2026-09-28, reviewed on Opus)

Both targets are now rank-based (Part 1, "Targets — REVISED"). Plan A's decisions
were re-run on the decision vantages; plan B's final run kept 2024's first-opening
decisions frozen.

- **The fix worked.** 2024 "soon" calibration: top bucket 0.27 predicted vs 0.22
  actual (0.27 vs 0.12 before), top-50 0.26 (0.16 before), AUC 0.873. Pooled over
  the decision vantages, the top bucket is 0.28 vs 0.26. The remaining 2024 gap is
  about 1.5 SE for a 153-player bucket.
- **The starter line is unchanged** (0.513 / 0.555 / 0.597 at 2019 / 2021 / 2022):
  the median-by-rank at 144 is the same quantity as the old bar. What changed is
  that each year's labels use rank.
- **Same groups adopted.**
  - Rating: age/level (z +7.5 / +4.2 / +6.2), power (+4.0 / +4.6 / +3.7),
    contact (+2.8 / +3.1 / +1.5), and speed, **marginally** (+1.0 / +0.9 / +1.6;
    rank gain +0.002–0.003).
  - Soon: age/level, power, and contact + approach as a pair (+1.5 / −0.3 / +1.8;
    kept regardless under the 2024 freeze).
- **Leads rejected again.** Age × SLG hurts the rating (z −2.7 / −1.5 / −2.5);
  swinging-strike × SLG does nothing.
- **Tracking for "soon": still off.** The production fit gives w +1.75
  [+1.17, +2.25] on 822 AAA hitter-seasons, but the held-out 2024 test shows no
  gain (AUC 0.833 → 0.823, z −0.4). That split between in-sample and held-out is
  itself the finding: untested with enough data, not refuted. Revisit when the
  2025 cohort's answers arrive.
- **Production:** rating tracking applied, provisional (w +0.185
  [+0.104, +0.275]). 1,431 hitters in `cache/hitter_ratings.csv`; the top 15 are
  AA/AAA, ages 19–25.
- **Known coverage gap:** a hitter needs ≥150 PA at a level in 2026 to be rated,
  so injured prospects are missing from this list.
- **Next: plan C, the consensus gate.** Board lists 2017–2026 are on file; the
  design is below (`plans/2026-09-27-3c-consensus-gate.md`).

## Plan C design: the consensus gate, detailed (approved 2026-09-28)

**Matching** runs from our side. Each prospect in a class is looked up on list
Y+1 by normalized name (accents folded, punctuation and Jr./II suffixes dropped),
guarded by age. Each list's Board-age date differs, so the offset between Board
age and StatsAPI season age is calibrated per list from the unique matches, and a
candidate within 1.5 years of it is accepted. Names shared by several players on
either side are **ambiguous**: listed in `consensus_ambiguous.csv`, never guessed.
Measured on list 2023 × class 2022: 396 of 544 Board hitters matched uniquely,
395 of them age-consistent; 6 names were shared. The unmatched were mostly
players not in the four full-season levels that year, so they are outside the
class anyway.

**Groups per class:**
1. **Head-to-head (decides):** the prospects that list Y+1 grades.
2. **Sleepers:** prospects in our class that FanGraphs didn't grade.
3. **Early graduates restored (guard):** head-to-head again, adding players who
   are missing from list Y+1 but had ≥100 MLB PA in year Y+1 (so they were deleted
   as graduates), using their list-Y grade.

Counts of graded, ungraded, ambiguous, age-rejected and restored players are
reported per class.

**Rankers:**
- **FanGraphs' order:** FV ("45+" = 47.5), then Top 100 rank, then org rank.
- **The model:** plan A's recipe as-of the vantage (rank targets, adopted groups,
  ridge/logit). Base only: the rating's tracking weight can't be tested as-of,
  and tracking is off for "soon".
- **Blend (decides):** the average of the two percentile ranks, with no fitting.
- **Fitted blend (information only):** trained on earlier classes that have a
  list (lists 2017+), each scored by its own as-of model (the walk-forward
  prediction at that class's year). Unavailable at rating 2019.

**Test classes:** rating 2019 / 2021 / 2022 (lists 2020 / 2022 / 2023); soon 2021 /
2022 / 2023 (lists 2022 / 2023 / 2024). Soon 2024 (list 2025) is information only,
since that cohort was already opened. One row per player (the highest level
played that season). Matches whose name has no candidate within the age guard are
**age-rejected** and left out of every group.

**Scoring:** rank accuracy (Spearman / AUC), top-25 / top-50, and a paired
player-bootstrap gain over FanGraphs.

**Verdict, per output, fixed in advance:**
- **"Model leads"** if the model beats FanGraphs by plan A's adoption rule (≥1 SE
  at 2 of 3 classes, none ≤ −2 SE, mean top-50 change ≥ −0.04).
- **Otherwise "model as tiebreaker"** if the blend beats FanGraphs by the same
  rule.
- **Otherwise "follow FV".**
- The **model is shown for ungraded players** if its sleeper rank-accuracy 95%
  interval (player bootstrap) is above chance (Spearman > 0, AUC > 0.5) at ≥2 of 3
  classes.
- **Guard:** if the restored-graduates run gives a different verdict, it's flagged
  **unstable** and the more cautious of the two stands.

**Outputs (gitignored):** `consensus_report.txt`, `consensus_verdict.json` (read by
sub-project 4), `consensus_ambiguous.csv`.

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
