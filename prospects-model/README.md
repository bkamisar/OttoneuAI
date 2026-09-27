# Prospect Value Model

Predicts which minor-league traits produce value in this league's 4x4 scoring.
Design: `../docs/superpowers/specs/2026-09-26-prospect-model-design.md`

## Layout
- `psmodel/` — pipeline modules
- `parity/`  — proves the Python SGP math matches shared.js
- `tests/`   — `python -m unittest discover -s tests -v`
- `cache/`   — raw API pulls (gitignored; never committed)

## Sources
- **MLB StatsAPI** — canonical for all counting and rate stats.
- **Baseball Savant** — expected and tracking metrics ONLY. Never blended with
  StatsAPI for the same quantity (Soto 2026: 477 PA / .278 in StatsAPI vs
  472 / .276 in Savant, because Savant counts tracked PAs).

## Known data notes (measured 2026-09-26)
- **Hitter and pitcher labels are on different SGP scales** (max ~6.6 vs ~3.3).
  Inherited faithfully from shared.js: the pitcher K term largely cancels through
  `ipScale`, which is why the tool splits dollars between hitting and pitching by
  SGP share. Fine while the two are modeled separately; do NOT compare raw SGP
  across types without that split.
- **Pitchers who batted before 2022 appear as `H` rows** (5,290 rows under 100 PA).
  The target builder must assign a prospect's type from his primary role, not
  from whichever rows exist.
- **Two-way players (Ohtani) have one `H` and one `P` row per season**; summing
  them into a player-season is the target builder's job.
- **2020 was 60 games.** Volume floors prorate (`context.season_fraction`) and
  `avg_pa` is a fixed constant, so a shortened season is uniformly ~37% of a full
  one. There was also no MiLB season in 2020.
- **Median pitcher is below replacement** (-0.33), because the replacement cohort
  is defined by `valProxy` and skews to low-inning arms with good ratios (mirrors
  the JS FA baseline). Targets are floored at 0, as `Math.max(0, sgp)` in shared.js.
- **2026 is incomplete** (the season ends 2026-09-27).

## Commands
    python -m unittest discover -s tests -v     # 52 tests (2 live-only skipped)
    PROSPECTS_LIVE=1 python -m unittest tests.test_statsapi -v
    python parity/compare.py                    # MUST pass after any labels.py change
    python build_labels.py                      # writes cache/labels.csv (gitignored)
