# Pitcher Prospects — Design (DRAFT: decisions pending)

**Status:** drafted overnight 2026-09-28 on Opus. **Approved by the user
2026-09-28:** the recommended defaults, with D2 changed to a 30 IP floor (see D2).
Plan P-A (`plans/2026-09-28-pitchers-base.md`) is cleared to build.

## What this is

The hitter pipeline, built again for pitchers, reusing everything that
generalizes:
- as-of walk-forward training with a sealed year;
- rank-based targets;
- group adoption under the same pre-registered rule;
- the consensus gate against FanGraphs;
- the shopping list.

What's new is the **stuff layer**. Every AAA pitch since 2022 carries velocity,
spin and movement, which is the pitcher counterpart of hitters' exit velocity.
The 3a whiff test found that box-score swing rates added nothing for pitchers
beyond K%, BB%, ERA and WHIP, and flagged tracking as where the headroom is.

## Data on hand (verified 2026-09-28, nothing else downloaded)

- **Minor-league pitcher season totals, 2012–2026, all four full-season levels.**
  Pulled overnight (`pull_pitcher_data.py`; same host and endpoints as hitters,
  security audit clean). About 350–400 pitchers with 40+ IP per level-season;
  swing data (whiffs, swings, pitches, strikes) on about 100%.
- **MLB pitching 2005–2026:** one row per player-season, used for the
  established-pitcher cut.
- **MLB pitcher labels 2013–2026:** 680–910 pitcher-seasons per year. The same 4×4
  SGP as the site (K, HR/9, ERA, WHIP), and `parity/compare.py` passes for
  pitchers too.
- **Pitch tracking in game records already on disk:** AAA 2022 (PCL) and 2023–26,
  and MLB 2022–26. A 25-game sample per level-season found velocity, spin,
  induced vertical break and extension on 96–100% of pitches, with pitch type
  labelled.
- **FanGraphs board pitcher exports 2017–2026** (in `cache/fv/`), for the consensus
  gate.
- **Below AAA,** only the Florida State League has tracking (the probe), and it
  isn't downloaded.

## Decisions for the user (recommended default first)

**D1. What counts as a good pitcher outcome?**
- *Recommended:* mirror the hitters with rank-based targets.
  - **Soon** = a top-**120** pitcher season within 2 years.
  - **Rating** = the best pitcher season in the next 4 (≥ 25 IP), valued on an
    as-of median rank → SGP curve.
- 120 = 12 teams × about 10 arms under the 1,500 IP cap (already `USEFUL_N["P"]`
  in `dataset.py`).
- *Alternative:* a separate reliever line. More complex, and a top-120 season
  already includes elite relievers who help ERA and WHIP. 3a found 61% of useful
  pitcher seasons came in under 90 IP.

**D2. Who counts as a prospect? DECIDED: 30 IP at a level** (the user asked
about relievers, 2026-09-28). A pitcher-season qualifies with **30+ IP at a
full-season level** and fewer than **100 prior MLB IP**.
- The draft's 40 IP was measured on coverage only, with no outcomes looked at.
  Relievers promoted mid-season split their innings across levels, and at 40 IP
  per level, 2,753 pitcher-seasons with 40+ total IP had no qualifying row. 90% of
  those (2,479) were relievers, about 21% of all reliever seasons, and skewed
  toward the promoted (good) ones.
- At 30 IP, 784 are lost (725 relievers, about 6%). At 25 IP, 208 are lost.
- Pure relievers reach 40 IP at one level only 50% of the time, and 30 IP 74% of
  the time.
- 30 IP is about 130 batters faced, close to the hitters' 150 PA. The model's IP
  feature discounts the smaller samples.
- The floor was chosen before any backtest, so it is not tuned to results.

**K−BB% was left out on purpose** (the user asked). In a linear model it is exactly
K% − BB%, so with both present it adds nothing: the model learns the weights, and
equal-and-opposite weights *are* K−BB. It could only help the tree challenger, and
it would blur the group tests by making two features nearly identical.

**D3. One model, or separate starters and relievers?**
- *Recommended:* **one model with role features** (share of games started, IP per
  game).
- Minor-league roles are unstable: many starting-pitcher prospects end up in the
  bullpen, and that uncertainty is exactly what the model should price. Splitting
  would halve the data and force a role guess.

**D4. Feature groups to test**, each kept or dropped by the hitters' rule:

| Group | Features |
|---|---|
| age/level | age, level flags |
| strikeouts | K%, whiff rate, swinging-strike rate, CSW |
| control | BB% |
| run prevention | ERA, WHIP, HR/9 |
| role | GS share, IP per game, IP |
| trajectory | repeat level, multi-level |

K−BB% is left out because it's exactly K% − BB%. BABIP is left out because the
source has no hits-allowed field.

**D5. The stuff layer (the big one): build it, and in what order?**
- *Recommended order:*
  1. **P-A:** the base model (box stats), with backtests.
  2. **P-B:** a pitch-tracking parity check. Our parser's per-pitcher velocity,
     spin and movement must match Baseball Savant's published MLB numbers before
     any AAA number is trusted, exactly as 3b did for hitters.
  3. **P-C:** a stuff score. Learn which pitch characteristics predict MLB value,
     then translate AAA stuff onto that scale.
- Then the as-of test decides whether the stuff score earns a place, as the
  tracking layer did for hitters.
- *Sub-decision (D5b):* where the stuff score learns from.
  - Our own MLB game records cover only 2022–26.
  - Savant covers MLB pitch data back to 2015: small, first-party, one CSV per
    season per leaderboard.
  - *Recommended:* use Savant for 2015–21, plus our records. This needs a small
    download, sized and security-audited first.
  - **Checked overnight (one cached request):** Savant's custom leaderboard for
    `type=pitcher`, 2019, returned 804 pitchers with every field asked for:
    four-seam velocity, spin, horizontal break, vertical and induced vertical
    break, extension, fastball / breaking / offspeed averages, slider metrics, pitch
    mix, whiff%, K% and IP. The `year` column matched the request.
  - So 2015–2021 costs about 7 requests (one CSV per season), from the same host
    the hitter pipeline already uses.

**D6. Consensus gate and shopping list.**
- *Recommended:* plan C's rules unchanged, against the board pitcher lists: FV
  alone vs the model vs their average, pre-registered, with the same verdict
  ladder.
- The Prospects page's pitchers then get the same lenses, odds and Take column as
  hitters.

## P-A result (run 2026-09-28 on Sonnet, reviewed on Opus)

`model_p_base.py` → `cache/model_p_base_report.txt`, `cache/model_p_choice.json`.
24,704 pitcher-season-levels (1,627–1,866 per season), 8,646 pitchers.

**Rating (ridge; trees lost at all three vantages):**
- **Kept:** age/level (z +4.7 / +4.3 / +4.1) and strikeouts (+2.7 / +3.4 / +3.6).
- **Dropped:** control, run prevention (minor-league ERA / WHIP / HR/9 add nothing,
  as the sabermetric consensus says), role, and trajectory.
- Rank accuracy 0.256 / 0.269 / 0.266, with top-50 hit rates of 0.28 / 0.26 / 0.22.
  Hitters were 0.43–0.45 and about 0.5, so pitchers are clearly harder, as expected.

**Soon (trees won by the preset rule: AUC 0.820 vs 0.818 / 0.846 vs 0.850 /
0.847 vs 0.815):**
- **Kept:** age/level (+3.6 / +5.1 / +4.9), strikeouts (+0.6 / +2.6 / +2.9), control
  (+1.3 / +1.2 / +0.2, marginal), and **role** (+1.3 / +2.0 / +1.0).
- **Dropped:** run prevention and trajectory.
- Final AUC 0.811 / 0.827 / 0.839. **Top-50 hit rates 0.08 / 0.08 / 0.20.**
- The top calibration bucket was 0.19 predicted vs 0.11 actual (overconfident).

**Review diagnosis of the weak "soon" top-N (not a bug):**
- **The target is rare:** only 2.3–2.9% of prospects post a top-120 season within
  2 years. So a top-50 rate of 0.08–0.20 is a 3–7× lift over the base rate.
- **What "useful" looks like:** a top-120 MLB pitcher season has a median of 73 IP;
  61% are under 90 IP and 25% are 150+ IP. Elite relievers qualify on ratios and
  strikeouts.
- **Who actually got there:** the prospects who hit "soon" averaged 24.9 years old
  with a 46% start share, many of them relievers and older arms.
- **Who the model favors:** its top 50 are young AAA starter prospects (age 23,
  about 90% starts), e.g. Grayson Rodriguez, Max Meyer and Cade Cavalli. They
  usually need more than 2 years to post a top-120 season, and their payoff shows
  up in the rating.
- **Tree vs plain model:** the plain logit's top 50 hit more at every vantage (6 / 7
  / 13 vs the trees' 4 / 4 / 10), but the preset kind rule compares ranking
  accuracy only, and the 2021 tree "win" was 0.002. **The rule stands; it is not
  re-decided after seeing results.** It is recorded here, and **pre-registered for
  the pitcher final check:** on sealed 2024, report the trees vs the plain model on
  "soon" AUC, top-50 and calibration.
  - If the trees lose on top-50 and calibration there too, production "soon" uses
    the plain model.
  - Either way, production "soon" odds get a calibration check before they're
    shown as percentages.

**3a check:** strikeouts were kept as a *group* for both outputs. The 3a result
(whiff / CSW add nothing *beyond K%*) was within-group and is not contradicted.

**Tree leads (for the pitcher final plan, as explicit terms under the same
rule):**
- For the rating, age × K% and age × CSW replicated at all three vantages. It's the
  pitcher version of the hitters' age × SLG, which was rejected.
- The "soon" model already is a tree model, so its patterns are already in it.

## Stuff layer design (P-B, P-C). Approved by the user 2026-09-28 ("go")

The user's two decisions:
- The stuff score predicts **next-season value at a fixed 100 IP workload**.
- **Savant 2015–2026** is the MLB training source: about 12 small CSVs from the
  host already in use, security-audited first.

**Probe findings that shaped the design (3 cached Savant requests, 2015 / 2019 /
2024):**
- **Per-pitch-type columns are served for every season.** Four-seam, sinker and
  cutter each have speed, spin, horizontal break and induced vertical break, plus
  pitch shares.
- **So metrics are built on each pitcher's *primary fastball*,** the most-thrown of
  FF / SI / FC. Four-seam-only metrics would drop pitchers with no four-seamer
  (44 of 800 in 2024, 45 of 725 in 2015). They would also mismeasure sinker-first
  pitchers, whose four-seamer is a minor pitch.
- **Horizontal break's sign flips with handedness** (2024 sinker −11.6, 2015 +15.8),
  so it enters as a **magnitude**.
- **`release_extension` is never served** (0 of 725 in 2015, 0 of 800 in 2024), so
  **extension is out**: there's no MLB training data for it, even though AAA game
  records carry it.
- **Offspeed is left out:** too many relievers throw none, and the missing values
  would drop them.

**Metrics** (defined to match Savant; ours are computed from game records):
- `fb_speed`, `fb_spin`, `fb_ivb`, `fb_hb` (magnitude): the primary fastball, 50+
  thrown.
- `breaking_speed`, `breaking_spin`: all breaking balls, 30+ thrown.
- `whiff_percent`: the pitcher's whiffs ÷ swings, on the hitter parity's chosen
  whiff definition.

**P-B: parity, then the tables** (mirrors 3b plan A):
- Our parser runs on the 2024 MLB game records and must reproduce Savant's 2024
  numbers: **r ≥ 0.98 and |mean bias| ≤ 0.1 SD per metric**. The bias rule is new
  because units matter here (movement in inches), not just correlation.
- Uncertain definitions run as variants, and the best is kept:
  - which pitch codes count as breaking;
  - movement from `breaks` vs `pfx` coordinates.
- If the gate fails, stop before building anything.
- After it passes, the build writes two files:
  - `cache/aaa_pitch_tracking.csv`: ours, AAA 2022–26.
  - `cache/mlb_pitch_tracking.csv`: Savant, MLB 2015–26.

**P-C: the stuff score** (mirrors step 1):
- **Target:** the next MLB season's line valued at 100 IP with the site's SGP
  formula (`labels.pitcher_sgp`: strikeouts scaled to 100 IP, ERA / WHIP / HR/9
  as-is, per-season replacement from `context`). It needs 25+ IP next season and
  is weighted by those innings.
- **Features:** age plus the groups velocity (`fb_speed`), fastball shape (spin,
  IVB, HB), breaking (speed, spin) and whiff. Each group is adopted by step 1's
  8-of-10 rule.
- **Also reported:** stuff vs box (K%, BB%), and robustness on the Hawk-Eye era
  only (2020+), since 2015–19 was Trackman and spin readings differ between the two
  systems.
- **AAA → MLB:** flat per-metric offsets from pitchers with 150+ pitches at both
  levels in the same season.
- **Gate:** AAA pitchers' first qualifying season in 2022–23, scored with the
  translated stuff score. It must rank their later MLB value (best season at 100
  IP, 25+ IP) above chance: **Spearman CI lower bound > 0** among arrivals. The
  2024 class is report-only.
  - If the gate fails, the stuff layer stops there.
  - If it passes, the pitcher final plan tests it as a layer, as for hitters.

## P-B parity result (run 2026-09-28, reviewed on Opus)

The first run failed on one metric: `breaking_spin` at r 0.9777, against 0.98
required. The bias was fine (+2.6 rpm on an SD of 248), and the other six metrics
all had r ≥ 0.998.

**Diagnosis:**
- 99.4% of pitchers matched within 5 rpm (median gap 0.26).
- The whole miss came from two knuckleball pitchers. One threw 936 knuckleballs
  (about 900 rpm): ours read 2,188 rpm against Savant's 941.
- **Savant counts knuckleballs as breaking balls.** Adding KN to the breaking set
  gives r = 1.0000 and bias 0.00.
- This is a definition fix, like the hitters' bunt and sweet-spot fixes. The gate
  was not loosened.

**Rerun: PASS on all 7 metrics** (2,430 games, 709,512 pitches):

| Metric | r | Bias |
|---|---|---|
| fb_speed | 0.9984 | −0.008 mph |
| fb_spin | 0.9998 | +0.15 rpm |
| fb_ivb | 0.9991 | −0.009 in |
| fb_hb | 1.0000 | −0.001 in |
| breaking_speed | 1.0000 | 0.000 mph |
| breaking_spin | 1.0000 | +0.001 rpm |
| whiff% | 0.9999 | −0.006 |

**Chosen definitions:**
- Breaking = SL / ST / SV / CU / KC / CS / KN.
- Movement from `breaks`, in inches. The `pfx` coordinates are on a different
  scale, and the loss rose from 0.043 to 1.81 when using them.

## P-C adoption rule correction (decided with the user 2026-09-28, BEFORE the prospect gate ran)

The first `stuff_run.py` run adopted no group, so the AAA prospect gate never
ran. **The cause was the rule, not the data.** P-C reused step 1's
`evaluate.adopt`, which requires *no* top-50 drop in each of 8 of 10 shuffles.
That's the flaw the 3c review had already found and fixed (1–2-player top-N swings
vetoing real gains): 3c's standard is a mean top-50 change ≥ −0.04.

The review measured the MLB comparisons without changing anything:

| Group | Rank gain | Mean top-50 change |
|---|---|---|
| Velocity | positive in 10/10 shuffles, +0.026 | −0.006 (±1 player per shuffle) |
| Fastball shape | 10/10, +0.025 | −0.004 |
| Whiff | 10/10, +0.075 | −0.044 (a consistent ~2-player drop) |
| Breaking | 8/10, about +0.001 | 0.000 |

About 86–90% of the model's top 50 were relievers either way; valuing at 100 IP
rewards relievers' rates.

**Corrected rule for P-C (`stuff.adopt`):** rank accuracy improves in ≥ 8 of 10
shuffles AND the mean top-50 change ≥ −0.04 (the 3c tolerance). The expected
consequence was fixed before rerunning: velocity and fastball shape are adopted;
whiff (−0.044) and breaking are not.

**Nothing else changes:**
- the AAA prospect gate (Spearman CI lower bound > 0 on the 2022–23 first
  qualifying seasons), which has not been looked at;
- the metrics, target and cohorts.

The staging rule (one pitch-level attempt if the *gate* fails) stands, and was not
spent on this rule defect.

## P-C result (run 2026-09-28 on Opus, after the rule correction)

`cache/stuff_report.txt` covers 3,710 MLB pitcher-seasons (t = 2015–25) from 1,202
pitchers. The target is the next season valued at 100 IP; ridge (rho 0.354) beat
gbm (0.316).

**Adopted:** velocity and fastball shape (rank gain 10/10), and **breaking at
exactly 8/10**.
- The expectation recorded before this run said breaking would *not* pass. It
  passes the recorded rule: rank gain +0.001, which is noise, and a top-50 change
  of 0.000. The rule governs, not the forecast. Its effect is negligible.
- Whiff was rejected (top-50 −0.044).

**On MLB:**
- Stuff *on top of* box (age, K%, BB%): rho 0.349 → **0.390** and top-50 0.632 →
  0.668, in 10/10 shuffles.
- Stuff + age alone (0.279) is weaker than box alone (0.349).
- Robust to the Hawk-Eye era only (t ≥ 2020) and to dropping 2020.

**Interactions:** fastball speed × IVB, IVB × HB and speed × spin are top-10 in
10/10 runs, but trees lost overall. These are leads for the pitch-level model.

**AAA → MLB offsets** (about 1,400 same-season pairs), small:
- fastball +0.17 mph and +18 rpm;
- breaking +0.33 mph and +21 rpm;
- movement about +0.2 in.
- Whiff differs a lot by level (−4.2 pts, slope 0.47) but isn't used.

**Prospect gate** (2022–23 AAA pitchers, first qualifying season, not
established): **PASS, narrowly.**

| 2022–23 cohort, 239 arrivals | Spearman vs later MLB value |
|---|---|
| stuff score | +0.155 [+0.025, +0.279] |
| box-score model | +0.224 |
| AAA K% | +0.255 |

- Stuff does sort who arrives: 48% of the top quintile vs 19% of the bottom.
- 2024 (report only): stuff +0.109 [−0.040, +0.255] vs K% +0.345.

**Reading:** stuff carries real MLB signal *beyond* box stats. For prospects on
its own, it's weaker than AAA strikeout rate. So the question that matters is
the layer test: does it add on top of the box model?

**Caveats for the pitcher final plan:**
1. **Redo the gate as-of** (stuff model fit only on MLB outcomes known by each
   cohort's year). Gate pitchers' own later MLB seasons are among this run's
   training rows. For hitters the as-of refit changed little (0.391 → 0.416).
2. **Test it as a layer** on top of the P-A base model: residualized and
   as-of, like hitters' tracking layer. The gate only licenses that test.
3. **Per the staging rule,** the pitch-level model is now the *upgrade candidate*.
   It must beat this season-level score in the final plan. The weak standalone
   showing makes it worth building.

## P-E: the pitch-level stuff model (designed + pre-registered 2026-09-28, before any pitch-level result)

**Why now:** the user chose "the best chance of doing this accurately" over speed.
The sealed 2024 pitcher class can be opened only once, so both stuff scores must be
ready before P-D opens it.

**Data** (the user approved the download 2026-09-28):
- **MLB game records 2020, 2021 and the rest of 2022**, about 4,300 games through
  `fetch_pbp.py`, `statsapi.mlb.com` only.
  - Hawk-Eye only; 2015–19 Trackman is skipped as a mismatched system.
  - A two-game check (one 2020 game, one 2021 game) that the tracking fields exist
    comes before the bulk run. The security audit comes first.
  - `fetch_pbp.py` skipped 2020 at every level; it's fixed to skip only the minor
    leagues.
- AAA 2022 (PCL) and 2023–26 are already on disk.
- **Known gap:** extension and release point have no Savant values to check
  against. They come from the same feed whose speed, spin and movement passed
  parity.

**Pitch-level models** (location excluded, as in public stuff models):
- **Per-pitch features:** speed, spin, IVB, horizontal break and release side
  (both sign-flipped for left-handers, so arm-side is consistent), release height
  (the `z0` coordinate at 50 ft), extension, same-side matchup, and speed / IVB /
  HB gaps to the pitcher-season's primary fastball.
- **Families:** fastball (FF / SI / FC), breaking (SL / ST / SV / CU / KC / CS /
  KN) and offspeed (CH / FS / FO / SC). Others are dropped.
- **Two gradient-boosted models per family:**
  - **P(whiff | swing):** whiff and swing codes as in the hitter parity's chosen
    variant.
  - **Expected damage on contact:** first a small model maps each MLB ball in
    play's (EV, LA) to the wOBA value of its result (1B 0.89, 2B 1.27, 3B 1.62,
    HR 2.10, everything else 0), which is the xwOBA idea. The damage model then
    predicts that smoothed value from pitch features.
- **As-of:** at vantage c, the pitch models train only on MLB seasons 2020..c.
- **Pitcher features:** each pitcher-season's mean predicted whiff | swing
  (`pl_whiff`) and mean predicted contact damage (`pl_damage`) over all its
  pitches in the three families, with 300+ pitches.

**From pitch grades to fantasy value** (P-C's machinery; the data sets the
weights):
- Ridge on age plus the adopted pitch-level features, predicting next season's
  value at 100 IP.
- Adoption uses `stuff.adopt` on MLB rows with t = 2020–25 (groups: whiff = `pl_whiff`,
  damage = `pl_damage`).
- AAA → MLB offsets come from same-season pairs, as-of.
- **Known minor issue:** MLB features are predicted by pitch models whose training
  included that same season's pitches. The trees are shallow and regularized on
  100k+ rows, so the in-sample lift should be small. It's disclosed rather than
  engineered away.

**Pre-registered decision rule (both scores, as-of, on identical pitchers):**
1. **Prospect gate, as-of:** AAA pitchers' first qualifying season in 2022–23,
   not established, arrivals only. Vantage c = the cohort year: the pitch models
   use MLB ≤ c, the mapping uses MLB t ≤ c−1, and the offsets use pairs ≤ c. The
   season-level (P-C) score is refit the same way (Savant t ≤ c−1). A score is
   usable only if its Spearman CI lower bound is > 0.
2. **Which score:** the pitch-level score replaces the season-level one only if
   its Spearman beats the season-level's by **≥ 1 paired player-bootstrap SE** and
   its own CI lower bound is > 0. On a tie, the season-level score stays.
3. **If the season-level score fails its as-of gate:** the pitch-level score (this
   plan) *is* the staging rule's single pre-registered attempt. If it also fails,
   stuff is out for pitchers until new cohorts arrive.

The verdict goes to `cache/stuff_choice_final.json`, which P-D reads.

### P-E result (2026-09-28): SEASON-LEVEL stays; the rule was applied as written

`pitchlevel_run.py`; full report in `cache/pitchlevel_report.txt`.
- **Adoption on MLB (t = 2020–25, 2,108 rows):** both pitch-level features were
  adopted 10/10 (whiff: ρ 0.223 → 0.329; damage: 0.262 → 0.329).
- **Context on identical MLB rows (report only, n = 2,081):**

  | score | out-of-fold ρ |
  |---|---|
  | box score (age, K%, BB%) | 0.334 |
  | pitch-level | 0.330 |
  | season-level | 0.273 |

  The pitch-level number is inflated by the disclosed in-sample pitch models.
- **As-of prospect gate (697 identical AAA pitchers, 239 arrivals):**

  | score | Spearman ρ | 95% CI | cohort 2022 (n=69) | cohort 2023 (n=170) |
  |---|---|---|---|---|
  | season-level (refit as-of) | +0.146 | [+0.016, +0.274] | +0.109 | +0.153 |
  | pitch-level | +0.167 | [+0.030, +0.294] | +0.250 | +0.122 |
  | AAA K% (reference) | +0.255 | [+0.132, +0.371] | +0.212 | +0.276 |

  The per-cohort figures are report only.
- **Difference:** pitch-level minus season-level = +0.021, paired player-bootstrap
  SE 0.062. That is well short of 1 SE, so under the pre-registered tie rule the
  season-level score stays.
- **What this settles:**
  - The P-C gate caveat is resolved. The season-level score still clears 0 when
    refit strictly as-of (+0.146, vs +0.155 before, when its gate pitchers' own
    seasons were in training).
  - Stuff alone still ranks prospects below AAA K% alone. Its value, if any, is
    as a layer on top of strikeouts. P-D tests exactly that; nothing here claims it.
- **Not done, on purpose:** no re-run with other hyperparameters, feature sets or
  cohorts. The pitch-level score had its pre-registered attempt.

## P-D: the pitcher final run (approved by the user 2026-09-28, BEFORE 2024 was opened)

`model_p_final.py` mirrors the hitters' `model3c_final.py`. Every rule below is
fixed before the sealed 2024 pitcher class is opened.

**1. Tree leads as explicit terms (rating only).**
- `age_x_k` = age × k and `age_x_csw` = age × csw: products of the standardized
  features, as the hitters' `cohorts.add_products`.
- Each lead is tested alone on top of P-A's rating keys (ridge) at the rating
  vantages 2019 / 2021 / 2022, under `walkforward.adopt`.
- "Soon" is not tested: its preset model is trees, which already search
  interactions.

**2. The sealed 2024 class is opened ONCE, for "soon" only** (its 4-year rating
answers are not in yet). Two decisions, in this order.

- **a. Trees vs plain logit.** Both are fit on P-A's "soon" keys, trained as-of
  2024 (classes ≤ 2022), and scored on 2024.
  - Reported for each: AUC, top-25 / top-50 / top-100 and the calibration table.
  - **Calibration error:** Σ n_b · |mean predicted_b − actual_b| / Σ n_b over the
    10 buckets of `walkforward.calibration`.
  - **Rule (the P-A wording):** switch to the logit only if the trees LOSE on
    both, i.e. the logit's top-50 hit rate is strictly higher AND its calibration
    error is strictly lower. Anything else, a tie included, keeps the trees.
- **b. The stuff layer for "soon",** on the model chosen in (a) (hitter precedent).
  - The stuff score is P-C's season-level score (P-E verdict "season") at vantage
    2024: Savant mapping on t ≤ 2023, AAA→MLB offsets from same-season pairs ≤ 2024,
    AAA rows with 300+ tracked pitches.
  - **Training:** the AAA rows of the as-of-2024 training set that have a score.
    That is only the 2022 class (PCL only). The score is residualized on the base
    model's out-of-fold prediction, and `tracking_layer.trust_weight` gives the
    weight and its bootstrap CI.
  - **Test:** the 2024 AAA pitchers with a score.
  - **Rule:** use it only if the weight's CI excludes 0 AND the paired AUC gain on
    2024 is z ≥ `walkforward.WIN_Z` (1.0).
  - Low power is expected. "Not used" would mean untested, not refuted.
- **Opened-once safeguard:** both decisions, and the 2024 numbers behind them,
  are written to `cache/model_p_2024_decisions.json` the moment they are made. A
  later run reads that file and never re-decides. The script never overwrites it;
  deleting it takes the user's explicit say-so.

**3. As-of stuff gate:** carried from P-E (`cache/stuff_choice_final.json`,
season-level +0.146 [+0.016, +0.274]). Not rerun.

**4. Production as of 2026 → `cache/pitcher_ratings.csv`.**
- **Rating:** ridge on P-A's keys plus any adopted lead.
  - Stuff layer: the stuff score at vantage 2026 (Savant t ≤ 2025, offsets
    ≤ 2026).
  - Its weight is learned from the AAA 2022 class (complete 2023–26 windows) plus
    the 2023–24 AAA classes, weighted by the share of their 4-year window already
    seen (hitter precedent).
  - It is applied only if the weight's CI excludes 0, and flagged PROVISIONAL: no
    later complete class exists to check it.
- **Soon:** the model chosen in 2a. Stuff is applied only if 2b said "use" AND the
  production weight's CI excludes 0.
- **One row per pitcher,** at their highest level. Columns: `player_id, name,
  level, age, start_share` (unstandardized games-started share), `rating_sgp,
  rating_percentile, p_useful_within_2, stuff_in_rating, stuff_in_soon, flags`.
- **Showing "soon" as percentages (rule for the shopping list):** the chosen
  model's mean predicted rate must fall inside the 95% Wilson interval of the
  actual rate on 2024, both in the top calibration bucket AND overall. If it does,
  `percent_ok: true`; otherwise the shopping list shows rank tiers.
  - The check uses the as-of-2024 fit as a stand-in for the production fit.
    Disclosed.
- **Sanity (report only):**
  - The top 15 by rating should be AA/AAA pitchers, about ages 20–25.
  - The role mix (start share) of the top 50 is reported.
  - A failure stops the run for an Opus review; nothing is tuned.
- **Outputs:** `cache/model_p_final_report.txt` and `cache/model_p_final.json`.

**Code:**
- New `psmodel/stuff_layer.py`: the stuff score as-of a vantage and AAA pitcher
  scores. It reuses `tracking_layer`'s `residualize` / `trust_weight` / `adjust`.
- `pcohorts.LEADS` and `add_products`.
- `model_p_final.py`.
- Tests on synthetic rows. The 2024 class is opened only by the real run.

**Out of scope (next plans):**
- P-F: the pitcher consensus (FanGraphs) gate.
- Then pitchers on the shopping list.

**Backlog (the user: "open to it, not super sold"):** a year-by-year "soon"
target for hitters and pitchers. Each prospect-year asks "a top season next
year?", so classes with open windows add their seen years without being mislabeled
as misses.
- It gains about half a class of recent data.
- It needs its own pre-registered test on a clean class: the 2025 class, once its
  answers arrive after 2027.
- Optional; low priority.

**The user's question, answered (2026-09-28):** does the seal stop us from
learning from fast risers? No.
- The seal only keeps 2024 out of the *tests*. Production trains on every class
  whose answer is known by 2026, so "soon" includes 2024.
- What delays learning is each class's answer window:
  - A 2025 riser enters "soon" training after 2027.
  - Rating classes enter 4 years after their season.

## Stuff layer: staging and the pitch-level follow-up (pre-registered 2026-09-28)

**What the review of public stuff models found** (FanGraphs Stuff+ and PitchingBot
primers, tjStuff+, aStuff+):
- The serious models grade **each pitch** on its expected outcome (run value, or
  swing / whiff / called strike / contact damage), leaving location out, then
  average up to the pitcher. Grades stabilize in about 200 pitches.
- Inputs: velocity, spin, movement, **release point and extension** (reported to
  matter about as much as movement), spin axis, and secondary pitches' **speed and
  movement gaps from the pitcher's own fastball**.
- The models are gradient-boosted trees, one per pitch family.
- Predictiveness has decayed as pitchers train toward these metrics: Stuff+ vs
  wOBA fell from about 0.50 in 2021 to 0.35 in 2025. So train on recent seasons,
  as-of.

**Why not use one of theirs:**
- They're third-party / community products, which the user's first-party data rule
  excludes, and FanGraphs automation is blocked.
- Published grades come from *current* models, so backtesting 2022–23 prospects on
  them would leak the future. Grades as they stood at the time mostly don't exist.
- Minor-league coverage is patchy or paywalled.

**Staging (decided with the user):**
1. **Run P-B / P-C as written** (season averages). This answers whether pitch
   tracking predicts prospects' fantasy value at all, cheaply.
2. **If the P-C gate PASSES:** a pitch-level stuff model (below) is the upgrade. It
   replaces the season-level score only if it beats it under the same adoption rule
   in the pitcher final plan.
3. **If the P-C gate FAILS:** the pitch-level model gets **one** attempt, with the
   same gate, cohorts and rule, before the stuff question is closed. This second
   try is pre-registered here, before any result, and applies only to this
   specific, stronger method. If it also fails, stuff is out for pitchers until new
   cohorts arrive.

**The pitch-level model, sketched for later design:**
- Trained on MLB game-record pitches (Hawk-Eye, 2022 onward), with each vantage
  training only on seasons at or before it.
- Features per pitch: velocity, spin, induced vertical and horizontal break (arm
  side), release height and side, extension, handedness, and for secondaries the
  speed / movement gap to the pitcher's primary fastball.
- Targets: P(whiff | swing) and expected damage on contact, combined into one
  per-pitch value, with a tree model per pitch family. Location excluded.
- AAA pitches scored with it (same tracking system, so parity is a lighter check),
  then averaged per pitcher-season into the stuff score.

## Carried over unchanged (no decision needed)

- **As-of discipline:** a vantage trains only on classes whose answer is known,
  and test-class players are kept out of training.
- **Vantages:** rating 2019 / 2021 / 2022; soon 2021 / 2022 / 2023.
- **2024 is sealed for pitchers.** Unlike the hitters' 2024 class, it has never
  been opened, so pitchers get a clean final check.
- **Adoption rule:** ≥1 SE at 2 of 3 vantages, none ≤ −2 SE, mean top-50 change
  ≥ −0.04.
- **Models:** ridge (rating) and logit (soon), with trees as a challenger.
- **Security:** re-audit before any network step; first-party sources only;
  `cache/` never committed.

## Known pitcher risks (priced by the target, not modeled separately)

Injuries, including Tommy John surgery; role changes; innings limits. The rating
takes the *best* season in four years, so one lost season doesn't zero a
pitcher, but a career-altering injury does. That's the honest outcome for a
fantasy roster, so no injury model is proposed.

## Code changes (small, backward-compatible)

- **`asof.py`:** add a `typ` argument, defaulting to `"H"` so hitter behavior is
  unchanged, to `attach_ranks`, `ref_curve`, `useful_value`, `rating_target` and
  `soon_target`.
  - Starters: `{"H": 144, "P": 120}`.
  - Eligibility: 100 PA for hitters, 25 IP for pitchers.
- **`walkforward.py`:** read the row's `typ` (default `"H"`) when attaching
  targets and top-N hits.
- **New `psmodel/pcohorts.py`:** pitcher rows, groups and the established-IP cut,
  mirroring `cohorts.py`.
- **New `model_p_base.py`:** mirrors `model3c_base.py`.
