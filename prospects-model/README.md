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
