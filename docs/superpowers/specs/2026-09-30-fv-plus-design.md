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
