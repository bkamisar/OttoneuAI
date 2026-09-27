# Step 1: Hitter Tracking Score — Implementation Plan (3b, plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Learn what hitter tracking metrics are worth from MLB (value at 600 PA next season), translate AAA readings onto the MLB scale, check the resulting tracking score on real 2022–23 AAA prospects, and report which metric groups matter, including the user's pulled-air hypothesis.

**Architecture:** `psmodel/step1.py` builds MLB training rows (tracking in *t* → value at 600 PA in *t+1*), fits the AAA→MLB offsets, and builds prospect rows. `psmodel/interactions.py` measures pairwise interaction strength. `psmodel/evaluate.py` gains `fit`/`predict` wrappers around the existing whiff-test harness. `step1_run.py` runs every test and writes the report. Research only: no ratings file, no UI.

**Tech Stack:** Python 3.14 stdlib + numpy, scipy, sklearn (all already used by `evaluate.py`). Tests: stdlib `unittest`. Hosts: `baseballsavant.mlb.com`, `statsapi.mlb.com`. Nothing new installed.

**Spec:** `docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md`.

---

## Context the implementer needs

- Run everything from `prospects-model/`. Tests: `python -m unittest discover -s tests` (**115 pass, 3 live-only skipped** before this plan).
- **Inputs already on disk (gitignored `cache/`):** `mlb_tracking.csv` (Savant, 2015–2026), `aaa_tracking.csv` (our code, 2022 PCL + 2023–26), `labels.csv` (`player_id,name,season,type,pa,ip,value`, one row per player-season-type; `value` is 4×4 SGP above replacement). MLB StatsAPI season stats for 2015–2026 are cached by `psmodel/http.py` (fetched when labels were built).
- **Target math:** `labels.hitter_sgp` is homogeneous in playing time. Scaling PA, R and HR by k with OBP/SLG fixed scales SGP by exactly k, replacement term included. So value at 600 PA = `value × 600 / PA`.
- **Existing helpers to reuse:** `dataset.load_labels(path)` → `{(player_id, type): [{season, value, pa, ip}]}`; `dataset.useful_threshold(labels, "H")` → the starter-quality SGP bar (≈0.61); `features.hitter_features(statsapi_row)` → `k, bb, iso, hr_pa, obp, slg, …`; `statsapi.season_stats(season, "hitting", sport_id)` → one row per player-season with `age`; `evaluate.compare / adopt / oof_predictions / assign_folds` (player-grouped CV; rows are `{player_id, f: {feature: value}, target, weight, useful}`).
- **Security posture (user requirement):** re-run the audit before any network step. Stdlib + already-installed packages only; hosts limited to `statsapi.mlb.com` and `baseballsavant.mlb.com`; `git ls-files cache` empty; no credentials. **No bulk downloads** (total network in this plan: about 20 Savant + about 6 StatsAPI requests).
- Commits are local only; end each message with `Co-Authored-By: <current model> <noreply@anthropic.com>`. The user pushes via GitHub Desktop.

## File map

| File | Change | Responsibility |
|---|---|---|
| `psmodel/savant.py` | Modify | Add spray fields to the custom pull; keep the EV board's batted-ball count as `bbe` |
| `build_tracking.py` | Modify | Write spray columns into the tables |
| `psmodel/evaluate.py` | Modify | `fit(rows, keys, kind)` and `predict(model, rows, keys)` |
| `psmodel/step1.py` | Create | Groups, tables, MLB rows, target, translation, prospect rows, Spearman CI |
| `psmodel/interactions.py` | Create | Friedman's H (absolute) and top pairs |
| `step1_run.py` | Create | Runs all tests; writes `cache/step1_report.txt`, `cache/aaa_translation.csv`, and `cache/step1_choice.json` (model type + adopted features, for 3c to refit the same score) |
| `tests/test_savant.py` | Modify | bbe + spray assertions |
| `tests/test_evaluate_fit.py`, `tests/test_step1.py`, `tests/test_interactions.py` | Create | Unit tests |

---

### Task 1: Discover Savant's spray fields (no code committed)

**Why:** the spray group should include a pulled-air rate if Savant publishes one (the user's hypothesis is specifically *pulled fly balls*). Field names must be verified, not guessed.

- [ ] **Step 1: Security audit.**

```bash
tasklist 2>/dev/null | grep -i python || echo "no stray python"
grep -rhoE "https?://[a-zA-Z0-9.-]+" psmodel/*.py *.py | sort -u
grep -rniE "api[_-]?key|password|token|secret|authorization" psmodel/*.py *.py || echo "no credentials"
git ls-files cache | wc -l
```

Expected: no stray python; only `https://baseballsavant.mlb.com` and `https://statsapi.mlb.com`; no credentials; `0`.

- [ ] **Step 2: List spray-like selection keys on the custom leaderboard page and test which ones return data** (2 requests):

```bash
python - <<'EOF'
import csv, io, re
from psmodel import http
html = http.fetch_text("https://baseballsavant.mlb.com/leaderboard/custom?year=2024&type=batter&min=q", ".html")
cands = sorted({k for k in re.findall(r"[a-z][a-z0-9_]*(?:pull|oppo|straight)[a-z0-9_]*", html)})
print("candidates:", cands)
url = ("https://baseballsavant.mlb.com/leaderboard/custom?year=2024&type=batter&min=100&selections="
       + ",".join(cands) + "&csv=true")
rows = list(csv.DictReader(io.StringIO(http.fetch_text(url, ".csv"))))
print("rows:", len(rows))
for k in cands:
    filled = sum(1 for r in rows if r.get(k) not in (None, ""))
    print(f"  {k:40} populated for {filled} hitters")
EOF
```

- [ ] **Step 3: Decide `SPRAY_FIELDS`.** Keep every candidate that is populated for ≥100 hitters **and** ends in `_percent`. `pull_percent`, `straightaway_percent`, `opposite_percent` are expected (they returned data in plan A's first parity run). Write the final list down for Task 2. If a pulled-air key is among them, say so to the user: that's their hypothesis's direct test. If the combined request errors (Savant rejecting an unknown key), repeat Step 2 with one candidate per request.

- [ ] **Step 4: Confirm the exit-velocity board carries a batted-ball count** (cached, no network):

```bash
python -c "from psmodel import http, savant; print(http.fetch_text(savant.EV_URL.format(year=2024), '.csv').splitlines()[0])"
```

Expected: the header includes `attempts` (batted balls). If it doesn't, stop and report; Task 2's `bbe` depends on it.

---

### Task 2: Spray fields and batted-ball count in the Savant tables

**Files:** Modify `psmodel/savant.py`, `build_tracking.py`, `tests/test_savant.py`

- [ ] **Step 1: Failing tests.** In `tests/test_savant.py`, replace `test_parses_and_merges` with:

```python
    def test_parses_and_merges(self):
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {"exit_velocity_avg": "91.2", "whiff_percent": "",
                                                                  "pull_percent": "40.5"})])
        self.pages["ev"] = lambda url: ev_csv([(10, 300, 115.1, 180.5)])
        got = savant.hitter_season(2024)
        self.assertAlmostEqual(got[10]["exit_velocity_avg"], 91.2)
        self.assertIsNone(got[10]["whiff_percent"])
        self.assertAlmostEqual(got[10]["max_hit_speed"], 115.1)
        self.assertAlmostEqual(got[10]["avg_distance"], 180.5)
        self.assertAlmostEqual(got[10]["pull_percent"], 40.5)
        self.assertEqual(got[10]["bbe"], 300.0)

    def test_custom_only_player_has_no_bbe(self):
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {}), (11, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 5, 100, 100)])
        self.assertIsNone(savant.hitter_season(2024)[11]["bbe"])
```

- [ ] **Step 2: Run** `python -m unittest tests.test_savant` → FAIL (`KeyError: 'pull_percent'` / `'bbe'`).

- [ ] **Step 3: Implement.** In `psmodel/savant.py` replace the `EV_FIELDS`/`CUSTOM_FIELDS` lines with the following, appending any extra keys chosen in Task 1 Step 3 to `SPRAY_FIELDS`:

```python
EV_FIELDS = ("max_hit_speed", "avg_distance")
# Savant's spray comes from tracked launch direction: usable for MLB history, but
# our AAA game records can't reproduce it (plan A parity), so these are MLB-only.
SPRAY_FIELDS = ["pull_percent", "straightaway_percent", "opposite_percent"]
CUSTOM_FIELDS = [m for m in HITTER_METRICS if m not in EV_FIELDS] + SPRAY_FIELDS + ["pa"]
```

and in `hitter_season` replace the two merge loops with:

```python
    for r in erows:
        d = out.setdefault(int(r["player_id"]), {f: None for f in CUSTOM_FIELDS})
        d.update({f: _num(r.get(f)) for f in EV_FIELDS})
        d["bbe"] = _num(r.get("attempts"))
    for d in out.values():
        for f in EV_FIELDS + ("bbe",):
            d.setdefault(f, None)
    return out
```

- [ ] **Step 4:** In `build_tracking.py` change `COLS` to:

```python
COLS = (["player_id", "season", "level", "bbe", "swings", "pitches", "pa"]
        + metrics.HITTER_METRICS + savant.SPRAY_FIELDS)
```

- [ ] **Step 5: Run** the full suite → 116 pass (3 skipped).

- [ ] **Step 6: Security audit** (same commands as Task 1 Step 1), then **rebuild the tables.** The custom URL changed, so this makes 12 Savant requests; the EV board is cached:

```bash
python build_tracking.py
python - <<'EOF'
import csv
m = list(csv.DictReader(open("cache/mlb_tracking.csv", encoding="utf-8")))
print("MLB rows", len(m), "| with bbe", sum(1 for r in m if r["bbe"]), "| with pull", sum(1 for r in m if r["pull_percent"]))
print("MLB rows with bbe >= 100 per season:",
      {s: sum(1 for r in m if r["season"] == str(s) and r["bbe"] and float(r["bbe"]) >= 100) for s in range(2015, 2027)})
EOF
```

Expected: same row counts as before (3,911 AAA / 9,835 MLB), most MLB rows with `bbe` and `pull_percent`, and roughly 350–450 hitters with ≥100 batted balls per full season (fewer in 2020). If `bbe` is empty everywhere, stop: the `attempts` column didn't come through.

- [ ] **Step 7: Commit** `feat(prospects-model): Savant spray fields and batted-ball counts in the MLB table`.

---

### Task 3: `fit` / `predict` in the evaluation harness

**Files:** Modify `psmodel/evaluate.py`; Create `tests/test_evaluate_fit.py`

- [ ] **Step 1: Failing tests** — `tests/test_evaluate_fit.py`:

```python
import unittest

import numpy as np

from psmodel import evaluate


class TestFitPredict(unittest.TestCase):
    def test_fit_then_predict_orders_rows(self):
        rng = np.random.default_rng(0)
        rows = [{"player_id": i, "f": {"x": float(x), "z": float(z)}, "target": 2 * x + 0.1 * z, "weight": 1.0}
                for i, (x, z) in enumerate(rng.normal(size=(200, 2)))]
        for kind in evaluate.KINDS:
            m = evaluate.fit(rows, ["x", "z"], kind)
            p = evaluate.predict(m, [{"f": {"x": -1.0, "z": 0.0}}, {"f": {"x": 1.0, "z": 0.0}}], ["x", "z"])
            self.assertLess(p[0], p[1], kind)

    def test_fit_refuses_phantom_feature(self):
        rows = [{"player_id": i, "f": {"x": float(i), "c": 1.0}, "target": float(i), "weight": 1.0}
                for i in range(10)]
        with self.assertRaises(ValueError):
            evaluate.fit(rows, ["x", "c"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_evaluate_fit` → FAIL (`AttributeError: … 'fit'`).

- [ ] **Step 3: Implement.** Append to `psmodel/evaluate.py`:

```python
def fit(rows, keys, kind="ridge"):
    """One model on all rows, after cross-validation has chosen what to fit."""
    guard_features(rows, keys)
    X, y, w = _xyw(rows, keys)
    return _fit(_model(kind), X, y, w, kind)


def predict(model, rows, keys):
    return model.predict(np.array([[r["f"][k] for k in keys] for r in rows], dtype=float))
```

- [ ] **Step 4: Run** the full suite → 118 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): fit/predict wrappers on the CV harness`.

---

### Task 4: Step-1 rows — MLB training data and the 600-PA target

**Files:** Create `psmodel/step1.py`, `tests/test_step1.py`

- [ ] **Step 1: Failing tests** — `tests/test_step1.py`:

```python
import os
import tempfile
import unittest

import numpy as np

from psmodel import step1


def stat(pid, season, pa=500, age=27):
    return {"player_id": pid, "season": season, "sport_id": 1, "age": age, "pa": pa, "ab": pa - 50,
            "h": 120, "hr": 20, "r": 70, "bb": 45, "so": 110, "sb": 5, "obp": 0.330, "slg": 0.450, "np": 2000}


def metrics_row(bbe=200.0, **over):
    m = {k: 50.0 for k in step1.tracking_keys()}
    m.update({"bbe": bbe, "pa": 500.0})
    m.update(over)
    return m


class TestTarget(unittest.TestCase):
    def test_rescales_to_600(self):
        self.assertAlmostEqual(step1.value_at_full_time(1.0, 300), 2.0)
        self.assertAlmostEqual(step1.value_at_full_time(-0.5, 600), -0.5)

    def test_small_samples_have_no_target(self):
        self.assertIsNone(step1.value_at_full_time(1.0, 99))
        self.assertIsNone(step1.value_at_full_time(1.0, 0))


class TestTables(unittest.TestCase):
    def test_load_table_parses_numbers_and_blanks(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("player_id,season,level,bbe,exit_velocity_avg\n5,2024,MLB,120,91.5\n6,2024,MLB,,\n")
            t = step1.load_table(p)
        self.assertEqual(t[(5, 2024)], {"bbe": 120.0, "exit_velocity_avg": 91.5})
        self.assertEqual(t[(6, 2024)], {"bbe": None, "exit_velocity_avg": None})

    def test_hitter_seasons_ignores_pitcher_labels(self):
        labels = {(1, "H"): [{"season": 2020, "value": 1.0, "pa": 300, "ip": 0.0}],
                  (1, "P"): [{"season": 2020, "value": 9.0, "pa": 0, "ip": 50.0}]}
        self.assertEqual(step1.hitter_seasons(labels), {1: {2020: (1.0, 300)}})


class TestMlbRows(unittest.TestCase):
    def test_filters_and_target(self):
        table = {(1, 2020): metrics_row(), (2, 2020): metrics_row(bbe=80.0),
                 (3, 2020): metrics_row(), (4, 2020): metrics_row()}
        seasons = {1: {2021: (1.0, 300)}, 2: {2021: (1.0, 300)}, 3: {2021: (1.0, 50)}, 4: {}}
        stats = {(p, 2020): stat(p, 2020) for p in (1, 2, 3, 4)}
        rows = step1.mlb_rows(table, seasons, stats, threshold=1.5)
        self.assertEqual([r["player_id"] for r in rows], [1])   # 2: <100 BBE; 3: <100 PA next; 4: no next season
        r = rows[0]
        self.assertAlmostEqual(r["target"], 2.0)
        self.assertEqual(r["weight"], 300.0)
        self.assertTrue(r["useful"])
        self.assertEqual(r["f"]["age"], 27)
        self.assertAlmostEqual(r["f"]["k"], 110 / 500)
        self.assertEqual(r["f"]["exit_velocity_avg"], 50.0)

    def test_complete_drops_rows_missing_a_key(self):
        rows = [{"f": {"a": 1.0, "b": None}}, {"f": {"a": 1.0, "b": 2.0}}]
        self.assertEqual(len(step1.complete(rows, ["a", "b"])), 1)

    def test_groups_cover_spray(self):
        self.assertIn("pull_percent", step1.GROUPS["spray"])
        self.assertEqual(step1.tracking_keys(["contact"]),
                         ["whiff_percent", "iz_contact_percent", "oz_contact_percent"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_step1` → `ImportError` (no `step1`).

- [ ] **Step 3: Implement** `psmodel/step1.py`:

```python
"""Step 1 of the prospect model: what hitter tracking metrics are worth, learned
on MLB and translated to AAA.

Tracking reached AAA only in 2022-23, too late for prospects with known careers,
so "batted-ball profile -> value" is learned from MLB (thousands of hitter-seasons
since 2015) and AAA readings are moved onto the MLB scale.
Spec: docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md.
"""
import csv

from . import features as F
from .savant import SPRAY_FIELDS

GROUPS = {
    "power": ["exit_velocity_avg", "avg_best_speed", "max_hit_speed", "hard_hit_percent", "barrel_batted_rate"],
    "launch": ["launch_angle_avg", "sweet_spot_percent", "groundballs_percent", "linedrives_percent",
               "flyballs_percent", "popups_percent"],
    "contact": ["whiff_percent", "iz_contact_percent", "oz_contact_percent"],
    "discipline": ["swing_percent", "oz_swing_percent", "z_swing_percent"],
    "spray": list(SPRAY_FIELDS),
}
BOX = ["k", "bb", "iso", "hr_pa", "obp", "slg"]
FULL_PA = 600
MIN_BBE = 100          # batted balls in season t for a row's metrics to count
MIN_PA_NEXT = 100      # the spec's peak-eligible floor, applied to the outcome season


def tracking_keys(groups=None):
    return [k for g in (GROUPS if groups is None else groups) for k in GROUPS[g]]


def _num(v):
    return None if v in (None, "") else float(v)


def load_table(path):
    """cache/{aaa,mlb}_tracking.csv -> {(player_id, season): {column: float | None}}."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(int(r["player_id"]), int(r["season"]))] = {
                k: _num(v) for k, v in r.items() if k not in ("player_id", "season", "level")}
    return out


def hitter_seasons(labels):
    """{player_id: {season: (value, pa)}} from dataset.load_labels output."""
    return {pid: {r["season"]: (r["value"], r["pa"]) for r in rows}
            for (pid, typ), rows in labels.items() if typ == "H"}


def value_at_full_time(value, pa):
    """SGP at 600 PA. Exact, because hitter_sgp scales linearly with playing time."""
    if not pa or pa < MIN_PA_NEXT:
        return None
    return value * FULL_PA / pa


def _features(metrics_row, stat_row):
    f = {k: metrics_row.get(k) for k in tracking_keys()}
    box = F.hitter_features(stat_row)
    f.update({k: box[k] for k in BOX})
    f["age"] = stat_row.get("age")
    return f


def mlb_rows(table, seasons, stats, threshold):
    """One row per MLB hitter with >=100 batted balls in t and >=100 PA in t+1.

    stats: {(player_id, season): StatsAPI hitter row} -- age and box score in t."""
    rows = []
    for (pid, t), m in table.items():
        if (m.get("bbe") or 0) < MIN_BBE:
            continue
        nxt = seasons.get(pid, {}).get(t + 1)
        st = stats.get((pid, t))
        target = value_at_full_time(*nxt) if nxt else None
        if target is None or st is None:
            continue
        rows.append({"player_id": pid, "season": t, "f": _features(m, st), "target": target,
                     "weight": float(nxt[1]), "useful": target >= threshold})
    return rows


def complete(rows, keys):
    return [r for r in rows if all(r["f"].get(k) is not None for k in keys)]
```

- [ ] **Step 4: Run** the full suite → 125 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): step 1 MLB rows with a value-at-600-PA target`.

---

### Task 5: AAA translation, prospect rows, Spearman interval

**Files:** Modify `psmodel/step1.py`, `tests/test_step1.py`, `docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md`

- [ ] **Step 1: Failing tests.** Append to `tests/test_step1.py` (above the `if __name__` line):

```python
class TestTranslation(unittest.TestCase):
    def test_offset_from_same_season_pairs(self):
        aaa = {(p, 2024): {"bbe": 100.0, "exit_velocity_avg": 90.0 + p} for p in range(10)}
        mlb = {(p, 2024): {"bbe": 60.0, "exit_velocity_avg": 89.0 + p} for p in range(10)}
        aaa[(99, 2024)] = {"bbe": 100.0, "exit_velocity_avg": 95.0}
        mlb[(99, 2024)] = {"bbe": 10.0, "exit_velocity_avg": 80.0}   # too few MLB batted balls
        t = step1.fit_translation(aaa, mlb, ["exit_velocity_avg"], n_boot=200)["exit_velocity_avg"]
        self.assertEqual(t["n"], 10)
        self.assertAlmostEqual(t["offset"], -1.0)
        self.assertAlmostEqual(t["lo"], -1.0)
        self.assertAlmostEqual(t["hi"], -1.0)
        self.assertAlmostEqual(t["slope"], 1.0)

    def test_metric_with_no_pairs(self):
        t = step1.fit_translation({}, {}, ["whiff_percent"])["whiff_percent"]
        self.assertEqual((t["n"], t["offset"]), (0, None))

    def test_translate_moves_only_translated_metrics(self):
        f = step1.translate({"exit_velocity_avg": 90.0, "obp": 0.35, "whiff_percent": None},
                            {"exit_velocity_avg": {"offset": -1.0}, "whiff_percent": {"offset": 2.0}})
        self.assertEqual(f, {"exit_velocity_avg": 89.0, "obp": 0.35, "whiff_percent": None})


class TestProspects(unittest.TestCase):
    def test_later_outcome_uses_only_later_qualifying_seasons(self):
        seasons = {7: {2022: (5.0, 600), 2024: (0.5, 300), 2025: (0.2, 80)}}
        self.assertEqual(step1.later_outcome(seasons, 7, 2022), (True, 1.0))
        self.assertEqual(step1.later_outcome(seasons, 8, 2022), (False, None))

    def test_aaa_rows_first_cohort_only(self):
        table = {(7, 2022): metrics_row(), (7, 2023): metrics_row(), (8, 2023): metrics_row(bbe=50.0)}
        stats = {k: stat(*k) for k in table}
        rows = step1.aaa_rows(table, stats, {7: {2024: (0.9, 600)}}, (2022, 2023), threshold=0.61)
        self.assertEqual([(r["player_id"], r["season"]) for r in rows], [(7, 2022)])
        self.assertTrue(rows[0]["arrived"])
        self.assertTrue(rows[0]["useful"])
        self.assertAlmostEqual(rows[0]["target"], 0.9)

    def test_spearman_ci(self):
        x = np.arange(50, dtype=float)
        rho, lo, hi = step1.spearman_ci(x, x * 2 + 1, n_boot=200)
        self.assertAlmostEqual(rho, 1.0)
        self.assertGreater(lo, 0.99)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_step1` → FAIL (`AttributeError: … 'fit_translation'`).

- [ ] **Step 3: Implement.** In `psmodel/step1.py` add `import random`, `import numpy as np` and `from scipy.stats import spearmanr` to the imports, add these constants under `MIN_PA_NEXT`:

```python
MIN_BBE_PAIR = 50      # batted balls at EACH level for a same-season translation pair
LAST_OUTCOME_SEASON = 2026
```

and append:

```python
def fit_translation(aaa, mlb, keys, min_bbe=MIN_BBE_PAIR, n_boot=1000, seed=0):
    """Per-metric AAA->MLB offset from hitters with both levels in the SAME season.

    A flat offset only. The MLB-on-AAA slope is reported, not applied: sampling
    noise in call-up-sized samples pulls it below 1 (errors-in-variables) whether
    or not the levels truly scale differently, so no held-out test can separate
    a real scale from noise."""
    pairs = [p for p in aaa if p in mlb
             and (aaa[p].get("bbe") or 0) >= min_bbe and (mlb[p].get("bbe") or 0) >= min_bbe]
    rng = random.Random(seed)
    out = {}
    for k in keys:
        pts = [(aaa[p][k], mlb[p][k], min(aaa[p]["bbe"], mlb[p]["bbe"])) for p in pairs
               if aaa[p].get(k) is not None and mlb[p].get(k) is not None]
        if not pts:
            out[k] = {"n": 0, "offset": None, "lo": None, "hi": None, "slope": None}
            continue
        a, b, w = (np.array(col, dtype=float) for col in zip(*pts))
        d = b - a
        boots = []
        for _ in range(n_boot):
            i = [rng.randrange(len(d)) for _ in range(len(d))]
            boots.append(float(np.average(d[i], weights=w[i])))
        slope = float(np.polyfit(a, b, 1, w=np.sqrt(w))[0]) if len(pts) >= 3 and np.ptp(a) > 0 else None
        out[k] = {"n": len(pts), "offset": float(np.average(d, weights=w)),
                  "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5)),
                  "slope": slope}
    return out


def translate(f, translation):
    """AAA feature dict -> MLB scale; metrics without an offset pass through."""
    out = dict(f)
    for k, t in translation.items():
        if out.get(k) is not None and t.get("offset") is not None:
            out[k] = out[k] + t["offset"]
    return out


def later_outcome(seasons, pid, season):
    """(arrived, best value at 600 PA) over MLB seasons after `season` with >=100 PA."""
    vals = [value_at_full_time(v, pa) for s, (v, pa) in seasons.get(pid, {}).items()
            if season < s <= LAST_OUTCOME_SEASON]
    vals = [x for x in vals if x is not None]
    return (bool(vals), max(vals) if vals else None)


def aaa_rows(table, stats, seasons, cohort_seasons, threshold):
    """AAA hitter-seasons with >=100 batted balls in the cohort seasons, keeping each
    player's FIRST qualifying season so nobody counts twice in the gate."""
    seen, rows = set(), []
    for pid, s in sorted(table, key=lambda k: (k[1], k[0])):
        m = table[(pid, s)]
        st = stats.get((pid, s))
        if s not in cohort_seasons or pid in seen or (m.get("bbe") or 0) < MIN_BBE or st is None:
            continue
        seen.add(pid)
        arrived, best = later_outcome(seasons, pid, s)
        rows.append({"player_id": pid, "season": s, "f": _features(m, st), "arrived": arrived,
                     "target": best, "useful": best is not None and best >= threshold})
    return rows


def spearman_ci(x, y, n_boot=2000, seed=0):
    """Spearman rho with a percentile bootstrap 95% interval."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        boots.append(float(spearmanr(x[i], y[i]).statistic))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return float(spearmanr(x, y).statistic), float(lo), float(hi)
```

- [ ] **Step 4: Run** the full suite → 131 pass.

- [ ] **Step 5: Spec refinement.** In `docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md` replace

```
reports it. Per metric: a **flat offset** by default (e.g. AAA EV reads about
1 mph high → subtract it). A scaling factor is added only if its bootstrap
interval excludes 1 **and** it improves the fit on held-out players. Same player
```

with

```
reports it. Per metric: a **flat offset** (e.g. AAA EV reads about 1 mph high →
subtract it). The MLB-on-AAA slope is **reported, not applied**: sampling noise in
call-up-sized samples pulls it below 1 (errors-in-variables) whether or not the
levels truly scale differently, so a held-out test can't tell a real scale from
noise. Same player
```

- [ ] **Step 6: Commit** `feat(prospects-model): AAA-to-MLB translation and prospect rows for step 1`.

---

### Task 6: Interaction strength

**Files:** Create `psmodel/interactions.py`, `tests/test_interactions.py`

- [ ] **Step 1: Failing tests** — `tests/test_interactions.py`:

```python
import unittest

import numpy as np

from psmodel import interactions


class Stub:
    """f = x0 * x1 + x2: one pure interaction (0, 1), everything else additive."""
    def predict(self, X):
        return X[:, 0] * X[:, 1] + X[:, 2]


class TestH(unittest.TestCase):
    def setUp(self):
        self.X = np.random.default_rng(0).uniform(-1, 1, size=(60, 3))

    def test_product_term_is_an_interaction(self):
        self.assertGreater(interactions.h_stat(Stub(), self.X, 0, 1), 0.2)

    def test_additive_pair_is_not(self):
        self.assertLess(interactions.h_stat(Stub(), self.X, 0, 2), 1e-9)

    def test_top_pairs_ranks_the_product_first(self):
        top = interactions.top_pairs(Stub(), self.X, ["a", "b", "c"], n=3)
        self.assertEqual((top[0][1], top[0][2]), ("a", "b"))
        self.assertEqual(len(top), 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_interactions` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/interactions.py`:

```python
"""Pairwise interaction strength: Friedman's H, unnormalized.

For features j and k, the part of their joint partial dependence that is NOT the
sum of their separate effects. Unnormalized (in target units, SGP) so pairs rank by
how much value the interaction moves; the normalized H ranks tiny effects as
highly as large ones.
"""
import numpy as np


def _pd(model, X, cols):
    """Partial dependence at each row's values of `cols`, averaged over X as the
    background: one predict call on len(X) ** 2 rows."""
    n = len(X)
    big = np.tile(X, (n, 1))
    for c in cols:
        big[:, c] = np.repeat(X[:, c], n)
    p = model.predict(big).reshape(n, n).mean(axis=1)
    return p - p.mean()


def h_stat(model, X, j, k, cache=None):
    cache = {} if cache is None else cache
    for c in (j, k):
        if c not in cache:
            cache[c] = _pd(model, X, [c])
    resid = _pd(model, X, [j, k]) - cache[j] - cache[k]
    return float(np.sqrt(np.mean(resid ** 2)))


def top_pairs(model, X, keys, n=10):
    """[(strength, key_j, key_k)] strongest first."""
    cache = {}
    scores = [(h_stat(model, X, j, k, cache), keys[j], keys[k])
              for j in range(len(keys)) for k in range(j + 1, len(keys))]
    return sorted(scores, key=lambda t: -t[0])[:n]
```

- [ ] **Step 4: Run** the full suite → 134 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): pairwise interaction strength (Friedman's H)`.

---

### Task 7: The step-1 run — tests, prospect gate, report

**Files:** Create `step1_run.py`

- [ ] **Step 1: Create** `step1_run.py`:

```python
"""Step 1 of the prospect model: what hitter tracking metrics are worth, learned on
MLB, translated to AAA, and checked on real prospects.

Usage:  python step1_run.py
Writes cache/step1_report.txt, cache/aaa_translation.csv and cache/step1_choice.json
(gitignored). Network: StatsAPI AAA season stats 2022-2024 (age, box score) on the
first run, cached after. Run the security audit first.
"""
import csv
import json
import os
import statistics

import numpy as np
from scipy.stats import spearmanr

from psmodel import dataset, evaluate, interactions, statsapi, step1

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "step1_report.txt")
TRANSLATION = os.path.join(CACHE, "aaa_translation.csv")
CHOICE = os.path.join(CACHE, "step1_choice.json")
SEEDS = 10
MLB_FIRST, MLB_LAST = 2015, 2025        # season t; outcomes run through 2026
GATE_COHORTS, LATE_COHORT = (2022, 2023), (2024,)
SPRAY = set(step1.GROUPS["spray"])


def stats_index(sport_id, seasons):
    out = {}
    for s in seasons:
        for r in statsapi.season_stats(s, "hitting", sport_id):
            if (r["player_id"], s) in out:
                raise SystemExit(f"duplicate StatsAPI row for {r['player_id']} in {s} (sport {sport_id})")
            out[(r["player_id"], s)] = r
    return out


def mean(results, key):
    return statistics.fmean(r[key] for r in results)


def mean_oof_rho(rows, keys, kind):
    y = [r["target"] for r in rows]
    return statistics.fmean(float(spearmanr(evaluate.oof_predictions(rows, keys, 5, s, kind), y).statistic)
                            for s in range(SEEDS))


def adoption_line(name, res):
    ok, wins = evaluate.adopt(res)
    return ok, (f"  {name:26} {'ADOPTED' if ok else 'rejected':9} {wins:2d}/10  "
                f"rho {mean(res, 'rho_base'):.4f} -> {mean(res, 'rho_fam'):.4f}  "
                f"top-50 {mean(res, 'top_base'):.3f} -> {mean(res, 'top_fam'):.3f}")


def main():
    L = []
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    threshold = dataset.useful_threshold(labels, "H")
    seasons = step1.hitter_seasons(labels)
    mlb = step1.load_table(os.path.join(CACHE, "mlb_tracking.csv"))
    aaa = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    mlb_stats = stats_index(statsapi.MLB, range(MLB_FIRST, MLB_LAST + 1))

    all_keys = ["age"] + step1.tracking_keys()
    built = step1.mlb_rows({k: v for k, v in mlb.items() if MLB_FIRST <= k[1] <= MLB_LAST},
                           seasons, mlb_stats, threshold)
    rows = step1.complete(built, all_keys + step1.BOX)
    L += ["STEP 1 -- what hitter tracking metrics are worth (learned on MLB)",
          f"rows: {len(rows)} hitter-seasons ({len(built) - len(rows)} dropped for a missing metric), "
          f"{len({r['player_id'] for r in rows})} players, seasons t={MLB_FIRST}-{MLB_LAST}",
          f"target: next-season 4x4 SGP at 600 PA; useful = >= {threshold:.3f} "
          f"({sum(r['useful'] for r in rows)} useful rows)", ""]

    kind_rho = {kind: mean_oof_rho(rows, all_keys, kind) for kind in evaluate.KINDS}
    kind = max(kind_rho, key=kind_rho.get)
    L += ["1. Model: " + ", ".join(f"{k} rho {v:.4f}" for k, v in kind_rho.items()) + f"  -> using {kind}", ""]

    L.append("2. Which groups earn their place (each vs age + all OTHER groups, 8/10 rule):")
    adopted = []
    for g in step1.GROUPS:
        others = [k for h in step1.GROUPS if h != g for k in step1.GROUPS[h]]
        ok, line = adoption_line(g, evaluate.compare(rows, ["age"] + others, step1.GROUPS[g],
                                                     seeds=SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted.append(g)
    if "power" not in adopted and "launch" not in adopted:
        others = [k for h in step1.GROUPS if h not in ("power", "launch") for k in step1.GROUPS[h]]
        ok, line = adoption_line("power + launch (jointly)", evaluate.compare(
            rows, ["age"] + others, step1.GROUPS["power"] + step1.GROUPS["launch"], seeds=SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted += ["power", "launch"]
    final_keys = ["age"] + step1.tracking_keys(adopted)
    L += [f"  adopted groups: {adopted or 'NONE'}", ""]

    if len(final_keys) > 1:
        box_base = ["age"] + step1.BOX
        ok, line = adoption_line("tracking on top of box", evaluate.compare(
            rows, box_base, step1.tracking_keys(adopted), seeds=SEEDS, kind=kind))
        L += ["3. Tracking vs box score (report only):",
              f"  box score + age alone      rho {mean_oof_rho(rows, box_base, kind):.4f}",
              f"  tracking + age alone       rho {mean_oof_rho(rows, final_keys, kind):.4f}", line, ""]

        L.append("4. Robustness (adopted tracking vs age alone):")
        for name, drop in (("without 2015", lambda r: r["season"] == 2015),
                           ("without 2020", lambda r: r["season"] in (2019, 2020))):
            sub = [r for r in rows if not drop(r)]
            L.append(adoption_line(name, evaluate.compare(sub, ["age"], step1.tracking_keys(adopted),
                                                          seeds=SEEDS, kind=kind))[1])
        L.append("")

        L.append("5. Strongest interactions (gbm, unnormalized H in SGP; finding = top-10 in >=8/10 runs):")
        counts, strength = {}, {}
        for s in range(SEEDS):
            folds = evaluate.assign_folds(rows, 5, s)
            train = [r for r, f in zip(rows, folds) if f != 0]
            m = evaluate.fit(train, final_keys, "gbm")
            idx = np.random.default_rng(s).choice(len(train), size=min(100, len(train)), replace=False)
            X = np.array([[train[i]["f"][k] for k in final_keys] for i in idx], dtype=float)
            for h, a, b in interactions.top_pairs(m, X, final_keys, n=10):
                counts[(a, b)] = counts.get((a, b), 0) + 1
                strength.setdefault((a, b), []).append(h)
        for (a, b), c in sorted(counts.items(), key=lambda t: (-t[1], -statistics.fmean(strength[t[0]])))[:10]:
            L.append(f"  {a} x {b}: strength {statistics.fmean(strength[(a, b)]):.3f}, top-10 in {c}/10 "
                     f"-> {'finding' if c >= 8 else 'hypothesis'}")
        L.append("")

    tkeys = [k for k in step1.tracking_keys() if k not in SPRAY]
    translation = step1.fit_translation(aaa, mlb, tkeys)
    with open(TRANSLATION, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "n", "offset", "lo", "hi", "slope_reported_not_applied"])
        for k in tkeys:
            t = translation[k]
            w.writerow([k, t["n"], t["offset"], t["lo"], t["hi"], t["slope"]])
    L.append("6. AAA -> MLB translation (same-season two-level hitters, >=50 batted balls at each level):")
    for k in tkeys:
        t = translation[k]
        L.append(f"  {k:22} n={t['n']:3d}  " + (
            f"offset {t['offset']:+.3f} [{t['lo']:+.3f}, {t['hi']:+.3f}]  slope {t['slope'] or float('nan'):.2f}"
            if t["offset"] is not None else "no pairs"))
    L.append("")

    score_keys = [k for k in final_keys if k not in SPRAY]
    box_base = ["age"] + step1.BOX
    model, box_model = evaluate.fit(rows, score_keys, kind), evaluate.fit(rows, box_base, kind)
    # 3c rebuilds the score from these choices (refit on demand; nothing serialized but JSON).
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "adopted": adopted, "score_keys": score_keys,
                   "threshold": threshold, "mlb_seasons": [MLB_FIRST, MLB_LAST]}, fh, indent=2)
    aaa_stats = stats_index(statsapi.AAA, GATE_COHORTS + LATE_COHORT)
    gate_pass = False
    L.append(f"7. Prospect check -- AAA hitters scored on {score_keys} (spray excluded: not measurable in AAA)")
    for name, cohorts, gates in (("2022-23 (GATE)", GATE_COHORTS, True), ("2024 (report only)", LATE_COHORT, False)):
        pr = step1.complete(step1.aaa_rows(aaa, aaa_stats, seasons, cohorts, threshold), score_keys + box_base)
        arr = [i for i, r in enumerate(pr) if r["arrived"]]
        L.append(f"  {name}: {len(pr)} AAA hitters, {len(arr)} reached 100+ MLB PA, "
                 f"{sum(r['useful'] for r in pr)} became starter-quality")
        if len(arr) < 10:
            L.append("    too few arrivals to test")
            continue
        for r in pr:
            r["f"] = step1.translate(r["f"], translation)
        score = evaluate.predict(model, pr, score_keys)
        box = evaluate.predict(box_model, pr, box_base)
        ops = np.array([r["f"]["obp"] + r["f"]["slg"] for r in pr])
        outcome = [pr[i]["target"] for i in arr]
        for label, s in (("tracking score", score), ("box-score model", box), ("AAA OPS", ops)):
            rho, lo, hi = step1.spearman_ci(s[arr], outcome)
            L.append(f"    {label:16} Spearman vs later MLB value {rho:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            if gates and label == "tracking score":
                gate_pass = lo > 0
        order = np.argsort(-score)
        for q, chunk in enumerate(np.array_split(order, 5), 1):
            L.append(f"    score quintile {q}: arrived {np.mean([pr[i]['arrived'] for i in chunk]):.2f}, "
                     f"starter-quality {np.mean([pr[i]['useful'] for i in chunk]):.2f}")
    L.append("")

    if "spray" in adopted:
        L.append("SPRAY: ADOPTED on MLB -- the user's hypothesis holds there. AAA scoring leaves it out until "
                 "the follow-up spray-parity plan (our coordinate-based version vs Savant on the 2023-26 "
                 "MLB game records).")
    else:
        L.append("SPRAY: not adopted -- direction adds nothing beyond the other groups on MLB. No follow-up.")
    L.append("GATE: " + ("PASS -- the tracking score ranks later MLB success above chance; 3c may use it"
                         if gate_pass else "FAIL -- stop; do not hand the score to 3c until resolved"))

    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run** the full suite → 134 pass (the driver has no unit tests; its pieces do).

- [ ] **Step 3: Security audit** (Task 1 Step 1 commands). This run fetches AAA season stats for 2022–2024 from `statsapi.mlb.com` (about 6 requests).

- [ ] **Step 4: Run** `python step1_run.py` (expect several minutes: about 1,000 model fits). Sanity checks before trusting it:
  - Section 1: rows in the low thousands (≈350–450 qualifying hitters × 11 seasons, minus those without 100 PA next season).
  - Section 6: EV offset is small (within ±3 mph), and `n` is at least ~100 for most metrics. If most metrics have n < 50, report it: the translation is thin.
  - If the run stops on `duplicate StatsAPI row`, stop and report (AAA traded-player splits need aggregating; don't guess).
  - **GATE FAIL:** do not loosen it. Report the section 7 numbers to the user and stop.

- [ ] **Step 5: Commit** `feat(prospects-model): step 1 tracking-score run and prospect gate` (the driver; the report and translation live in gitignored `cache/`).

- [ ] **Step 6: Record results.** Add a "Step 1 result (run <date>)" section to the step-1 spec with: model choice, adopted groups (and the spray verdict in plain words for the user), tracking vs box score, robustness, the top interactions labeled finding/hypothesis, translation highlights (EV, whiff, barrel offsets and n), and the gate numbers. Update `project_prospect_model.md` in memory with the verdict and next step. Commit `docs(spec): record step 1 result`. Tell the user the verdict. If spray was adopted, tell them the follow-up spray-parity plan is next (design on Opus). Otherwise 3c is next.

---

## Not in this plan

- **AAA spray (only if section 2 adopts spray).** A follow-up plan checks whether our coordinate-based spray, especially pulled-air, reproduces Savant's on the 2023–26 MLB game records already on disk (r ≥ 0.98, plan A's bar). It's written after this run because its definitions depend on Task 1's field discovery and its existence depends on section 2.
- Pitchers (same pipeline, next); ratings and UI (3c); historic FV grades (3c, one-year ID-join test first); MLB game records for 2015–22.
