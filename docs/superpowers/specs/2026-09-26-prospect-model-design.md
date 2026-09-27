# Prospect Value Model — Design

**Date:** 2026-09-26
**Status:** Approved in brainstorming; awaiting spec review
**Home:** `prospects-model/` (Python pipeline) + output consumed by `prospects.html`

## Roadmap at a glance (updated 2026-09-27)

| # | Piece | What it is | Status |
|---|---|---|---|
| 1 | **Answer key** | Every MLB season 2015–2026 valued in this league's 4×4 (`build_labels.py`) | ✅ done |
| 2 | **Minor-league data** | Season stats + whiff/CSW (season-level, validated); exit velocity (AAA 2022–26 game records, downloaded) | ✅ gathered |
| 3 | **What predicts value** | First test: does whiff/CSW add signal beyond K%/BB%? (`plans/2026-09-27-whiff-test.md`). Then the exit-velocity bridge, then the full backtest | ⏭ **current** |
| 4 | **Shopping list** | `prospects.html` shows the model's rating vs FanGraphs FV; the gap is the bargain | ⏭ later |

## Goal

Answer a question the generic prospect lists can't: **which minor-league traits
predict value in *this* league's 4×4 scoring (R/HR/OBP/SLG, K/HR9/ERA/WHIP)** —
and surface the prospects whose FanGraphs FV misprices them for that format.

Two deliverables that matter: the **insight** (which traits pay off here, and
where that diverges from conventional prospect valuation) and the **edge list**
(prospects the model rates above their FV-implied price).

## Decisions made in brainstorming

| Decision | Choice | Why |
|---|---|---|
| Target variable | Peak single-season 4×4 value across the **first 4 seasons from debut** | Dynasty-actionable horizon; also maximizes the number of cohorts with complete outcomes (vs. a 5-year window) |
| Training population | **Every MiLB player-season**, stats-driven | Thousands of rows, deep history, no dependency on historical scouting grades |
| Scouting grades | **Deferred, not dropped** | Historical FanGraphs Board availability unconfirmed; the stats model must stand alone |
| Stack | Python + sklearn in `prospects-model/`, output committed for the site | sklearn is the right tool and matches the NFLU workflow; one repo, one push |
| Statcast role | MLB-calibrated **bridge**, plus a provisional AAA overlay | Minors tracking is too recent to fit on directly (see Constraints) |
| Edge metric | model value − existing FV/rank dynasty value | Both already exist; needs no historical grade data |
| History depth | **MiLB snapshots 2016–2025** (~10 years) | The game changed: velocity/K-rate drift, 2023 pitch clock and shift ban, 2021 MiLB contraction. Row count isn't the binding constraint — independent cohort *years* are, and this yields ~6 complete ones (NFLU had 5) |
| Early production | Reported as a **second output**, not treated as bias | The goal is players who produce well *and soon*; a 19-year-old with a 5-year ceiling and a 24-year-old who helps next April must not collapse into one number |
| Stat authority | **StatsAPI canonical** for counting/rate stats; Savant only for expected + tracking metrics | Measured: Soto 2026 is 477 PA / .278 in StatsAPI vs 472 / .276 in Savant. Savant counts tracked PAs. Never blend the two for the same quantity |

## Measured facts (verified 2026-09-26, not assumed)

**Reachability from this machine's shell:**
- **MLB StatsAPI — works.** `statsapi.mlb.com/api/v1/stats`. AAA 2019 returned
  1,665 hitter-seasons with `player.id`, age, level, league and every category
  we score. **The `player.id` is the MLB ID, so MiLB→MLB is an exact join** — no
  fuzzy name matching (NFLU needed a 0.88 cutoff).
- **Baseball Savant — works.** `baseballsavant.mlb.com/leaderboard/...&csv=true`
  returns CSV directly.
- **FanGraphs — 403 Cloudflare challenge.** Must go through Apps Script. Only
  needed for grades/projections, not for the core model.

**Three endpoints that returned confident-looking WRONG data.** Recorded because
each cost a probe and each would have silently corrupted the model:
1. `leaderboard/expected_statistics?...&minors=true` — byte-identical to the
   call without it; 251 MLB rows either way. `minors=true` is a **no-op**.
2. `statcast_search/csv?...&hfLevel=AAA|` — 200 OK, **zero rows**.
3. `statcast-search-minors/csv?...` — 200 OK, 4,215 rows, **but every
   `home_team` is an MLB club**. The path alone doesn't scope to the minors.
> Lesson (third occurrence this project, after ZiPS `season=`): **verify the
> returned rows, not the HTTP status.** Any new endpoint gets a content assertion.

**Minor-league Statcast coverage** (from Savant's own page text): tracking since
2021 for certain levels/parks — *all* Triple-A from **2023**, plus Pacific Coast
League and Charlotte home games for **2022**, and Florida State League
(Single-A) from **2021**. Level values are `A` and `AAA`.

**Backtest feasibility for AAA Statcast** (measured): of **394** AAA hitters
with 200+ PA in 2023, **120 (30%)** reached MLB with 100+ PA in 2024–26,
averaging **2.05** seasons of MLB data. Enough for a hypothesis check; not
enough for model selection.

**Source depth** (measured):

| Source | Earliest usable | Volume |
|---|---|---|
| StatsAPI AAA | 2005 or earlier | 1,428–1,665 player-seasons/yr; ~500 with 200+ PA |
| StatsAPI AAA 2023+ | — | ~930/yr, ~390 qualified (2021 MiLB contraction) |
| Savant Statcast | **2015** (2014 returns 0 rows) | ~960–990 batters/yr |

**Statcast metric availability tiers** (measured on `leaderboard/custom`):
- **2015+ (deep, ~11k MLB player-seasons — calibratable):** `xba`, `xslg`,
  `xwoba`, `xobp`, `xiso`, `avg_best_speed`, `barrel_batted_rate`,
  `hard_hit_percent`, `sweet_spot_percent`, `k_percent`, `bb_percent`,
  `whiff_percent`, `swing_percent`, GB/FB/LD/PU%, `sprint_speed`
- **2023+ only (bat tracking — provisional on both ends):** `avg_swing_speed`,
  `attack_angle`, and the squared-up / swing-length family
- Raw avg and max exit velocity, squared-up rate and swing length are **not on
  the `custom` endpoint** under those names — they live on the dedicated
  `bat-tracking` and `exit_velocity` leaderboards, joined by `player_id`.
- **To investigate before using 2026 as a training year:** Savant's 2026 file
  returns 662 rows vs ~990 in prior seasons.

**Spot-checks passed** (user-verified 2026-09-26): Soto MLB 2026, Bobby Witt Jr.
2021 AA *and* AAA (age 21, two levels in one season — exactly the multi-level
case the features must handle), Nate Pearson 2019 AA, Savant Soto 2026 and
Trout 2019.
> A name-substring search for "Witt" during probing matched **Jantzen Witte**, a
> 31-year-old in Tacoma. Live proof of why the join is on `player.id` only.

## Constraints this creates

- Minors Statcast spans ~3 seasons at AAA only. Fitting a prospect model on it
  would learn **"who produces early,"** not "who peaks high" — biased toward
  older MLB-ready AAA bats and against young high-upside players. Any such
  result must say so.
- **Unresolved:** the correct level parameter for the minors Statcast search.
  `hfLevel` is not it. Resolve by capturing the real request in the browser
  (network panel) before building the Savant minors fetcher.

## Architecture — four sub-projects

Only **#1 is in scope for the first implementation plan.** The rest are designed
here so #1 doesn't paint them into a corner.

### 1. Label builder (first plan)

Every historical MLB player-season scored as its value in *this* league.

**Label math** — 4×4 SGP above replacement:
- **Denominators held fixed** at this league's current values. They encode our
  league's competitive spread, which is a league property, not a season property.
- **Replacement level recomputed per season** from that season's MLB pool, by
  rank (roster-slot count × 12 teams), mirroring the FA-cohort logic in
  `calcReplacementLevels`.
- Fixed denominators + per-season replacement is what makes 2019 and 2024
  comparable: era inflation is absorbed into replacement rather than making old
  seasons look better.
- Dollars only for readability; SGP is the modeling unit.

**Target construction:**
- `debut_season` = first MLB season with ≥1 PA (hitters) or ≥1 IP (pitchers).
- `window` = `debut_season` … `debut_season + 3` (4 calendar seasons).
- A season is **peak-eligible** at ≥100 PA / ≥25 IP. Below that, low volume
  already self-penalizes in the SGP math (counting stats stay small, rate stats
  are weighted by PA/IP), so the floor only blocks small-sample rate flukes.
- `target` = max label over peak-eligible seasons in the window; **0 if none**.
- `completeness_weight` = (window seasons already played) / 4, floor 0.25 —
  NFLU's class-completeness weighting.

**Labeling a non-arrival (subtle, gets this wrong easily):** a MiLB season row is
labeled `0` only if **≥5 seasons have elapsed since the snapshot with no debut**.
A 2024 MiLB player who hasn't debuted is **unknown and excluded**, not a zero.
Conflating "hasn't yet" with "never will" would poison recent cohorts.

**Validation gate (build this first, before any modeling):** a parity harness
feeding *identical stat lines* to both the Python label builder and the JS
`calculateAllValues` via a node harness, then correlating. Target ≥0.98; a real
gap means the label is wrong and everything downstream inherits it. Note the
comparison must use the same inputs — the JS tool normally runs on Steamer
projections, so feeding it actuals is what isolates math differences from input
differences.

### 2. Feature builder

Per MiLB player-season, from StatsAPI. All candidates; the sweep decides.
- **Age, and age relative to level average** (classically the strongest signal)
- **Plate discipline:** K%, BB%, BB/K — expected to matter more here than in an
  AVG league, because OBP is scored and AVG isn't
- **Power:** ISO, HR/PA, SLG
- **Playing time / trajectory:** PA or IP, repeat-level flag, multi-level
  season, year-over-year deltas
- **Speed and SB: included as candidates and allowed to fail.** No SB category
  exists in this league, so whether speed still pays through runs scored is a
  *finding*, not an assumption.
- Pitchers: K%, BB%, K−BB%, HR/9, ERA, WHIP, role (GS share), level, age

**Normalize within level-season.** A prospect's K% is expressed relative to his
own league-year average, not raw. This handles era drift directly (velocity and
K-rate creep, the 2023 rule changes) and keeps the option of extending history
backward cheap if the model turns out data-starved.

**Two structural facts the feature builder must handle explicitly:**
- **2020 has no minor-league season.** Snapshot years are 2016–2019 and
  2021–2025 — nine usable years with a hole. Any year-over-year delta must treat
  a 2021 player's previous season as **2019**, not "missing" and not 2020.
- **Multi-level seasons are the norm, not the exception.** Witt Jr. 2021 is 279
  PA at AA *and* 285 at AAA. A player-season is therefore (player × season ×
  level) rows that must be combined deliberately — highest level reached,
  weighted blend, or both as separate features — never silently deduplicated.

**Forbidden features (leakage):** anything knowable only later, e.g. "highest
level ever reached." Only what was true **through the snapshot season**.

### 3. Model and backtest

- Separate models for **hitters and pitchers**.
- Compare Ridge / ElasticNet / GBM / RandomForest by cross-validated score,
  as NFLU does; prefer the simpler model on ties.
- **Walk-forward by cohort year**, three vantage points, **2-of-3 adoption
  rule** — no change adopted on one lucky year.
- **Phantom-feature guard:** assert every declared feature exists in the fitted
  matrix. NFLU shipped two documented-but-nonexistent features for months;
  the assert is free.
- **Report top-N precision** ("of the top 20 flagged, how many became useful"),
  not just R². That matches how the list is actually used.

**Second output: time to contribution.** Alongside peak value, predict how soon
a prospect reaches a peak-eligible season. The league is dynasty but the planning
horizon is not 5–10 years — the goal is players who produce well *and soon*, so a
model that favors quick contributors is measuring something wanted, not a bias to
correct. Keeping it a separate number is what stops a distant high ceiling and an
imminent solid regular from collapsing into one score.

**Interactions (user, 2026-09-27): 3a/3b are screens, not final cuts.** A feature
whose value is conditional — "whiffs a lot, but elite exit velocity → actually
great" — can average to zero in an additive model and be wrongly dropped. That
profile matters MORE in this league: with no AVG, strikeouts hurt only through
OBP, while the power feeds HR/SLG/R, so generic lists likely undervalue it. So:
3a compares under ridge AND gradient boosting (adopt if either wins) and prints a
whiff × power grid; **3b is a joint model of contact + contact quality (whiff,
EV, barrel, their interactions) on MLB data** — the only place whiff, EV and
outcomes coexist for ten years — not EV alone; 3c's tree models re-test all
families jointly.

**3b design, hitters first (decided 2026-09-27).** Sequence: hitters, then
pitchers reusing the pipeline.
- **MLB history from Savant leaderboards, not a game crawl.** The custom
  leaderboard populates all 27 hitter metrics the bridge needs back to 2015
  (EV avg, best-speed EV, hard-hit %, barrel %, sweet-spot %, LA, whiff %, swing %,
  chase `oz_swing_percent`, zone/out-of-zone contact, pull/center/oppo %,
  GB/LD/FB/PU %, xwOBA family, K %, BB %, sprint speed), and the exit-velocity
  leaderboard adds max EV and distance. ~29,000 MLB games avoided.
- **One MLB season (2024, ~2,430 games) is downloaded only to prove our metric
  code reproduces Savant's published numbers** (like whiff at r = 0.9997). Uncertain
  definitions — foul tip as whiff, bunts as swings/batted balls, pull threshold,
  the barrel window — are tried as variants; the variant that matches Savant wins.
  Only after this parity passes are AAA metrics computed and trusted.
  **Result: passed on 18 metrics; pull/center/oppo dropped** — see "Tracking
  parity result" below.
- Lost by skipping the crawl: metrics Savant doesn't publish (e.g. pulled
  fly-ball rate). Recoverable later by extending the fetcher; not a one-way door.
- Game-record encoding (verified on MLB and AAA 2024): pitch result in
  `details.code` (B, *B, C, S, W, F, T, L, X/D/E in play, H…); EV only on in-play
  pitches (X/D/E), never fouls; `hitData.trajectory` labels batted-ball type
  including `bunt_grounder`; `pitchData.zone` 1–9 in / 11–14 out on every pitch;
  `matchup.batSide` per PA.
- Two plans: (A) extraction + Savant parity + AAA metrics + Savant history pull;
  (B) the bridge model (next-season value on MLB, AAA→MLB translation from
  same-season two-level players 2023–26, validation on 2022–23 AAA cohorts,
  grouped importance, interaction report) — designed after A's parity results.

**3c requirement — open-ended interaction search (user, 2026-09-27).** Not just
whiff × EV: any stat × any stat (e.g. walk rate × power, age × level, velocity ×
command) may be "the ticket." Tree models search all pairs and triples without
enumeration. The constraint is sample size — ~30 features give 435 pairs and
thousands of triples against ~150–300 players who became starters — so:
1. search freely (trees, shallow and regularized);
2. an interaction counts only if it improves out-of-sample predictions in the
   walk-forward backtest under the 2-of-3 rule;
3. deliver a **ranked interaction report**: pairwise interaction strength (e.g.
   SHAP interaction values or Friedman's H) for the top pairs, each flagged by
   whether it replicates across backtest years. Unreplicated patterns are
   labeled hypotheses, not findings.
EV-involving interactions can only be learned where EV exists (MLB 2015+, AAA
2022+), i.e. in the bridge; the rest on the full 2016–2025 MiLB data.

**Statcast bridge (the well-powered use):** learn which tracking metrics predict
4×4 value from **MLB Statcast 2015+** (thousands of player-seasons), then apply
that relationship to a prospect's AAA readings — rather than re-learning it from
120 players. **Comparability is testable, not assumed:** many players have both
AAA and MLB readings in the same season, so measure the offset directly. The
thin AAA cohorts then serve as a sanity check on the bridge, not its foundation.

### 4. Tool surface

Extend **`prospects.html`** (grades and dynasty values already render there):
- Model's predicted value, as plain-language odds rather than false precision.
- **Edge column** = model value − existing FV/rank dynasty value
  (`PROSPECT_RANK_CURVE` / `FV_DYNASTY_FLOORS` in `shared.js` are the consensus
  price). Sortable — this is the shopping list.
- **Competence flag:** say nothing rather than give a confident number for a
  19-year-old with 80 rookie-ball PA or an international signee with no record.
- Statcast overlay visibly labeled provisional until it earns adoption.

Output path: `data/prospect_model.json`, registered in `REPO_FILES` so
`autoLoadFromRepo` picks it up like every other feed.

## Operational and security decisions

- **Pinned dependencies, minimal set, PyPI only.** The Python dependency tree is
  a larger real exposure than any of the HTTP traffic (which is unauthenticated,
  read-only GETs to MLB-operated hosts carrying no credentials and no personal
  data).
- **Fetched content is data, never instructions.** Real parsers, never
  `eval`/`exec`. The site's `textContent`-only rendering invariant holds for the
  new columns.
- **CSV injection:** sanitize leading `= + - @` on any CSV written for spreadsheet use.
- **Cache to disk and throttle.** Never re-fetch what's already local; bulk
  multi-season pulls are the one way to get the IP blocked.
- **Raw pulls are gitignored; only derived artifacts are committed.** This repo
  is public and MLB's terms attach to their content — committing our computed
  labels and features is a different act from mirroring their database.
- Refresh is a **local script run plus a commit**, not an Apps Script trigger.

## Directory layout

```
prospects-model/
  README.md
  requirements.txt      # pinned
  fetch/                # StatsAPI + Savant clients, disk cache, content asserts
  build/                # labels.py, features.py
  model/                # train.py, backtest.py, guards.py
  parity/               # label vs JS calculateAllValues harness
  cache/                # gitignored raw pulls
```

## Sub-project 2 — what the data actually offers (probed 2026-09-26)

**Pitch-level data comes from StatsAPI play-by-play** (`/api/v1/game/{pk}/playByPlay`),
one game per request, clean JSON, joined on the same `player.id`.

| Feature family | Levels | Years |
|---|---|---|
| Season stats (K%, BB%, ISO, OBP, SLG, SB, GO/AO, pitches/PA, age) | all four | 2016–25 |
| **Pitch-result family** — whiff, swinging-strike, swing, contact, called-strike, foul rate; **CSW%** for pitchers | **all four** | **2016–25** |
| Ball tracking — exit velo, launch angle, distance; pitch velo, spin, extension, movement, zone | **AAA 2023+, Florida State League (Single-A) 2021+** | recent only |
| Bat speed, squared-up | none in MiLB | — |

- Pitch descriptions ("Swinging Strike", "Called Strike", "Foul"…) exist for every
  pitch at every level back to 2016, with no tracking hardware required. Verified on
  sampled games at AA, High-A, Single-A and AAA in 2016, 2018 and 2024.
- **Chase rate is not available** before tracking: it needs pitch location (`zone`).
- AA and High-A have **no** ball tracking in any year sampled.
- `?fields=` cuts payloads **5.5×** (591 KB → 108 KB) with identical content.
- Full scope is **~80,700 games** (2016–19, 2021–25, four levels): ~22 h at 1 req/s.

**The Mexican League contaminates AAA before 2021.** In 2019, 162 of 510 "AAA"
hitters with 200+ PA (32%) were in the Mexican League, median age **29** vs 26 in
the affiliated leagues, and 993 of 3,192 AAA games. Left in, it inflates the AAA
age baseline and drags every level-normalized rate toward an older, hitter-friendly
league. **Exclude league id 125 everywhere** — at fetch time and in season stats.
> Correction to an earlier claim in this doc: the post-2021 drop in AAA volume is
> mostly the Mexican League leaving the AAA classification, not the MiLB contraction.
> The affiliated qualified pool went 348 → 380, essentially flat.

**Leagues changed levels in 2021.** The Florida State League was High-A (sportId 13)
in 2019 and Single-A (sportId 14) from 2021, and every league was renamed. So
normalize **within (sportId, season)**, never within a league name across years.
AA, High-A and Single-A contain only affiliated leagues.

**REVISED (same day): the pitch-result family comes from season stats, not game logs.**
StatsAPI `stats=seasonAdvanced` carries `totalSwings` and `swingAndMisses` per
player-season for hitters AND pitchers (pitchers also get `whiffPercentage` and
`strikePercentage`) at every MiLB level back to at least 2016. Validated against an
independent source: MLB 2024 whiff rate from `seasonAdvanced` vs Savant's
`whiff_percent` correlates **0.9997** across 397 hitters (mean gap 0.10 pts); swing
rate 0.9974 (0.22 pts). So whiff, swing, swinging-strike and contact rates cost a
few dozen requests covering **all four levels and all nine seasons**, instead of
17,600 game downloads covering two levels and four seasons. The backfill was
stopped after 1,375 games (atomic writes held: 0 temp files, 0 unreadable).
`seasonAdvanced` returns exactly 1,000 rows per page, so it must be paginated.

**CSW% is ALSO derivable from season stats — no download.** Every swing is a
strike, so `called = strikes − totalSwings`, joining basic `season` (which has raw
`strikes` and `numberOfPitches` for pitchers) to `seasonAdvanced` (`totalSwings`,
`swingAndMisses`). Validated against the pitch-by-pitch answer key in the 1,375
downloaded 2016 AA games: for pitchers with ≥98% of their games downloaded,
derived CSW vs counted CSW **r = 0.994**, n = 39 (r = 0.885 across all 293, the gap
being pure partial-coverage sampling noise). Derived CSW runs a **constant +1.0 pt
high** (mean abs gap ≈ signed bias), almost certainly bunt attempts counted as
strikes but not swings. Within-(sportId, season) normalization removes a constant
offset, so it is documented, not corrected. Note the pitcher pitch count lives in
basic `season`, NOT `seasonAdvanced` — the first probe silently matched zero
pitchers for that reason.

**Exit velocity / launch angle still need play-by-play — `metricAverages` is trap #5.**
`stats=metricAverages&metrics=launchSpeed` returns per-player averages with a
`maxValue`, which looked ideal. But it **ignores `sportId`**: Aaron Judge appears in
the "AAA", "AA" and "Single-A" results for every year, AAA 2019 (no tracking)
returns 1,985 players, and AA 2024 (no tracking) is byte-for-byte AAA 2024. It is
major-league data regardless of the level requested. Caught only by checking that
a known MLB-only player was absent.

So the **only** download still required is **ball tracking**, scoped to where it
exists: AAA 2023–2026, the Florida State League 2021–2025, and PCL + Charlotte home
games in 2022. The fetcher needs a league-inclusion filter so it downloads only
tracked leagues (the FSL is roughly a third of Single-A).
> Lesson: check every stat TYPE an API offers before building a per-game crawl.
> The first season endpoint lacked the field; a sibling endpoint had it.

**Original decision (superseded by the above):** prove the pitch-result family before paying for the full backfill.
First vertical slice = **AA + affiliated AAA, 2016–2019 (~17,600 games, ~5 h)**,
extracting the whole pitch-result family, then testing whether it predicts MLB value
beyond K% and BB%. The skeptical hypothesis is that whiff rate is a noisier K%, since
both come from the same plate appearances. AAA is included because it is where
near-term targets sit and because its players debut sooner, so their outcome windows
are more complete. The test needs the feature builder, the label join and two simple
models — a small end-to-end slice of sub-projects 2 and 3 — so the pipeline gets
built either way; only the 22-hour backfill depends on the result.

## Whiff test result (run 2026-09-27)

AA + affiliated AAA, 2016–2019 seasons; MLB outcomes through 2026. 5-fold
player-grouped CV, 10 seeded shuffles, ridge and gradient boosting.

- **Hitters: ADOPTED (via ridge, 9/10 shuffles), not via gbm (4/10).** 3,088
  rows / 1,510 players, 147 (9.7%) reached starter-quality (top-144-equivalent
  peak, ≥0.61 SGP). Whiff family improved rank accuracy (Spearman 0.462→0.468)
  and top-50 hit rate (61.6%→63.6%).
  - Standardized ridge weights: `whiff −0.225`, `swstr +0.216`, `slg +0.151`,
    `age −0.130`, `hr_pa +0.121`, `iso −0.096`, `bb +0.088`. **Note the sign
    split between `whiff` (misses/swing) and `swstr` (misses/pitch) — these are
    correlated by construction (`swstr ≈ whiff × swing_rate`), a multicollinearity
    artifact to watch in 3c, not necessarily two independent effects.**
  - Interaction grid (whiff × ISO, split at medians) — the user's exact
    question, answered directly: low-ISO/low-whiff 4.4% (n=981) →
    low-ISO/high-whiff 2.5% (n=563) → high-ISO/high-whiff 14.0% (n=981) →
    high-ISO/low-whiff 19.2% (n=563). Power still wins even with more whiffs,
    but low-whiff sluggers do best; whiffing without power is the worst cell.
- **Pitchers: NOT adopted** under either model (max 3/10 shuffles). All
  whiff-family coefficients near zero (`whiff −0.005`, `csw −0.002`,
  `swstr +0.006`). K%/BB%/ERA/WHIP already appear to capture what whiff-derived
  stats would add, for pitchers, in this cohort.
- Full report: `prospects-model/cache/whiff_test_report.txt` (gitignored,
  regenerate with `python whiff_test.py`).
- **Screen, not final cut** — 3c re-tests every family jointly with the full
  interaction search (see below); this only decided sub-project 2's next step.

**Critical re-read (Opus, 2026-09-27) — corrections to the first write-up:**
1. **Hitter gain is real but small.** Player-level bootstrap (20 resamples):
   Spearman gain +0.0064, sd 0.0049, positive in 95%. The fold-shuffle sd
   (0.001) understated uncertainty. Top-50 gain ≈ one player. Cause: in MiLB,
   `r(whiff, K%) = 0.90` — mostly redundant with strikeout rate.
2. **The per-feature trait ranking is NOT interpretable.** Near-duplicate
   features: `r(whiff, swstr) = 0.93`, `r(iso, slg) = 0.90`,
   `r(iso, hr_pa) = 0.93`. Ridge splits credit arbitrarily among them, which is
   why it reported opposite signs for whiff/swstr and iso/slg. **3b and 3c must
   report importance by feature GROUP** (contact, power, discipline, age/level —
   drop-group-and-refit, or one representative per correlated cluster), never by
   single ridge coefficient.
3. **The whiff × ISO grid is suggestive, not proof:** whiffing costs sluggers
   proportionally less (−27% vs −43%), but gbm did not confirm an interaction and
   median splits are crude.
4. **gbm underperformed ridge** for both types (hitters 0.419 vs 0.462,
   pitchers 0.218 vs 0.282). At ~1,500 players, trees are data-hungry; in 3c they
   must earn their place against a linear baseline, not be assumed better.
5. **Reliever-mislabeling hypothesis checked and REJECTED.** Elite relief
   seasons clear the pitcher bar (Clase 2024 +1.25, E. Díaz 2022 +0.96, D. Williams
   2023 +0.88, Hader 2023 +0.77), and **61% of starter-quality pitcher seasons
   are <90 IP**. Pitcher prediction is weak because MiLB box-score stats carry
   little signal (ridge alpha 162 vs 2.3 for hitters — heavy shrinkage), not
   because the labels are wrong. **Pitchers are where tracking data (velocity,
   spin, movement, extension) has the most headroom.**

## Tracking parity result (run 2026-09-27)

`parity_tracking.py` on all 2,430 games of 2024 MLB vs Savant's 2024 leaderboards
(398–405 qualified hitters): **PASS on 18 metrics**, every one r ≥ 0.989 (EV avg
0.9999, max EV 1.0000, LA avg 0.9996, whiff 1.0000, swing 1.0000, GB/LD/FB/PU
≥ 0.9993, sweet spot 0.9911, barrel 0.9890 vs its 0.95 bar, chase 0.9942, oz
contact 0.9894). Chosen variant: **foul tip counts as a whiff; bunt attempts
count as swings.** Report: `cache/tracking_parity_report.txt`; definitions:
`cache/tracking_definitions.json` (both gitignored; rerun to regenerate).

Definitions the first run got wrong, each settled by the data:
1. **Bunts are split by metric.** Savant keeps bunted balls in batted-ball
   *rates and types* (GB %, hard-hit %, distance, barrel/sweet-spot denominators)
   but leaves them out of the **EV and LA averages** (and best-speed). Counting
   them in the EV average biased it −0.5 mph (r 0.958); dropping them from the
   rates cost GB % 0.9995 → 0.993. Bunts average 34 mph vs 89 mph for swings.
2. **Launch angle in game records is whole degrees** (100% of 123,794 batted
   balls), so a ball at exactly 8° or 32° is only half inside Savant's 8–32
   sweet-spot window. Half-weighting the boundaries took sweet spot from
   r 0.982 / bias +1.4 pts to r 0.991 / bias +0.1.
3. **Pull / straightaway / opposite % were dropped — not reproducible from game
   records.** Game records carry only the Gameday *charted* hit location
   (`hitData.coordinates`; the full hitData key set is launchSpeed, launchAngle,
   totalDistance, trajectory, hardness, location, coordinates), while Savant's
   direction evidently comes from tracked launch direction. Evidence it is a
   ceiling, not a bug: a threshold sweep (5–40°) moves bias through zero but
   straightaway r never passes 0.76; R and L hitters fail identically (no sign
   bug); fitting home-plate origin plus separate air/ground thresholds (4
   parameters) tops out at straightaway r 0.87 / pull 0.96, confirmed
   out-of-sample on split halves. Mixing Savant's MLB spray with our AAA spray
   would build a +5-pt definitional gap into the bridge. **If plan B needs spray**,
   the consistent route is our coordinate-based version at both levels, which
   needs MLB game records 2015–2025 (~27k games, ~7.5 h background download).

Remaining biases (e.g. chase +1.1 pts, distance +1.4 ft) are constant method
offsets; the bridge's AAA→MLB translation, learned from same-season two-level
players, absorbs a constant. The gate is on r for that reason.

## Tracking tables built (2026-09-27, Task 5)

`build_tracking.py` on the parity-chosen variant (foul tip = whiff, bunts
count as swings): **3,911 AAA hitter-seasons** (2022 PCL-only 336, 2023–2026
~865–909 each) and **9,835 MLB hitter-seasons** (2015–2026 from Savant, all
12 present and distinct) → `cache/aaa_tracking.csv` / `cache/mlb_tracking.csv`
(gitignored). Hitters with 100+ batted balls: AAA 150 (2022) / 445–456
(2023–26). Median avg exit velocity 87.7–89.9 mph across both levels and all
years, AAA at or slightly below MLB as expected; 2020 has no 300+-PA median
(60-game season). **Plan A is complete.** Next: design plan B (the bridge
model) on Opus.

## The FanGraphs ↔ StatsAPI id gap (found 2026-09-26)

`roster.csv` carries `FG MajorLeagueID` and `FG MinorLeagueID` (494 and 522 of
526 rows populated), but these are **FanGraphs' own ids, not MLBAM**: Soto is
`20123` there against `665742` in StatsAPI. So there is **no free bridge** from
the FanGraphs side (Board grades, `prospects.csv`, Ottoneu rosters) to StatsAPI.

Sub-project 1 is unaffected — it is entirely StatsAPI with exact id joins. But
the **tool surface** and the **grades phase** both need this mapping, and the
fallback is name matching, which already produced a live failure during design
(a "Witt" substring matched Jantzen Witte, a 31-year-old in Tacoma).

**Cheapest possible fix, to check first:** whether the Board payload carries an
MLBAM id. `probeBoardShape` in Apps Script already logs every `dataScout` key —
if one is `xMLBAMID` or equivalent, the bridge is exact and free for precisely
the population we care about. Check this before building any name matcher.

Reusable pieces already in the repo, for when that work happens:
- `normalizeName` (shared.js) — accent folding and punctuation stripping, the
  right starting point for any name fallback.
- `PROSPECT_RANK_CURVE`, `FV_DYNASTY_FLOORS`, `prospectDynastyValue` — the
  consensus FV→dollars mapping that the edge metric subtracts against.
- `computeContractHorizon` / `holdHorizon` — turns a predicted value into
  surplus under Ottoneu's +$2/+$4 salary escalation.

## Deferred (recorded so it isn't silently lost)

- **Scouting grades as features** — needs historical FanGraphs Board data;
  probe whether the API serves past seasons (requires the `fetchBoard` function,
  which lives only in the Apps Script project, not this repo).
- **MLB buy-low/sell-high model** — same label engine, Statcast-rich, deep
  history. Deliberately second; prospects are the stated priority.
- **`MODEL.md` §1 is stale** — still lists Y1/Y2 projections and `prospects.csv`
  as manual uploads; both were automated in Sept 2026. Fix alongside this work.

## Open questions for the plan

1. **The minors Statcast level parameter.** `hfLevel` is not it; resolve by
   capturing the real request from the browser network panel.
2. **Savant 2026 returns 662 rows vs ~990** in prior seasons — understand before
   using 2026 as a training year.
3. Exact roster-slot counts for the rank-based replacement level per season —
   should mirror this league's lineup structure.
4. Correct Savant field names for raw/max exit velocity and the squared-up
   family on the `bat-tracking` and `exit_velocity` leaderboards.

## Historical scouting grades — BLOCKED at the source (tested 2026-09-26)

`probeBoardSeasons` run from Apps Script returned **HTTP 403 with a Cloudflare
"Just a moment..." challenge for every season tried (2026, 2025, 2022, 2019)**.
So the question below is not merely unanswered — the endpoint is unreachable.

**The block is selective.** `/api/projections` still works from the same script
(hitting and pitching projections pulled 2026-09-25), while
`/api/prospects/board/prospects-list-combined` is challenged. It last succeeded
on **2026-08-24**, which is exactly when `data/prospects.csv` stopped updating —
so that file is frozen at the August snapshot, and `updateProspects` would now
fail if triggered.

**It fails safe:** `fetchBoard` throws on any non-200, so `updateProspects` dies
before `pushFile` and no challenge page can overwrite good data.

**Consequences:**
- Grades history for training is not obtainable via the API. If the grades phase
  is ever wanted, the path is **manual export from the website** (which is where
  `prospects.csv` originally came from) for whatever seasons the UI exposes.
- Current in-app grades sit at the 2026-08-24 snapshot. Acceptable — FVs move
  slowly — but it should be a known number, not a surprise.
- Do **not** work around the challenge with logged-in session cookies. Fragile,
  and circumventing an explicit block is categorically different from using a
  public endpoint.
- Worth a periodic retry; Cloudflare rules change.

**Unblocked path (user, 2026-09-27):** historical Board ratings can be exported
manually from the website. That enables testing FV and tool grades as features in
the full model (3c) and measuring the edge directly. When the time comes, ask for
the seasons matching the training cohorts (likely 2016–2019, plus the current
board), and check whether the export carries an MLB player id; name-only joins
need care (Witt → Witte).

This is why grades were scoped as deferred and non-blocking. Sub-project 1 is
unaffected: it is entirely MLB StatsAPI.

## The original probe rationale (superseded by the 403 above)

The Board URL (from `fetchBoard`, Apps Script) carries
`season=2026&seasonend=2026&draft=2026prospect&quickleaderboard=2026all`.
Those are exactly the parameters a historical probe would vary. Given the
`season=` no-op precedent with ZiPS, the probe must **assert that returned FVs
and player names actually differ by season** rather than trusting HTTP 200.
If history exists, grades become a testable feature family on the same cohorts.
