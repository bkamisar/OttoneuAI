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
