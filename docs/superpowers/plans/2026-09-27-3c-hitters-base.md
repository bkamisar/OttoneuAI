# 3c-hitters Plan A: Data + As-Of Base-Model Backtests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minor-league hitter base model's data (2012–2026, four levels), its two as-of targets, and a walk-forward harness that trains only on what was known at each vantage year. Then run the backtests that decide model type, which feature groups matter, and which interactions replicate, for both outputs.

**Architecture:** `psmodel/cohorts.py` loads and assembles hitter rows. `psmodel/asof.py` defines the targets and when each answer became known. `psmodel/walkforward.py` is the vantage-year harness: isolation, 2024 seal, adoption rules, calibration and interactions. `model3c_base.py` runs everything and writes the report plus `cache/model3c_choice.json` for plan B. The tracking layer, the sealed 2024 check and the ratings file are **plan B**.

**Tech Stack:** Python 3.14 stdlib + numpy, scipy, sklearn (already used by `evaluate.py`). Tests: stdlib `unittest`. Host: `statsapi.mlb.com` only. Nothing new installed.

**Spec:** `docs/superpowers/specs/2026-09-27-3c-hitters-design.md`.

---

## Context the implementer needs

- Run from `prospects-model/`. Tests: `python -m unittest discover -s tests` (**134 pass, 3 live-only skipped** before this plan).
- **The as-of rule is the point of this plan.** A backtest at vantage V trains only on cohorts whose answer was known by V: rating = best season in Y+1…Y+4, known once Y+4 ≤ V; soon = starter-quality season in Y+1…Y+2, known once Y+2 ≤ V. The useful bar is computed from MLB seasons ≤ V. Test-cohort players are removed from training. **2024 is sealed**: the harness refuses it unless explicitly unsealed, and nothing in plan A unseals it.
- **Existing pieces:** `milb.season_rows(season, sport_id, group)` → combined player rows (Mexican League excluded) with `swings`/`whiffs` from `seasonAdvanced`; `features.hitter_features(row)`; `features.standardize_within(rows, keys)` z-scores within `(sport_id, season)`; `dataset.load_labels(path)` → `{(player_id, type): [{season, value, pa, ip}]}`; `dataset.useful_threshold(labels, "H", first, last)`; `evaluate._model(kind)` (ridge/gbm regressors); `evaluate.guard_features(rows, keys)`; `interactions.top_pairs(model, X, keys, n)`; `http.cache_path(url, suffix)` and `http.CACHE_DIR`.
- **`http.fetch_text` never refetches a cached URL.** That's why the 2026 MLB labels need a deliberate refresh (Task 2).
- **Security posture (user requirement):** run this audit before every network step:

```bash
tasklist 2>/dev/null | grep -i python || echo "no stray python"
grep -rhoE "https?://[a-zA-Z0-9.-]+" psmodel/*.py *.py | sort -u
grep -rniE "api[_-]?key|password|token|secret|authorization" psmodel/*.py *.py || echo "no credentials"
git ls-files cache | wc -l
```

Expected: no stray python; only `https://baseballsavant.mlb.com` and `https://statsapi.mlb.com`; no credentials; `0`.
- **No bulk downloads.** Total network in this plan is about 250 small StatsAPI requests (season totals), and the HTTP cache makes every rerun resume.
- Commits are local only; end each message with `Co-Authored-By: <current model> <noreply@anthropic.com>`. The user pushes via GitHub Desktop.

## File map

| File | Change | Responsibility |
|---|---|---|
| `psmodel/statsapi.py` | Modify | `season_url()` (shared URL builder), `invalidate_season()` |
| `build_labels.py` | Modify | Labels from 2013; `--refresh SEASON` |
| `psmodel/features.py` | Modify | `_ratio` returns None when the numerator is missing |
| `psmodel/milb.py` | Modify | `season_rows(..., advanced=True)` |
| `psmodel/cohorts.py` | Create | Constants, MLB PA history, MiLB loading, row building, feature groups |
| `psmodel/asof.py` | Create | Targets, when they're known, the as-of useful bar |
| `psmodel/walkforward.py` | Create | Vantage frames, fit/predict, metrics, adoption, model choice, group importance, calibration, interactions |
| `pull_3c_data.py` | Create | Pulls all inputs into the cache and prints counts |
| `model3c_base.py` | Create | Runs the backtests and writes the report + choice JSON |
| `tests/test_statsapi_invalidate.py`, `test_3c_inputs.py`, `test_cohorts.py`, `test_asof.py`, `test_walkforward.py` | Create | Unit tests |

---

### Task 1: Probe — does minor-league swing data exist before 2016? (no code committed)

- [ ] **Step 1: Security audit** (commands above).
- [ ] **Step 2: Probe** (about 20 requests; the whiff test already cached 2016–2019 AA/AAA):

```bash
python - <<'EOF'
from psmodel import http, statsapi
for season in (2012, 2014, 2015):
    for sid in (11, 12, 13, 14):
        n_basic = len(statsapi.season_stats(season, "hitting", sid))
        try:
            adv = statsapi.season_advanced(season, "hitting", sid)
            swings = sum(v["swings"] for v in adv.values())
            print(season, sid, f"basic rows {n_basic}, advanced players {len(adv)}, total swings {swings}")
        except http.DataError as exc:
            print(season, sid, f"basic rows {n_basic}, advanced: NONE ({exc})")
EOF
```

- [ ] **Step 3: Decide `WHIFF_FIRST`.** If every probed level-season has advanced players with swings > 0, set `WHIFF_FIRST = 2012` in Task 4. Otherwise use `WHIFF_FIRST = 2016`, and tell the user the whiff features will be judged only at the 2021 and 2022 rating vantages (the spec anticipates this). If any `basic rows` count is 0, stop and report: that level didn't exist or its sportId differs in that year.

---

### Task 2: Labels from 2013, and a deliberate 2026 refresh

**Files:** Modify `psmodel/statsapi.py`, `build_labels.py`; Create `tests/test_statsapi_invalidate.py`

- [ ] **Step 1: Failing test** — `tests/test_statsapi_invalidate.py`:

```python
import os
import tempfile
import unittest

from psmodel import http, statsapi


class TestInvalidate(unittest.TestCase):
    def test_moves_every_cached_page_aside(self):
        with tempfile.TemporaryDirectory() as d:
            old = http.CACHE_DIR
            try:
                http.CACHE_DIR = d
                for off in (0, statsapi.PAGE):
                    p = http.cache_path(statsapi.season_url(2026, "hitting", statsapi.MLB, off), ".json")
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write("{}")
                self.assertEqual(statsapi.invalidate_season(2026, "hitting", statsapi.MLB), 2)
                self.assertEqual(statsapi.invalidate_season(2026, "hitting", statsapi.MLB), 0)
                self.assertEqual(len([f for f in os.listdir(d) if f.endswith(".stale")]), 2)
            finally:
                http.CACHE_DIR = old


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_statsapi_invalidate` → FAIL (`AttributeError: … 'season_url'`).

- [ ] **Step 3: Implement.** In `psmodel/statsapi.py` add `import os` below the module docstring (above `from . import http`). Add this function above `season_stats`:

```python
def season_url(season, group, sport_id, offset):
    return (f"{BASE}?stats=season&season={season}&group={group}"
            f"&sportId={sport_id}&limit={PAGE}&offset={offset}&playerPool=all")
```

In `season_stats`, replace the two-line `url = (...)` assignment with `url = season_url(season, group, sport_id, offset)`. Then add below `season_stats`:

```python
def invalidate_season(season, group, sport_id):
    """Move this season's cached pages aside (renamed *.stale) so the next call
    refetches -- for a season that was still in progress when first cached.
    Returns the number of pages moved."""
    moved, offset = 0, 0
    while True:
        path = http.cache_path(season_url(season, group, sport_id, offset), ".json")
        if not os.path.exists(path):
            return moved
        os.replace(path, path + ".stale")
        moved += 1
        offset += PAGE
```

- [ ] **Step 4:** In `build_labels.py`: change `FIRST, LAST = 2015, 2026` to `FIRST, LAST = 2013, 2026`; change the docstring's first line to `"""Builds MLB player-season labels for 2013-2026 and writes cache/labels.csv.`; after `ap.add_argument("--games", …)` add

```python
    ap.add_argument("--refresh", type=int, default=None,
                    help="refetch this season's MLB stats (cached while still in progress)")
```

and right after `args = ap.parse_args()` add

```python
    if args.refresh is not None:
        for group in ("hitting", "pitching"):
            n = statsapi.invalidate_season(args.refresh, group, statsapi.MLB)
            print(f"refresh {args.refresh} {group}: moved {n} cached page(s) aside")
```

- [ ] **Step 5: Run** the full suite → 135 pass.

- [ ] **Step 6: Security audit**, then rebuild labels (4–8 new requests for 2013–2014):
  - **Ask the user whether the 2026 MLB regular season has ended.** It ends in late September 2026.
    - If it has: `python build_labels.py --refresh 2026`.
    - If not: `python build_labels.py`, then rerun with `--refresh 2026` before Task 8's final run.
  - Then `python parity/compare.py`. It must pass: `labels.py` is unchanged, but the gate is the rule after any label rebuild.
  - Check the printout: 2013 and 2014 each show roughly 600–700 hitters, and the replacement OBP sits in the same range as 2015's.

- [ ] **Step 7: Commit** `feat(prospects-model): labels from 2013 and a deliberate in-season refresh`.

---

### Task 3: Rows without swing data

**Files:** Modify `psmodel/features.py`, `psmodel/milb.py`; Create `tests/test_3c_inputs.py`

- [ ] **Step 1: Failing tests** — `tests/test_3c_inputs.py`:

```python
import unittest

from psmodel import features as F
from psmodel import milb, statsapi


def raw(pa=200):
    return {"player_id": 1, "name": "A", "season": 2014, "sport_id": 12, "league": "Eastern League",
            "age": 22, "g": 50, "pa": pa, "ab": pa - 20, "h": 50, "hr": 5, "r": 20, "bb": 15, "so": 40,
            "sb": 3, "obp": 0.33, "slg": 0.40, "np": pa * 4}


class TestMissingSwings(unittest.TestCase):
    def test_missing_swings_give_missing_rates(self):
        f = F.hitter_features(dict(raw(), swings=None, whiffs=None))
        self.assertIsNone(f["whiff"])
        self.assertIsNone(f["swing"])
        self.assertIsNone(f["swstr"])
        self.assertAlmostEqual(f["k"], 0.2)

    def test_season_rows_can_skip_advanced(self):
        orig = (statsapi.season_stats, statsapi.season_advanced)
        calls = []
        statsapi.season_stats = lambda s, g, sid: [raw()]
        statsapi.season_advanced = lambda *a: calls.append(a) or {}
        try:
            rows = milb.season_rows(2014, 12, "hitting", advanced=False)
        finally:
            statsapi.season_stats, statsapi.season_advanced = orig
        self.assertEqual(calls, [])
        self.assertIsNone(rows[0]["swings"])
        self.assertIsNone(rows[0]["whiffs"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_3c_inputs` → FAIL (`TypeError: unsupported operand … NoneType` and `unexpected keyword argument 'advanced'`).

- [ ] **Step 3: Implement.** In `psmodel/features.py` replace `_ratio` with:

```python
def _ratio(a, b):
    return (a / b) if (a is not None and b) else None
```

In `psmodel/milb.py` replace `season_rows` with:

```python
def season_rows(season, sport_id, group, advanced=True):
    """advanced=False skips seasonAdvanced (swing data): swings/whiffs become None,
    for seasons where the endpoint has no data."""
    basic = [r for r in statsapi.season_stats(season, group, sport_id)
             if r.get("league") not in MEX_LEAGUES]
    rows = combine_by_player(basic, group)
    adv = statsapi.season_advanced(season, group, sport_id) if advanced else None
    for r in rows:
        a = adv.get(r["player_id"], {}) if adv is not None else None
        r["swings"] = a.get("swings", 0) if a is not None else None
        r["whiffs"] = a.get("whiffs", 0) if a is not None else None
    return rows
```

- [ ] **Step 4: Run** the full suite → 137 pass. The existing `test_milb` still passes because `advanced` defaults to True.
- [ ] **Step 5: Commit** `feat(prospects-model): minor-league rows without swing data`.

---

### Task 4: Cohort rows — history, loading, features, groups

**Files:** Create `psmodel/cohorts.py`, `tests/test_cohorts.py`

- [ ] **Step 1: Failing tests** — `tests/test_cohorts.py`:

```python
import unittest

from psmodel import cohorts


def milb_row(pid, season, sid, pa=200, age=22):
    return {"player_id": pid, "name": f"P{pid}", "season": season, "sport_id": sid, "age": age,
            "pa": pa, "ab": pa - 20, "h": 50, "hr": 5, "r": 20, "bb": 15, "so": 40, "sb": 3,
            "obp": 0.33, "slg": 0.40, "np": pa * 4, "swings": pa * 2, "whiffs": pa // 2}


class TestPriorPa(unittest.TestCase):
    def test_counts_only_earlier_seasons(self):
        hist = {1: {2010: 200, 2011: 150, 2013: 50}}
        self.assertEqual(cohorts.prior_mlb_pa(hist, 1, 2012), 350)
        self.assertEqual(cohorts.prior_mlb_pa(hist, 2, 2012), 0)


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        milb = [milb_row(1, 2018, 12), milb_row(1, 2019, 12, pa=300),
                milb_row(2, 2019, 12, pa=50), milb_row(2, 2021, 12), milb_row(2, 2021, 11),
                milb_row(3, 2019, 11), milb_row(4, 2019, 13, pa=100)]
        hist = {3: {2017: 400}}
        mlb = {1: [{"season": 2020, "value": 1.0, "pa": 300, "ip": 0.0}]}
        rows = cohorts.build_rows(milb, hist, mlb)
        self.by = {(r["player_id"], r["season"], r["sport_id"]): r for r in rows}

    def test_volume_floor_and_established_cut(self):
        self.assertEqual(sorted(self.by), [(1, 2018, 12), (1, 2019, 12), (2, 2021, 11), (2, 2021, 12)])

    def test_repeat_level_bridges_2020(self):
        self.assertEqual(self.by[(1, 2019, 12)]["f"]["repeat_level"], 1.0)
        self.assertEqual(self.by[(1, 2018, 12)]["f"]["repeat_level"], 0.0)
        self.assertEqual(self.by[(2, 2021, 12)]["f"]["repeat_level"], 1.0)   # 2019 AA, even at 50 PA
        self.assertEqual(self.by[(2, 2021, 11)]["f"]["repeat_level"], 0.0)

    def test_multi_level_and_level_flags(self):
        f = self.by[(2, 2021, 11)]["f"]
        self.assertEqual((f["multi_level"], f["is_aaa"], f["is_aa"], f["is_higha"]), (1.0, 1.0, 0.0, 0.0))
        self.assertEqual(self.by[(1, 2018, 12)]["f"]["multi_level"], 0.0)

    def test_mlb_attached_and_groups_cover_every_feature(self):
        self.assertEqual(self.by[(1, 2018, 12)]["mlb"][0]["season"], 2020)
        keys = {k for g in cohorts.GROUPS.values() for k in g}
        self.assertEqual(keys, set(self.by[(1, 2018, 12)]["f"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_cohorts` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/cohorts.py`. Set `WHIFF_FIRST` from Task 1 Step 3:

```python
"""3c-hitters rows: every minor-league hitter-season-level from 2012, with the
features the base model uses and the player's MLB labels attached. Targets are
attached later, per vantage year, by walkforward.py -- never here.
"""
from . import features as F
from . import milb, statsapi

CURRENT_SEASON = 2026
PA_HISTORY_FIRST = 2005        # MLB PA before the first cohort, for the established cut
MILB_SEASONS = tuple(s for s in range(2012, CURRENT_SEASON + 1) if s != 2020)   # no 2020 MiLB season
LEVELS = (11, 12, 13, 14)
LEVEL_NAMES = {11: "AAA", 12: "AA", 13: "High-A", 14: "Single-A"}
LEVEL_FLAGS = {11: "is_aaa", 12: "is_aa", 13: "is_higha"}   # Single-A is the baseline
WHIFF_FIRST = 2016             # first season with minor-league swing data (Task 1)
MIN_PA = F.HIT_MIN_PA          # 150 at the level
ESTABLISHED_PA = 300           # prior MLB PA that makes him not a prospect

GROUPS = {
    "age_level": ["age", "is_aaa", "is_aa", "is_higha"],
    "contact": ["k", "whiff", "swstr"],
    "approach": ["bb", "obp", "swing"],
    "power": ["iso", "hr_pa", "slg"],
    "speed": ["sb_pa"],
    "trajectory": ["repeat_level", "multi_level", "pa"],
}
BINARY = {"is_aaa", "is_aa", "is_higha", "repeat_level", "multi_level"}
_BOX = ("age", "pa", "k", "bb", "iso", "hr_pa", "obp", "slg", "sb_pa", "whiff", "swing", "swstr")


def mlb_pa_history(first=PA_HISTORY_FIRST, last=CURRENT_SEASON):
    """{player_id: {season: MLB PA}}."""
    out = {}
    for s in range(first, last + 1):
        for r in statsapi.season_stats(s, "hitting", statsapi.MLB):
            out.setdefault(r["player_id"], {})[s] = r["pa"]
    return out


def prior_mlb_pa(history, pid, season):
    return sum(pa for s, pa in history.get(pid, {}).items() if s < season)


def load_milb(seasons=MILB_SEASONS, levels=LEVELS):
    rows = []
    for s in seasons:
        for sid in levels:
            rows += milb.season_rows(s, sid, "hitting", advanced=s >= WHIFF_FIRST)
    return rows


def previous_season(season):
    return 2019 if season == 2021 else season - 1


def build_rows(milb_rows, pa_history, mlb_seasons):
    """Rows {player_id, name, season, sport_id, f, mlb} for hitters with >=150 PA at
    a level who weren't established in MLB. Repeat/multi-level flags look at ALL
    minor-league rows (any PA). Continuous features are z-scored within
    level-season, so age becomes age relative to the level."""
    seen = {}
    for r in milb_rows:
        seen.setdefault((r["player_id"], r["season"]), set()).add(r["sport_id"])
    rows = []
    for r in milb_rows:
        pid, s = r["player_id"], r["season"]
        if r["pa"] < MIN_PA or prior_mlb_pa(pa_history, pid, s) >= ESTABLISHED_PA:
            continue
        base = F.hitter_features(r)
        f = {k: base[k] for k in _BOX}
        for sid, name in LEVEL_FLAGS.items():
            f[name] = 1.0 if r["sport_id"] == sid else 0.0
        f["repeat_level"] = 1.0 if r["sport_id"] in seen.get((pid, previous_season(s)), ()) else 0.0
        f["multi_level"] = 1.0 if len(seen[(pid, s)]) > 1 else 0.0
        rows.append({"player_id": pid, "name": r["name"], "season": s, "sport_id": r["sport_id"],
                     "f": f, "mlb": mlb_seasons.get(pid, [])})
    F.standardize_within(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
    return rows
```

- [ ] **Step 4: Run** the full suite → 142 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): 3c hitter cohort rows, 2012 onward`.

---

### Task 5: As-of targets

**Files:** Create `psmodel/asof.py`, `tests/test_asof.py`

- [ ] **Step 1: Failing tests** — `tests/test_asof.py`:

```python
import unittest

from psmodel import asof


def s(season, value, pa=500):
    return {"season": season, "value": value, "pa": pa, "ip": 0.0}


class TestTargets(unittest.TestCase):
    def test_rating_is_best_of_next_four_eligible_seasons(self):
        mlb = [s(2019, 3.0), s(2020, 1.0, 300), s(2021, 9.0, 50), s(2023, 5.0)]
        self.assertEqual(asof.rating_target(mlb, 2018), 3.0)   # 2021 under 100 PA; 2023 outside
        self.assertEqual(asof.rating_target(mlb, 2019), 5.0)

    def test_rating_floor_and_empty(self):
        self.assertEqual(asof.rating_target([s(2019, -1.0)], 2018), 0.0)
        self.assertEqual(asof.rating_target([], 2018), 0.0)

    def test_soon_window_is_two_seasons(self):
        mlb = [s(2020, 0.7), s(2021, 0.9)]
        self.assertTrue(asof.soon_target(mlb, 2018, 0.6))
        self.assertFalse(asof.soon_target(mlb, 2017, 0.6))    # window 2018-2019
        self.assertFalse(asof.soon_target([s(2019, 0.5)], 2018, 0.6))

    def test_known_by_vantage(self):
        self.assertTrue(asof.rating_known(2018, 2022))
        self.assertFalse(asof.rating_known(2019, 2022))
        self.assertTrue(asof.soon_known(2021, 2023))
        self.assertFalse(asof.soon_known(2022, 2023))


class TestUsefulBar(unittest.TestCase):
    def test_uses_only_seasons_through_the_vantage(self):
        labels = {(i, "H"): [s(2013, float(i)), s(2014, float(100 + i))] for i in range(150)}
        self.assertEqual(asof.useful_bar(labels, 2013), 6.0)     # 144th best of 0..149
        self.assertEqual(asof.useful_bar(labels, 2014), 56.0)    # median(6, 106)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_asof` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/asof.py`:

```python
"""As-of targets: what a hitter produced after a snapshot season, and when that
answer became known. A backtest at vantage V may train only on cohorts whose
answer was known by V -- the NFLU rule.
"""
from . import dataset, targets

RATING_YEARS = 4
SOON_YEARS = 2
FIRST_LABEL = 2013


def rating_target(mlb, cohort):
    """Best season value in cohort+1..cohort+4 with >=100 PA, floored at 0."""
    vals = [r["value"] for r in mlb
            if cohort < r["season"] <= cohort + RATING_YEARS and (r.get("pa") or 0) >= targets.MIN_PA]
    return max(0.0, max(vals)) if vals else 0.0


def soon_target(mlb, cohort, bar):
    """A starter-quality season (total value >= bar) in cohort+1..cohort+2."""
    return any(r["value"] >= bar for r in mlb if cohort < r["season"] <= cohort + SOON_YEARS)


def rating_known(cohort, v):
    return cohort + RATING_YEARS <= v


def soon_known(cohort, v):
    return cohort + SOON_YEARS <= v


def useful_bar(labels, v):
    """The starter-quality bar from MLB seasons through v only."""
    return dataset.useful_threshold(labels, "H", first=FIRST_LABEL, last=v)
```

- [ ] **Step 4: Run** the full suite → 147 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): as-of targets for 3c`.

---

### Task 6: The walk-forward harness

**Files:** Create `psmodel/walkforward.py`, `tests/test_walkforward.py`

- [ ] **Step 1: Failing tests** — `tests/test_walkforward.py`:

```python
import unittest

import numpy as np

from psmodel import walkforward as W


def cohort_rows(n=150, cohorts=range(2012, 2025), seed=0):
    rng = np.random.default_rng(seed)
    rows, pid = [], 0
    for c in cohorts:
        if c == 2020:
            continue
        for _ in range(n):
            x, z = float(rng.normal()), float(rng.normal())
            rows.append({"player_id": pid, "season": c, "sport_id": 12, "f": {"x": x, "z": z},
                         "mlb": [{"season": c + 1, "value": x, "pa": 500, "ip": 0.0}]})
            pid += 1
    return rows


BARS = {v: 0.5 for v in range(2015, 2026)}


class TestFrames(unittest.TestCase):
    def test_sealed_cohort_refused_unless_unsealed(self):
        rows = cohort_rows(n=5)
        with self.assertRaises(ValueError):
            W.frames(rows, "soon", 2024, 0.5, ["x"])
        W.frames(rows, "soon", 2024, 0.5, ["x"], unseal=True)

    def test_train_only_known_cohorts_and_no_test_players(self):
        rows = cohort_rows(n=5)
        for season in (2014, 2019):
            rows.append({"player_id": 999, "season": season, "sport_id": 12,
                         "f": {"x": 0.0, "z": 0.0}, "mlb": []})
        train, test = W.frames(rows, "rating", 2019, 0.5, ["x"])
        self.assertEqual(max(r["season"] for r in train), 2015)
        self.assertNotIn(999, {r["player_id"] for r in train})
        self.assertIn(999, {r["player_id"] for r in test})
        soon_train, _ = W.frames(rows, "soon", 2021, 0.5, ["x"])
        self.assertEqual(max(r["season"] for r in soon_train), 2019)

    def test_rows_missing_a_key_are_dropped(self):
        rows = cohort_rows(n=5)
        rows[0]["f"]["x"] = None
        train, _ = W.frames(rows, "rating", 2019, 0.5, ["x"])
        self.assertNotIn(rows[0]["player_id"], {r["player_id"] for r in train})


class TestFitting(unittest.TestCase):
    def test_signal_family_is_adopted(self):
        res = W.compare(cohort_rows(), ["z"], ["x"], "rating", "ridge", BARS, W.RATING_VANTAGES)
        self.assertTrue(W.adopt(res)[0])

    def test_soon_classifier_ranks_signal(self):
        preds = W.predictions(cohort_rows(), ["x"], "soon", "logit", BARS, W.SOON_VANTAGES)
        self.assertEqual(sorted(preds), list(W.SOON_VANTAGES))
        for v, (test, p) in preds.items():
            self.assertGreater(W.metrics(test, p, "soon", 0.5)["rank"], 0.8)

    def test_too_little_training_is_not_available(self):
        res = W.compare(cohort_rows(n=5), ["z"], ["x"], "rating", "ridge", BARS, (2019,))
        self.assertIsNone(res[2019])


class TestDecisions(unittest.TestCase):
    def _m(self, rank, t50=0.5, t100=0.5):
        return {"rank": rank, "top50": t50, "top100": t100}

    def test_adopt_needs_two_wins_without_top_losses(self):
        win = {"base": self._m(0.3), "fam": self._m(0.4)}
        top_loss = {"base": self._m(0.3, t50=0.6), "fam": self._m(0.4, t50=0.5)}
        self.assertEqual(W.adopt({1: win, 2: win, 3: top_loss})[:2], (True, 2))
        self.assertEqual(W.adopt({1: win, 2: top_loss, 3: top_loss})[:2], (False, 1))
        self.assertFalse(W.adopt({1: win, 2: None, 3: None})[0])     # only one vantage available

    def test_pick_kind_prefers_simple_unless_complex_wins_twice(self):
        s, c = self._m(0.4), self._m(0.5)
        self.assertEqual(W.pick_kind({1: (s, c), 2: (c, s), 3: (c, s)}, "rating"), "ridge")
        self.assertEqual(W.pick_kind({1: (s, c), 2: (s, c), 3: (c, s)}, "soon"), "gbm")

    def test_calibration_bins(self):
        pred = np.linspace(0, 1, 100)
        test = [{"y": 1.0 if p > 0.5 else 0.0} for p in pred]
        bins = W.calibration(test, pred, bins=10)
        self.assertEqual(len(bins), 10)
        self.assertEqual(bins[0][1], 0.0)
        self.assertEqual(bins[-1][1], 1.0)


class TestInteractions(unittest.TestCase):
    def test_pairs_reported_per_vantage(self):
        hits = W.interactions_by_vantage(cohort_rows(), ["x", "z"], "soon", BARS, (2021,))
        self.assertEqual(list(hits), [("x", "z")])
        self.assertEqual(hits[("x", "z")][0][0], 2021)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_walkforward` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/walkforward.py`:

```python
"""Walk-forward backtests that train only on what was known at each vantage year.

At vantage V the test set is cohort V; training is every cohort whose answer was
known by V (asof.rating_known / soon_known), minus every player in the test
cohort (a player's rows share one outcome). The 2024 cohort is SEALED for the
final check and refused unless unseal=True.
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import asof, evaluate, interactions

SEALED = frozenset({2024})
RATING_VANTAGES = (2019, 2021, 2022)
SOON_VANTAGES = (2021, 2022, 2023)
KINDS = {"rating": ("ridge", "gbm"), "soon": ("logit", "gbm")}   # (simple, complex)
MIN_TRAIN = 300
TOP_NS = (25, 50, 100)


def _y(r, target, bar):
    if target == "rating":
        return asof.rating_target(r["mlb"], r["season"])
    return 1.0 if asof.soon_target(r["mlb"], r["season"], bar) else 0.0


def frames(rows, target, v, bar, keys, unseal=False):
    """(train, test) at vantage v, complete on keys, with targets attached as 'y'."""
    if v in SEALED and not unseal:
        raise ValueError(f"cohort {v} is sealed until the final check")
    known = asof.rating_known if target == "rating" else asof.soon_known
    test = [r for r in rows if r["season"] == v]
    ids = {r["player_id"] for r in test}
    train = [r for r in rows if known(r["season"], v) and r["player_id"] not in ids]
    return [[dict(r, y=_y(r, target, bar)) for r in part if all(r["f"].get(k) is not None for k in keys)]
            for part in (train, test)]


def _model(target, kind):
    if target == "rating":
        return evaluate._model(kind)
    if kind == "gbm":
        return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                              min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=10, max_iter=2000))


def _X(rows, keys):
    return np.array([[r["f"][k] for k in keys] for r in rows], dtype=float)


def fit_predict(train, test, keys, target, kind):
    m = _model(target, kind).fit(_X(train, keys), np.array([r["y"] for r in train]))
    Xt = _X(test, keys)
    return m, (m.predict_proba(Xt)[:, 1] if target == "soon" else m.predict(Xt))


def metrics(test, pred, target, bar):
    """Rank accuracy (Spearman for rating, AUC for soon) and top-N precision,
    counting PLAYERS: each player's best-predicted row only."""
    y = [r["y"] for r in test]
    rank = roc_auc_score(y, pred) if target == "soon" else spearmanr(pred, y).statistic
    best = {}
    for r, p in zip(test, pred):
        useful = r["y"] >= bar if target == "rating" else r["y"] == 1.0
        if r["player_id"] not in best or p > best[r["player_id"]][0]:
            best[r["player_id"]] = (p, useful)
    ranked = sorted(best.values(), key=lambda t: -t[0])
    out = {"rank": float(rank), "n": len(test)}
    for n in TOP_NS:
        top = ranked[:n]
        out[f"top{n}"] = sum(u for _, u in top) / len(top)
    return out


def compare(rows, base, family, target, kind, bars, vantages, unseal=False):
    """{v: {'base': metrics, 'fam': metrics} | None}, both fits on IDENTICAL rows
    (complete on base + family)."""
    union = base + [k for k in family if k not in base]
    res = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], union, unseal)
        if len(train) < MIN_TRAIN or not test:
            res[v] = None
            continue
        res[v] = {}
        for name, keys in (("base", base), ("fam", union)):
            evaluate.guard_features(train, keys)
            res[v][name] = metrics(test, fit_predict(train, test, keys, target, kind)[1], target, bars[v])
    return res


def adopt(res, min_wins=2):
    """(adopted, wins, vantages available). A win = better rank accuracy without a
    lower top-50 or top-100. Needs >=2 available vantages."""
    avail = [r for r in res.values() if r is not None]
    wins = sum(1 for r in avail if r["fam"]["rank"] > r["base"]["rank"]
               and r["fam"]["top50"] >= r["base"]["top50"] and r["fam"]["top100"] >= r["base"]["top100"])
    return len(avail) >= 2 and wins >= min_wins, wins, len(avail)


def pick_kind(res, target):
    """The complex model only if it beats the simple one on rank at >=2 vantages."""
    simple, complex_ = KINDS[target]
    wins = sum(1 for r in res.values() if r is not None and r[1]["rank"] > r[0]["rank"])
    return complex_ if wins >= 2 else simple


def choose_kind(rows, keys, target, bars, vantages, unseal=False):
    res = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN or not test:
            res[v] = None
            continue
        evaluate.guard_features(train, keys)
        res[v] = tuple(metrics(test, fit_predict(train, test, keys, target, k)[1], target, bars[v])
                       for k in KINDS[target])
    return pick_kind(res, target), res


def group_importance(rows, groups, target, kind, bars, vantages):
    """{(group,): compare-result}: each group vs all the others. Groups that fail
    alone are also tested in pairs, since near-duplicates hide each other."""
    all_keys = [k for g in groups.values() for k in g]
    out = {}
    for g, keys in groups.items():
        out[(g,)] = compare(rows, [k for k in all_keys if k not in keys], keys, target, kind, bars, vantages)
    failing = [g for g in groups if not adopt(out[(g,)])[0]]
    for i, a in enumerate(failing):
        for b in failing[i + 1:]:
            fam = groups[a] + groups[b]
            out[(a, b)] = compare(rows, [k for k in all_keys if k not in fam], fam, target, kind, bars, vantages)
    return out


def predictions(rows, keys, target, kind, bars, vantages, unseal=False):
    """{v: (test rows, predictions)} for one model."""
    out = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN or not test:
            continue
        evaluate.guard_features(train, keys)
        out[v] = (test, fit_predict(train, test, keys, target, kind)[1])
    return out


def calibration(test, pred, bins=10):
    """[(mean predicted, actual rate, n)] by predicted-probability bin."""
    pred = np.asarray(pred, dtype=float)
    return [(float(np.mean(pred[c])), float(np.mean([test[i]["y"] for i in c])), len(c))
            for c in np.array_split(np.argsort(pred), bins)]


class _Proba:
    """Makes a classifier's probability look like predict() for interactions.py."""
    def __init__(self, m):
        self.m = m

    def predict(self, X):
        return self.m.predict_proba(X)[:, 1]


def interactions_by_vantage(rows, keys, target, bars, vantages, n=10, sample=100, unseal=False):
    """{(key_a, key_b): [(vantage, strength)]} for pairs in each vantage's top n (trees)."""
    hits = {}
    for v in vantages:
        train, _ = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN:
            continue
        m, _ = fit_predict(train, train[:1], keys, target, "gbm")
        model = _Proba(m) if target == "soon" else m
        idx = np.random.default_rng(v).choice(len(train), size=min(sample, len(train)), replace=False)
        for h, a, b in interactions.top_pairs(model, _X([train[i] for i in idx], keys), keys, n):
            hits.setdefault((a, b), []).append((v, h))
    return hits
```

- [ ] **Step 4: Run** the full suite → 157 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): as-of walk-forward harness with a sealed 2024`.

---

### Task 7: Pull the inputs

**Files:** Create `pull_3c_data.py`

- [ ] **Step 1: Create** `pull_3c_data.py`:

```python
"""Pulls the 3c-hitters inputs into the HTTP cache: minor-league hitter season
totals at four levels for 2012-2026 (swing data from WHIFF_FIRST), and MLB PA for
2005-2026 (the established-player cut). Every request is cached, so a rerun
resumes where a killed run stopped.

Usage:  python pull_3c_data.py
"""
from psmodel import cohorts, milb


def main():
    hist = cohorts.mlb_pa_history()
    print(f"MLB PA history: {len(hist)} players, {cohorts.PA_HISTORY_FIRST}-{cohorts.CURRENT_SEASON}", flush=True)
    for s in cohorts.MILB_SEASONS:
        parts = []
        for sid in cohorts.LEVELS:
            rows = milb.season_rows(s, sid, "hitting", advanced=s >= cohorts.WHIFF_FIRST)
            q = sum(1 for r in rows if r["pa"] >= cohorts.MIN_PA)
            sw = sum(1 for r in rows if r.get("swings"))
            parts.append(f"{cohorts.LEVEL_NAMES[sid]} {len(rows)} ({q} with {cohorts.MIN_PA}+ PA, {sw} with swings)")
        print(s, " | ".join(parts), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Security audit**, then `python pull_3c_data.py` (about 250 requests at 1/s, ~5 minutes). Sanity checks:
  - every level-season has ≥ ~150 hitters with 150+ PA;
  - `with swings` is 0 before `WHIFF_FIRST` and close to the row count after it;
  - the MLB PA history covers ~20k players.

  If a level-season shows 0 rows, stop and report.
- [ ] **Step 3: Commit** `feat(prospects-model): 3c data pull`.

---

### Task 8: The base-model backtests

**Files:** Create `model3c_base.py`

- [ ] **Step 1: Create** `model3c_base.py`:

```python
"""3c-hitters plan A: as-of walk-forward backtests of the base model, for both
outputs -- rating (best season in the next 4) and soon (starter-quality season
within 2). Model choice, group importance, interactions, calibration. 2024 stays
sealed for plan B's final check.

Usage:  python model3c_base.py
Reads only cached data (run pull_3c_data.py and build_labels.py first).
Writes cache/model3c_base_report.txt and cache/model3c_choice.json (gitignored).
"""
import json
import os
import statistics

import numpy as np

from psmodel import asof, cohorts, dataset
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model3c_base_report.txt")
CHOICE = os.path.join(CACHE, "model3c_choice.json")


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['base']['rank']:.3f}->{r['fam']['rank']:.3f} "
                     f"top50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f}"
                     for v, r in res.items())


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    mlb = {pid: rows for (pid, typ), rows in labels.items() if typ == "H"}
    rows = cohorts.build_rows(cohorts.load_milb(), cohorts.mlb_pa_history(), mlb)
    L = ["3c-HITTERS BASE MODEL -- as-of walk-forward backtests (2024 sealed)",
         f"rows: {len(rows)} hitter-season-levels, {len({r['player_id'] for r in rows})} players",
         "per season: " + ", ".join(f"{s} {sum(1 for r in rows if r['season'] == s)}"
                                    for s in cohorts.MILB_SEASONS), ""]
    all_keys = [k for g in cohorts.GROUPS.values() for k in g]
    choice = {}
    for target, vantages in (("rating", W.RATING_VANTAGES), ("soon", W.SOON_VANTAGES)):
        bars = {v: asof.useful_bar(labels, v) for v in vantages}
        simple, complex_ = W.KINDS[target]
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; useful bar as-of: "
                 + ", ".join(f"{v} {b:.3f}" for v, b in bars.items()))
        kind, kres = W.choose_kind(rows, all_keys, target, bars, vantages)
        L.append(f"model: {kind}  (" + "; ".join(
            f"{v}: n/a" if r is None else f"{v}: {simple} {r[0]['rank']:.3f} vs {complex_} {r[1]['rank']:.3f}"
            for v, r in kres.items()) + ")")
        L.append("groups -- drop-and-refit; KEEP if dropping it hurts at >=2 vantages:")
        adopted = set()
        for gs, res in W.group_importance(rows, cohorts.GROUPS, target, kind, bars, vantages).items():
            ok, wins, avail = W.adopt(res)
            L.append(f"  {' + '.join(gs):24} {'KEEP' if ok else 'drop':4} {wins}/{avail}  {fmt(res)}")
            if ok:
                adopted.update(gs)
        keys = [k for g in cohorts.GROUPS if g in adopted for k in cohorts.GROUPS[g]]
        choice[target] = {"kind": kind, "adopted": sorted(adopted), "keys": keys}
        if not keys:
            L += ["  nothing adopted -- no final model", ""]
            continue
        preds = W.predictions(rows, keys, target, kind, bars, vantages)
        for v, (test, p) in preds.items():
            m = W.metrics(test, p, target, bars[v])
            L.append(f"final model {v}: rank {m['rank']:.3f}, top25 {m['top25']:.2f}, "
                     f"top50 {m['top50']:.2f}, top100 {m['top100']:.2f} (n={m['n']})")
        if target == "soon":
            test = [r for v in preds for r in preds[v][0]]
            pred = np.concatenate([preds[v][1] for v in preds])
            L.append("calibration, pooled test cohorts (predicted -> actual):")
            L += [f"  {mp:.2f} -> {act:.2f}  (n={n})" for mp, act, n in W.calibration(test, pred)]
        hits = W.interactions_by_vantage(rows, keys, target, bars, vantages)
        L.append("interactions (trees; finding = top-10 at >=2 vantages):")
        for (a, b), vs in sorted(hits.items(), key=lambda t: (-len(t[1]), -statistics.fmean(h for _, h in t[1])))[:10]:
            L.append(f"  {a} x {b}: {len(vs)} vantage(s), strength {statistics.fmean(h for _, h in vs):.3f} "
                     f"-> {'finding' if len(vs) >= 2 else 'hypothesis'}")
        wp = hits.get(("whiff", "iso"))
        L.append(f"  whiff x power rematch (whiff x iso): "
                 + (f"top-10 at {len(wp)} vantage(s)" if wp else "not in any vantage's top 10"
                    if "whiff" in keys and "iso" in keys else "not testable (a group was dropped)"))
        L.append("")
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump(choice, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run** the full suite → 157 pass (the driver has no unit tests; its pieces do).

- [ ] **Step 3: Confirm the 2026 labels are final.** If Task 2 ran before the MLB regular season ended, run the security audit and then `python build_labels.py --refresh 2026` and `python parity/compare.py` now. The rating's 2022 test cohort depends on the 2026 season.

- [ ] **Step 4: Run** `python model3c_base.py`. It reads only cached data, and may take several minutes. Sanity checks before trusting it:
  - rows per season in the low thousands;
  - useful bars around 0.5–0.7;
  - rating rank (Spearman) positive, roughly 0.3–0.5 (the whiff test got 0.46 on a related target);
  - soon AUC well above 0.5;
  - a vantage showing `n/a` only where the spec expects it (the rating's 2019 vantage for whiff-bearing models if `WHIFF_FIRST` is 2016).

  If anything else is `n/a`, or the ranks are near 0, stop and report. Don't tune.

- [ ] **Step 5: Commit** `feat(prospects-model): 3c base-model as-of backtests` (the report and choice JSON live in gitignored `cache/`).

- [ ] **Step 6: Record results.** Add a "Plan A result (run <date>)" section to the 3c spec: model choice per output, kept/dropped groups (in plain words), the per-vantage final metrics, calibration highlights, interaction findings vs hypotheses, the whiff × power rematch, and whether `WHIFF_FIRST` limited anything. Update `project_prospect_model.md` in memory. Commit `docs(spec): record 3c plan A result`. **Hand the result summary to Opus for a check before telling the user:** step 1's first write-up overclaimed, and memory records that lesson. Plan B (tracking layer, pulled-air parity, sealed 2024 check, ratings) is next, designed on Opus.

---

## Not in this plan (plan B)

The as-of tracking layer and trust weights, the pulled-air parity check, **opening the sealed 2024 cohort**, and `hitter_ratings.csv`.
