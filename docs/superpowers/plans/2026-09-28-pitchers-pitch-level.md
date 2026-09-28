# Pitchers Plan P-E: Pitch-Level Stuff Model — Implementation Plan

> Executed inline on Opus at the user's request ("this feels difficult"). The design and the **pre-registered decision rule** are in `docs/superpowers/specs/2026-09-28-pitchers-design.md`, "P-E: the pitch-level stuff model". This plan lists the tasks and checks; the code lives in the files named, each with tests.

**Goal:** Build a pitch-level stuff score, then decide between it and P-C's season-level score, as-of and on identical pitchers, by the rule fixed in the spec. The verdict goes to `cache/stuff_choice_final.json` for P-D.

## Ground rules

- **Where to run:** from `prospects-model/`. Before this plan: 229 pass, 3 skipped.
- **Network:** MLB game records 2020–2022 only, via `fetch_pbp.py` (`statsapi.mlb.com`).
  1. Security audit first.
  2. Then the two-game field check.
  3. Then the bulk run.
- **Long steps are checkpointed:**
  - The download resumes per game.
  - Pitch frames are one `.npz` per level-season; completed ones are skipped unless `--force` is given.
- **`cache/` is never committed.** Commit locally after each task; never push.
- **After the verdict, stop.** Record the result and hand to the user before P-D.

## Tasks

- [ ] **T1 — `fetch_pbp.py` fetches MLB 2020.**
  - A `skip_season(season, sport_id)` helper skips 2020 for the minor leagues only.
  - Add a test.

- [ ] **T2 — Download.**
  1. Run the security audit.
  2. Fetch one 2020 and one 2021 MLB game, and confirm `extension`, `breaks`, `x0`/`z0`, `hitData` and `result.eventType` are present.
  3. Only then: `python fetch_pbp.py --seasons 2020 2021 2022 --levels 1` (background; about 1.5 h; resumable).
  4. Expected on disk: about 900 (2020), about 2,430 (2021) and about 2,430 (2022) games.

- [ ] **T3 — Parser.**
  - `tracking.iter_pitch_events(game)`: per pitch, the pitcher, pitch hand, batter side, type, code, speed, spin, IVB, HB, extension, x0, z0, EV, LA, and the play's event type on the in-play pitch.
  - Add a test.

- [ ] **T4 — `psmodel/pitchlevel.py` frames.**
  - Pitch family, the handedness flip, primary-fastball means, per-pitch features incl. gaps, swing/whiff/in-play flags, and the wOBA value of the result.
  - Output: `season_frame(pitches)` → numpy arrays.
  - Add tests on synthetic pitches.

- [ ] **T5 — `build_pitch_frames.py`.**
  - Covers MLB 2020–26 and AAA 2022–26 → `cache/pitch_frames/{season}_{sport}.npz`, checkpointed, with `--force`.
  - Run it. Sanity: about 700k pitches per full MLB season and a swing rate of about 47%.

- [ ] **T6 — `pitchlevel.py` models.**
  - The xdamage(EV, LA) model.
  - Per-family whiff | swing and damage | contact models trained on MLB seasons ≤ c.
  - Per-pitcher aggregation into `pl_whiff` / `pl_damage`.
  - Add tests on synthetic data.

- [ ] **T7 — `stuff.py` takes a key list** (`_features`, `mlb_rows`, `aaa_rows`), defaulting to the season-level keys so P-C is unchanged. Add a test.

- [ ] **T8 — `pitchlevel_run.py`.**
  1. Adoption on MLB t = 2020–25.
  2. The as-of prospect gate for **both** scores (vantages 2022 and 2023) on identical pitchers.
  3. The paired-bootstrap difference.
  4. The verdict by the pre-registered rule → `cache/pitchlevel_report.txt` and `cache/stuff_choice_final.json`.
  5. Run it, then stop for review.
