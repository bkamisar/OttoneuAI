# FV+: FanGraphs FV tuned to 4x4 Ottoneu (design, 2026-09-30)

Designed on Opus with the user; approved in conversation 2026-09-30. Everything in
this file is fixed BEFORE any FV+ result is computed. Do not change a rule, a
feature, or a threshold after seeing a result. A change needs a new dated section
that says what was already seen.

## Why this exists

The first pass (3c hitters, P-A..P-F pitchers) built models from stats and then
raced them against FanGraphs' FV. They lost on rating; FV was never an input. The
user's goal was different: **start from FV and learn where your league's value
differs from it.** Every model scored outcomes in 4x4 terms, but none started
from FV. That includes the pitcher stuff layer, which sat on the stats model.

A review on 2026-09-30 found three gaps:
1. FV was never the base. The only combinations tried were a 50/50 rank average,
   an information-only fitted blend, and a tool-grade test that REPLACED FV.
2. Stats are normalized within (level, season), not within league
   (`psmodel/features.py:3-5`). The Pacific Coast League's offense (and the old
   California League's) inflated hitters and punished pitchers. The code
   comment's reason ("leagues changed levels in 2021") does not apply within a
   single season.
3. Verdicts rested on ~3 classes each and were never pooled.

## What is already seen (declared, so replications are labelled as such)

- Stats model vs FV: FV wins on rating (hitters, pitchers). The hitter soon blend
  beat FV 3/3; the pitcher blend was positive in 6/6 comparisons, clearing 1 SE
  once.
- Bat grades ((Hit + Game Pwr)/2) REPLACING FV lost badly on rating.
- Step 1: pulled-air terms improved the top-50 hit rate among 2022-23 AAA hitters
  (not FV-conditioned).
- P-D: the stuff layer did not help on top of the stats model.
- Every class with answers has been looked at in some form. **All adopted
  findings are provisional until the 2025 class confirms them** (soon: after the
  2027 season).

## Phase 1: league-season normalization (correctness fix)

- `standardize_within` groups by (level, season, league name) for minor-league
  rows. A league-season group with fewer than 30 rows falls back to
  (level, season). The Mexican League stays excluded.
- Rerun the whole chain: hitter base, then final; pitcher base, then final; then
  `consensus_gate.py` (both); then `build_shopping_list.py`.
- Frozen 2024 decisions stay frozen (`model_p_2024_decisions.json` and the
  hitter 2024 decisions). Vantage-level adoption decisions are re-made by the
  same unchanged rules. Every change in adopted groups, rank accuracy and the
  consensus verdict is reported old vs new.
- If the consensus verdict changes, the new verdict takes effect. The rule is
  unchanged; only the data got more correct.

## Phase 1 result (run 2026-09-30 on Opus; commits 2c7f04c..b30f771)

- **Audit:** 0 FAILs. Every row has a league. Every league-season group has at
  least 110 rows, so the fallback is never used. Features re-derive exactly
  (max diff 0).
- **Hitters: essentially unchanged.**
  - Adopted groups: the same.
  - Consensus verdicts: the same (rating: follow FV; soon: model as tiebreaker).
  - Ratings vs old: Spearman 0.996 (rating) and 0.989 (soon).
  - **Surprise, reported as such:** Pacific Coast League AAA hitters moved UP
    +0.5 rating-percentile points on average (International League −0.4).
    The idea that PCL inflation was why the model lost to FV is NOT supported;
    the effect is tiny.
- **Pitchers:**
  - Rating: unchanged groups, Spearman 0.999. PCL pitchers +1.7 points,
    International League −1.1 (the expected direction, small).
  - **Soon: two borderline group decisions flipped.**
    - control dropped: 2/3 at z +1.3/+1.2 before, now 1/3;
    - trajectory kept: now 2/3 at z +1.2/+1.2.
    - Soon ratings vs old: Spearman 0.957, top-50 overlap 29/50.
  - **Consensus verdict for pitcher soon changed: follow FV → model as
    tiebreaker.**
    - Blend vs FV by class: z +1.4 / +1.6 / +0.7, versus +0.2 / +0.9 / +0.7
      before.
    - Still UNSTABLE (the graduates-restored run says "model leads").
    - It rests on the two knife-edge group decisions above.
- **Decision (the user, 2026-09-30):** the new verdict stands and is recorded.
  The page change (a "Closest to helping" lens for pitchers) waits for Phase 2.
  P-SM asks the same question pooled over 7 soon classes instead of 3, so the
  page gets one consistent update.
- `data/prospect_model.json` was regenerated: the pitcher soon tiers moved; the
  hitter output is near-identical.

## Amendment A (2026-09-30, BEFORE any Phase 2 result; approved by the user)

**What was seen:** only sample sizes. Graded players and "soon" successes per
class were counted; no feature was compared with any outcome.

| class (list) | hitters graded / soon hits | pitchers graded / soon hits |
|---|---|---|
| 2016 (2017) | 204 / 21 | 202 / 14 |
| 2017 (2018) | 174 / 17 | 140 / 7 |
| 2018 (2019) | 219 / 7 | 204 / 11 |
| 2019 (2020) | 283 / 10 | 267 / 14 |
| 2021 (2022) | 331 / 28 | 317 / 14 |
| 2022 (2023) | 312 / 25 | 345 / 22 |
| 2023 (2024) | 292 / 16 | 325 / 17 |
| 2024 (2025) | 306 / 22 | 364 / 22 |

(2020 had no minor-league season, so there is no class 2020.)

**Corrections and changes (these replace the matching parts of Phase 2 below):**

1. **Strict as-of fitting.** A test class v is fitted only on classes c whose
   answer is known at v (`asof.rating_known` / `soon_known`: c + 4 <= v for
   rating, c + 2 <= v for soon), exactly like every other model here. A test
   class is used only if its training set has >= 300 players and, for soon,
   >= 30 successes. That gives:
   - **Rating:** test classes 2021 and 2022. The spec's "5 rating classes" was
     wrong.
   - **Hitter soon:** test classes 2019, 2021, 2022, 2023, 2024.
   - **Pitcher soon:** test classes 2021, 2022, 2023, 2024 (2019's training has
     only 21 successes).
2. **The decision test is one omnibus model per player type and output: 4
   decision tests, one Holm family.**
   - The base is `fv_score`. FV+ is `fv_score` plus ALL the pre-registered
     adjustments for that output, in one regularized model: ridge with CV for
     rating, logit with CV for soon (the project's simple kinds).
   - Power: with ~100 pooled soon successes, the original 19 separate tests
     could only detect gains of about +0.05; one omnibus test per output is the
     most powerful honest answer to "can FV be tuned to 4x4 at all?".
   - The components per model are the Phase 2 tables' adjustments:
     - **Hitter rating:** RW (Hit, Game Pwr, Spd, premium position, BB%), UP
       (age relative to league, Raw Pwr minus Game Pwr), OP, SM.
     - **Hitter soon:** RW, OP, PX (level flags, age relative to league), SM.
     - **Pitcher rating:** SH (FB, best breaker, CH, CMD, FB x CMD,
       FB x breaker, reliever), GB, OP, SM.
     - **Pitcher soon:** SH, GB, OP, PX, SM.
   - **Interactions** use grades centred at 50:
     (FB − 50) x (CMD − 50) / 10 and (FB − 50) x (breaker − 50) / 10.
   - **Missing tool grades** are imputed with that list's median for the grade,
     and missing counts are reported.
   - **Adoption (all must hold):**
     - pooled z of the paired gain, two-sided, Holm-adjusted p < 0.05 across
       the 4;
     - gain > 0 in a majority of test classes (rating 2 of 2; hitter soon >= 3
       of 5; pitcher soon >= 3 of 4);
     - no class at or below −2 SE;
     - soon: pooled top-50 not down more than 0.04;
     - shuffle control: the adjustment block, shuffled jointly among players of
       the same FV grade within each class, 200 times; the real gain must beat
       the 95th percentile.
   - **Components are NOT adopted individually.** Each component group's
     contribution is reported as the drop in pooled gain when that group is
     removed, with a bootstrap interval. It is labelled "explanation, not
     decision". Expected signs are compared as before.
   - An adopted model becomes the FV+ column for that player type and output.
3. **The Statcast group, exploration map and confirmation queue are
   unchanged.** The Statcast group's partial Spearman needs no training, so its
   classes are every class with AAA tracking: soon 2022-2024, rating 2022.

**Note on Amendment A (2026-09-30, before any model was fit; the user chose to
follow the rule):**
- The listed hitter-soon test class 2019 was an arithmetic slip: the count
  forgot that the rule removes the test class's own players from training.
  That removes 94 hitters and leaves 284, under the 300 minimum.
- The rule stands, so **hitter soon tests 2021-2024** (majority 3 of 4).
- The other three models' classes matched the rule exactly.
- The runner's pre-registered stop caught the difference before any fit.

## Phase 2 result (run 2026-09-30 on Opus; `fvplus_run.py`, report `cache/fvplus_report.txt`)

**Plumbing:** FV-alone rank accuracy and top-50 match the consensus gate's FV
line exactly in every class, for hitters and pitchers. The comparison ran on
the same players in the same order.

| model | test classes | per-class gain (z) | pooled z | Holm p | shuffle | guard | verdict |
|---|---|---|---|---|---|---|---|
| hitter rating | 2021, 2022 | −0.5, −0.2 | −0.49 | 0.62 | — | fails | **FV stands** |
| hitter soon | 2021-2024 | +0.4, +1.9, +1.5, +1.1 | +2.48 | 0.039 | real +0.30 vs 95th pct −0.01 | z +3.8, 4/4 | **ADOPT FV+** |
| pitcher rating | 2021, 2022 | −1.0, −1.1 | −1.44 | 0.30 | fails | fails | **FV stands** |
| pitcher soon | 2021-2024 | +0.7, +2.0, +2.4, +1.2 | +2.97 | 0.012 | real +0.52 vs 95th pct +0.04 | z +3.8, 4/4 | **ADOPT FV+** |

AUC gains for soon run +0.02 to +0.18 per class; the top-50 hit rate is up on
average (hitters +0.035, pitchers +0.065).

**What drives it (components, explanation only):**
- **Pitcher soon:** level and age (PX) carry most of it. Dropping them loses
  +0.39 (z 4.8). Ground balls (+0.05, z 1.8) and the stats model (+0.04, z 1.9)
  add a little. The pitch-grade shape block does not help (−0.16).
- **Hitter soon:** spread across the re-weighted grades (+0.06), the stats model
  (+0.02) and opportunity. The groups overlap, because the stats model already
  carries level and age.
- **Reading:** FV grades a player's ceiling, not his timing. What FV+ adds for
  "soon" is mostly how close a player is to the majors, which FV leaves out on
  purpose.
- **Rating:** adding grades and stats to FV HURT (hitters −0.03 pooled,
  pitchers −0.10). FV already prices long-run value better than these
  adjustments can; only the stats model helped within it (hitter SM +0.065,
  z 3.8), not enough to carry the rest.

**Weights (production fit, standardized, 95% player bootstrap):**
- **Hitter soon:**
  - Level (AAA +0.94, AA +0.71), BB% +0.29, Game Power +0.32 and worse-team
    opportunity −0.20 all run the expected way.
  - Premium position −0.30 [−0.58, −0.08]: glove-first prospects arrive and
    produce less in 4x4, within the same FV.
- **Hitter rating:**
  - Speed −0.041 [−0.071, −0.010], in the expected direction (FV pays for SB,
    4x4 doesn't).
  - **Surprise:** age relative to league +0.034 [+0.002, +0.068]. Within the
    same FV, OLDER hitters did better on the 4-year rating, the opposite of the
    "upside premium" expectation.
- **Pitcher soon:**
  - Level and age (older) +, ground balls +0.17 [+0.00, +0.38], reliever +0.18
    (borderline).
  - **Surprise:** best breaking-ball grade −0.16 [−0.37, −0.04]. Within the same
    FV, a better breaker meant LESS near-term value.

**Statcast group (provisional):**
- 2022 is n/a everywhere: fewer than 30 graded AAA players with the measure,
  because 2022 game records are PCL-only.
- Pulled air for soon: +0.09 / +0.20 (pooled z +1.58).
- Unrealized-power flag: −0.08 / −0.08 (z −1.36).
- Stuff: +0.24 / −0.20 (z +0.28).
- Nothing near Holm. It is decided after 2028 as planned.

**Exploration map and confirmation queue:** 24 cells were queued (95% interval
excludes 0, n >= 20). Notable ones:
- **Pulled air HIGH with EV HIGH:** +0.13 on soon (n 41).
- **Pulled air HIGH with EV LOW:** −0.06 (n 21). This is the Paredes-style
  profile, opposite to the article's claim.
- Low speed +, and non-premium position +, on both hitter outputs.
- A few pitch-grade pairs.
- The pitcher profiles (power arm, command artist, breaker-first) show nothing:
  FV prices "kind of pitcher" already.
- All of these are pre-registered for the 2025+ classes; none is adopted now.

**Consequences (per the spec):**
- FV+ soon is adopted for hitters AND pitchers. It becomes a column and a sort
  option on the shopping list, labelled with what it adjusts.
- FV stays the default sort until the 2025 class confirms (soon answers after
  the 2027 season).
- The pitcher "Closest to helping" lens deferred in Phase 1 is now answered by
  FV+ soon, a stronger test than the consensus blend.
- The page work is the next plan.

## Phase 2: FV+ tests

### Population and data

- **Players:** graded players on Board list Y, matched to our ids by
  `consensus.match` (name + calibrated age). This is plan C's graded population.
  Plan C's graduates-restored run is repeated as a guard. If it disagrees, the
  more cautious call stands.
- **Targets:** unchanged. Hitter rating (best season's rank in the next 4,
  valued on the as-of rank-to-SGP curve) and soon (top-144 season within 2).
  Pitchers use the P-A/P-D equivalents. List Y pairs with vantage Y-1, as in
  plan C.
- **Classes with answers:**
  - Rating: lists 2017-2023.
  - Soon: lists 2017-2025.
  - 2017-18 are thin, so they are used for fitting only, never as test classes.
- **Walk-forward:** fit on all earlier lists, test on list Y.
  - Rating test classes: 2019-2023 (5).
  - Soon test classes: 2019-2025 (7).
- **Base:** `fv_score` (FV plus the Top 100 / org-rank tiebreaks), entered
  linearly. Rating uses a linear model; soon uses a logit.
- **Adjustments:** added to that base. Each decision test compares "base +
  adjustment" against "base alone" on the same players.
- **FV grades:** future grades ("30 / 55" becomes 55) from the Board; the
  Board's stat columns are never used. All stats come from our as-of pipeline
  after the Phase 1 normalization.

### Decision tests: hitters (Holm family H, 8 tests)

| Test | Adjustment (all within FV) | Scoring-rule reason | Expected | Outputs |
|---|---|---|---|---|
| H-RW re-weighted FV | Hit, Game Pwr, Spd grades; premium position (first listed Pos in C/SS/CF); as-of BB% | FV credits stolen bases, glove and batting average; 4x4 scores OBP, SLG, HR and R only | Spd weight below 0; Game Pwr and BB% above 0; position unclear | rating, soon |
| H-UP upside premium | age minus the level's mean age (as-of); Raw Pwr minus Game Pwr | A bust scores 0 however close they came, so the payoff is lopsided and volatile profiles are worth more than FV's typical-outcome grade | younger and bigger gap = better | rating |
| H-OP opportunity | parent club's win% in season Y-1 | Playing time drives near-term value; FV is organization-neutral | lower win% = better | rating, soon |
| H-PX proximity | highest level in vantage season; age minus the level's mean age | FV grades ceiling, not timing (replication of the hitter soon blend) | higher and older = better | soon |
| H-SM stats model | our as-of model percentile (rating model for rating, soon model for soon) | the pooled within-FV test never run (replication) | better | rating, soon |

### Decision tests: pitchers (Holm family P, 9 tests)

| Test | Adjustment (all within FV) | Scoring-rule reason | Expected | Outputs |
|---|---|---|---|---|
| P-SH pitcher shape | FB, best breaker (max of SL and CB), CH, CMD grades; FB x CMD; FB x best breaker; reliever flag from Board Pos | "What kind of pitcher": FV sets the level, the grades set the shape. Relievers are discounted by FV but hold 4x4 ratio value | no call on individual weights; reliever above 0 for soon | rating, soon |
| P-GB ground balls | GO/(GO+AO), as-of, league-normalized, IP-weighted across levels | HR/9 is a category; FV does not price it directly | more ground balls = better | rating, soon |
| P-OP opportunity | as H-OP | as H-OP | as H-OP | rating, soon |
| P-PX proximity | as H-PX | as H-PX | as H-PX | soon |
| P-SM stats model | as H-SM | as H-SM (replication) | better | rating, soon |

- **Missing pitch grades:** a pitcher without an SL or CB takes the other one.
  With neither, the breaker is 20; a missing CH is 20.
- **Reliever flag:** Board Pos in the relief set. The plan confirms the codes
  used (for example MIRP or SIRP).
- **K% (H6 in the conversation):** covered by P-SM and the breaker grade; not a
  separate test.

### The adoption rule (identical for every decision test)

- **Metric:** rating uses Spearman (rank accuracy); soon uses AUC.
- **Per-class gain:** the paired player-bootstrap gain `W.paired_gain` of
  base + adjustment over base alone.
- **Pooled z:** sum(d) / sqrt(sum(se^2)) over the test classes.

A test is ADOPTED only if all five hold:
1. Holm-adjusted two-sided p < 0.05 within its family (H or P).
2. Gain > 0 in a majority of test classes (rating >= 3 of 5; soon >= 4 of 7).
3. No test class at or below -2 SE.
4. For soon: the pooled top-50 hit rate is not down more than 0.04.
5. **Shuffle control:** the real pooled gain beats the 95th percentile of 200
   runs in which the adjustment's values are shuffled among players of the
   same FV grade within each class.

Fitted weights are reported with bootstrap 95% intervals and compared with the
expected signs above. A sign opposite to the expectation is reported as a
surprise, never explained away.

### Statcast group (provisional; Holm family S, 6 tests)

These only exist for AAA from 2022, so there are too few classes to decide now:
soon lists 2023-2025, and rating list 2023 only. With no earlier class to fit on,
each is tested as a **partial Spearman with the target, controlling for
`fv_score`**, per class and pooled. There is no fitting.

| Test | Measure | Reason | Expected | Outputs |
|---|---|---|---|---|
| S-PA pulled air | share of batted balls pulled in the air (LD + FB), from the AAA game records on disk | pulled fly balls turn contact into in-game power, most of all without big exit velocity (the user's gut feeling; Pitcher List's "kings of the pulled fly ball") | better | rating, soon |
| S-EV unrealized power | indicator: top-third `avg_best_speed` AND bottom-third (LD% + FB%) among AAA hitters that season | big exit velocity with the ball on the ground: a leap if the player lifts it (Wood/Walker) | rating better; soon no call | rating, soon |
| S-ST stuff | season-level stuff score (`stuff_choice_final.json`) | stuff has never been tested against FV | better | rating, soon |

- **Measurement caveat (S-PA):** our AAA pull measure matches Savant at about
  r 0.92, which failed the 0.98 parity bar for model features. Noise can only
  push this test toward "no effect", so it is allowed here, disclosed.
- **Stuff x grades** (for example high stuff with weak secondaries, or command
  and breakers without velocity) is a 2x2 map within FV: stuff high/low by
  (CMD + best secondary) high/low. It is descriptive only.
- **Reporting and decision:** reported now with the same rule, labelled
  PROVISIONAL. Formally decided when soon has >= 5 tracked classes and rating
  has >= 3 (after the 2028 season), with this rule unchanged.
- **Not testable:** bat speed and attack angle. They are not in public
  minor-league data.

### Exploration map (descriptive only; never adopts anything)

- Within FV grade buckets (40, 45, 50, 55, 60+), mean outcome with counts and
  bootstrap intervals by:
  - each hitter grade bin (Hit, Game Pwr, Raw Pwr, Spd) and position;
  - each pitch grade, and every pair of pitch grades;
  - the named profiles: power arm (FB >= 60, CMD <= 40); command artist
    (CMD >= 55, FB <= 50); breaker-first (best breaker >= 60, FB <= 50);
  - pulled air at low vs high exit velocity (the article's interaction);
  - the stuff x grades 2x2.
- Anything whose interval excludes zero goes to a **confirmation queue**: one
  line each, pre-registered for the 2025+ classes under the adoption rule above.
  Nothing from the map changes FV+ now.

## Outputs

- `cache/fvplus_report.txt`: every test and its weights, the guard run, the
  shuffle control, the Statcast group and the exploration map.
- `cache/fvplus_verdict.json`: the adopted tests per family.
- **Consequence:** if at least one test is adopted for a player type, "FV+"
  (FV plus the adopted adjustments, refit on all answered classes) becomes a
  column and a sort option on the shopping list for that type, with a label
  naming what it adjusts. FV stays the default sort until the 2025 class
  confirms. If nothing is adopted, the report stands as "FV already prices these
  for 4x4", with the table of what does and doesn't matter.

## New data (small, first-party)

- **Parent-club win%:** MLB StatsAPI standings for 2016-2024 (9 requests). Board
  Org abbreviations are mapped to team ids.
  - Runs a security audit before the network step: one host, TLS, stdlib, cache
    untracked.
  - Checked on returned content, not HTTP status.
- **Ground-out and air-out counts:** already in the cached StatsAPI season
  JSON. Extract only; no download.
- **Pulled-air rate:** built from the AAA game records already on disk.

## Execution

- Build on Sonnet from a written plan; Opus reviews every result before the
  user sees it.
- Phase 1 is a separate plan from Phase 2 and must be finished and reviewed
  first, because Phase 2's stats inputs and H-SM/P-SM depend on it.
- Long steps checkpoint per phase (per-phase JSON, skip completed phases, a
  `--force` flag).

## Backlog (the user's ideas, deferred on purpose)

- **Process-change flags:** find pitchers whose pitch mix or approach changed
  sharply, and hitters whose stance or depth of contact changed, in near-real
  time, and flag the changes that seem to drive outcomes. This is a separate
  tool (a watch list, not prospect valuation) with its own design later.
