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
