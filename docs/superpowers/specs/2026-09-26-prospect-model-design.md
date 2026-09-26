# Prospect Value Model — Design

**Date:** 2026-09-26
**Status:** Approved in brainstorming; awaiting spec review
**Home:** `prospects-model/` (Python pipeline) + output consumed by `prospects.html`

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

## Deferred (recorded so it isn't silently lost)

- **Scouting grades as features** — needs historical FanGraphs Board data;
  probe whether the API serves past seasons (requires the `fetchBoard` function,
  which lives only in the Apps Script project, not this repo).
- **MLB buy-low/sell-high model** — same label engine, Statcast-rich, deep
  history. Deliberately second; prospects are the stated priority.
- **`MODEL.md` §1 is stale** — still lists Y1/Y2 projections and `prospects.csv`
  as manual uploads; both were automated in Sept 2026. Fix alongside this work.

## Open questions for the plan

1. How far back does StatsAPI MiLB coverage actually go with usable stat lines?
   (Verify at build time; assumed ~2006+.)
2. The minors Statcast level parameter (above).
3. Exact roster-slot counts to use for the rank-based replacement level per
   season — should mirror this league's lineup structure.
