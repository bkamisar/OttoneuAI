# 3c-hitters Plan B: Tracking Layer, Sealed 2024 Check, Ratings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the hitter prospect model:
- test the tree leads as explicit terms;
- run the pulled-air parity check;
- open the sealed 2024 cohort exactly once (it decides "soon"'s marginal contact+approach pair and whether tracking helps "soon");
- re-run step 1's prospect gate as-of;
- fit everything as of 2026 and write `cache/hitter_ratings.csv`.

**Architecture:**
- `walkforward.py` gains a production fit (no player isolation) and out-of-fold predictions.
- `cohorts.py` gains raw age and the lead product terms.
- `tracking_layer.py` refits step 1 as-of a vantage, scores AAA hitters, residualizes the score against the base prediction, and estimates a trust weight with a player-bootstrap interval.
- `spray.py` + `pulled_air_parity.py` settle the pulled-air question.
- `model3c_final.py` runs it all.

**Tech Stack:** Python 3.14 stdlib + numpy, scipy, sklearn (already used). Tests: stdlib `unittest`. **No new network:** everything reads the cache.

**Spec:** `docs/superpowers/specs/2026-09-27-3c-hitters-design.md` (Part 3 and "Plan A result").

---

## Context the implementer needs

- Run from `prospects-model/`. Tests: `python -m unittest discover -s tests` (**159 pass, 3 skipped** before this plan).
- **As-of, still.** Every vantage-V fit uses only data through V, including the step-1 MLB model (MLB rows whose outcome season is ≤ V) and the AAA→MLB offsets (pairs in seasons ≤ V). **Production** (V = 2026) trains on every cohort whose answer is known by 2026 and does **not** isolate players: nothing is being evaluated there, so all known history is fair game.
- **The sealed 2024 cohort is opened exactly once, in Task 5**, for "soon" only (the rating's 4-year answers for 2024 aren't in yet). Two decisions are made there by rules written *before* opening it:
  1. Soon's contact+approach pair is kept only if its 2024 AUC gain is ≥1 SE and top-50 doesn't fall by more than 0.04.
  2. Tracking is used for "soon" only if its trust-weight interval (trained on AAA 2022) excludes 0 **and** its 2024 AUC gain on AAA hitters is ≥1 SE.
- **Inputs (all cached):**
  - `cache/labels.csv` (2013–2026, 2026 refreshed);
  - `cache/mlb_tracking.csv` / `cache/aaa_tracking.csv` (step 1);
  - `cache/step1_choice.json` (ridge, `score_keys`, threshold);
  - `cache/model3c_choice.json` (plan A: kind, adopted groups, keys per output);
  - MLB game records 2023–2026 in `cache/pbp_live/{season}/1/`;
  - StatsAPI MLB 2015–2025 and AAA 2022–2026 season stats in the HTTP cache.
- **Adoption rule** (`walkforward.adopt`): win = rank gain ≥ 1 SE (paired player bootstrap) at ≥2 of 3 vantages, no vantage ≤ −2 SE, mean top-50 change ≥ −0.04.
- **Security posture:** this plan should make no network requests. Run the standard audit before Task 5 anyway (a cache miss would fetch):

```bash
tasklist 2>/dev/null | grep -i python || echo "no stray python"
grep -rhoE "https?://[a-zA-Z0-9.-]+" psmodel/*.py *.py | sort -u
grep -rniE "api[_-]?key|password|token|secret|authorization" psmodel/*.py *.py || echo "no credentials"
git ls-files cache | wc -l
```

- Commits are local only; end each message with `Co-Authored-By: <current model> <noreply@anthropic.com>`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `psmodel/walkforward.py` | Modify | `frames(..., isolate=True)`, `production()`, `oof()` |
| `psmodel/cohorts.py` | Modify | `age_raw` on rows; `LEADS`; `add_products()` |
| `psmodel/tracking_layer.py` | Create | As-of step 1, AAA scores, residualize, trust weight, adjust |
| `psmodel/spray.py` | Create | Spray angle from charted coordinates; pull% and FB% per batter |
| `pulled_air_parity.py` | Create | Our pull×FB vs Savant's on MLB 2023–26 → `cache/pulled_air_parity.json` |
| `model3c_final.py` | Create | The final run → report, decisions JSON, `hitter_ratings.csv` |
| `tests/test_walkforward.py`, `tests/test_cohorts.py` | Modify | New tests |
| `tests/test_tracking_layer.py`, `tests/test_spray.py` | Create | Unit tests |

---

### Task 1: Production fits and out-of-fold predictions

**Files:** Modify `psmodel/walkforward.py`, `tests/test_walkforward.py`

- [ ] **Step 1: Failing tests.** Append to `tests/test_walkforward.py`, above `if __name__`:

```python
class TestProduction(unittest.TestCase):
    def test_production_keeps_every_known_player(self):
        rows = cohort_rows(n=100)
        for season in (2014, 2019):
            rows.append({"player_id": 999, "season": season, "sport_id": 12,
                         "f": {"x": 0.0, "z": 0.0}, "mlb": []})
        m, train, test, pred = W.production(rows, ["x"], "rating", "ridge", 0.5, 2019)
        self.assertIn(999, {r["player_id"] for r in train})
        self.assertEqual(max(r["season"] for r in train), 2015)
        self.assertEqual(len(pred), len(test))

    def test_oof_predictions_track_the_signal(self):
        train, _ = W.frames(cohort_rows(), "rating", 2022, 0.5, ["x"])
        p = W.oof(train, ["x"], "rating", "ridge")
        self.assertEqual(len(p), len(train))
        self.assertGreater(np.corrcoef(p, [r["f"]["x"] for r in train])[0, 1], 0.95)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_walkforward` → FAIL (`AttributeError: … 'production'`).

- [ ] **Step 3: Implement.** In `psmodel/walkforward.py` change the `frames` signature and its `ids` line:

```python
def frames(rows, target, v, bar, keys, unseal=False, isolate=True):
    """(train, test) at vantage v, complete on keys, with targets attached as 'y'.
    isolate=False (production only) keeps test players' earlier rows in training."""
```

```python
    ids = {r["player_id"] for r in test} if isolate else set()
```

and append:

```python
def production(rows, keys, target, kind, bar, v):
    """Fit on every cohort whose answer is known by v, using ALL players (nothing is
    being evaluated), and predict cohort v. Returns (model, train, test, pred)."""
    train, test = frames(rows, target, v, bar, keys, unseal=True, isolate=False)
    evaluate.guard_features(train, keys)
    m, pred = fit_predict(train, test, keys, target, kind)
    return m, train, test, pred


def oof(train, keys, target, kind, k=5, seed=0):
    """Out-of-fold predictions for training rows (player-grouped folds), so a
    second-stage fit on them isn't fooled by in-sample fit."""
    folds = np.array(evaluate.assign_folds(train, k, seed))
    pred = np.zeros(len(train))
    for f in range(k):
        te = np.where(folds == f)[0]
        m = _model(target, kind).fit(_X([r for r, g in zip(train, folds) if g != f], keys),
                                     np.array([r["y"] for r, g in zip(train, folds) if g != f]))
        Xt = _X([train[i] for i in te], keys)
        pred[te] = m.predict_proba(Xt)[:, 1] if target == "soon" else m.predict(Xt)
    return pred
```

- [ ] **Step 4: Run** the full suite → 161 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): production fits and out-of-fold predictions`.

---

### Task 2: Raw age and the lead terms

**Files:** Modify `psmodel/cohorts.py`, `tests/test_cohorts.py`

- [ ] **Step 1: Failing tests.** Append to class `TestBuildRows` in `tests/test_cohorts.py`:

```python
    def test_raw_age_kept_beside_the_standardized_one(self):
        self.assertEqual(self.by[(1, 2018, 12)]["age_raw"], 22)

    def test_lead_products(self):
        rows = [{"f": {"age": 2.0, "slg": 1.5, "swstr": None}}]
        cohorts.add_products(rows)
        self.assertEqual(rows[0]["f"]["age_x_slg"], 3.0)
        self.assertIsNone(rows[0]["f"]["swstr_x_slg"])
```

- [ ] **Step 2: Run** `python -m unittest tests.test_cohorts` → FAIL (`KeyError: 'age_raw'`).

- [ ] **Step 3: Implement.** In `psmodel/cohorts.py`, below `_BOX`, add:

```python
# Tree patterns from plan A, tested as explicit terms (products of standardized features).
LEADS = {"age_x_slg": ("age", "slg"), "swstr_x_slg": ("swstr", "slg")}


def add_products(rows):
    for r in rows:
        f = r["f"]
        for name, (a, b) in LEADS.items():
            f[name] = f[a] * f[b] if f.get(a) is not None and f.get(b) is not None else None
    return rows
```

In `build_rows`, change the `rows.append({...})` call to include the raw age:

```python
        rows.append({"player_id": pid, "name": r["name"], "season": s, "sport_id": r["sport_id"],
                     "age_raw": r.get("age"), "f": f, "mlb": mlb_seasons.get(pid, [])})
```

- [ ] **Step 4: Run** the full suite → 163 pass. (`test_mlb_attached_and_groups_cover_every_feature` still passes: products are only added by `add_products`.)
- [ ] **Step 5: Commit** `feat(prospects-model): raw age and lead product terms for 3c`.

---

### Task 3: The tracking layer

**Files:** Create `psmodel/tracking_layer.py`, `tests/test_tracking_layer.py`

- [ ] **Step 1: Failing tests** — `tests/test_tracking_layer.py`:

```python
import unittest

import numpy as np

from psmodel import tracking_layer as TL


class Stub:
    def predict(self, X):
        return X[:, 1]


def stat(pid, season):
    return {"player_id": pid, "season": season, "sport_id": 11, "age": 24, "pa": 400, "ab": 360, "h": 100,
            "hr": 15, "r": 50, "bb": 35, "so": 90, "sb": 5, "obp": 0.34, "slg": 0.45, "np": 1600,
            "swings": 800, "whiffs": 200}


class TestScores(unittest.TestCase):
    def test_scores_translated_rows_with_enough_batted_balls(self):
        aaa = {(1, 2024): {"bbe": 150.0, "exit_velocity_avg": 90.0},
               (2, 2024): {"bbe": 50.0, "exit_velocity_avg": 95.0},
               (3, 2021): {"bbe": 150.0, "exit_velocity_avg": 95.0}}
        stats = {k: stat(*k) for k in aaa}
        got = TL.aaa_scores(aaa, stats, Stub(), {"exit_velocity_avg": {"offset": -1.0}},
                            ["age", "exit_velocity_avg"], {2024})
        self.assertEqual(got, {(1, 2024): 89.0})


class TestResidual(unittest.TestCase):
    def test_residual_is_uncorrelated_with_base(self):
        rng = np.random.default_rng(0)
        base = rng.normal(size=500)
        resid, (a, b) = TL.residualize(2 * base + rng.normal(size=500), base)
        self.assertAlmostEqual(float(np.corrcoef(resid, base)[0, 1]), 0.0, places=6)
        self.assertAlmostEqual(b, 2.0, delta=0.15)


class TestWeights(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1)
        self.n = 3000

    def test_rating_weight_recovers_signal(self):
        base, resid = self.rng.normal(size=self.n), self.rng.normal(size=self.n)
        y = base + 0.5 * resid + 0.1 * self.rng.normal(size=self.n)
        w, lo, hi = TL.trust_weight("rating", y, base, resid, np.ones(self.n), np.arange(self.n), n_boot=200)
        self.assertAlmostEqual(w, 0.5, delta=0.05)
        self.assertGreater(lo, 0.0)

    def test_soon_weight_recovers_signal(self):
        base = self.rng.uniform(0.02, 0.5, size=self.n)
        resid = self.rng.normal(size=self.n)
        p = 1 / (1 + np.exp(-(np.log(base / (1 - base)) + resid)))
        y = (self.rng.uniform(size=self.n) < p).astype(float)
        w, lo, hi = TL.trust_weight("soon", y, base, resid, np.ones(self.n), np.arange(self.n), n_boot=200)
        self.assertAlmostEqual(w, 1.0, delta=0.25)
        self.assertGreater(lo, 0.0)

    def test_no_signal_interval_covers_zero(self):
        base, e, r = (self.rng.normal(size=400) for _ in range(3))
        resid = r - (r @ e) / (e @ e) * e          # exactly uncorrelated with y - base
        w, lo, hi = TL.trust_weight("rating", base + e, base, resid, np.ones(400), np.arange(400), n_boot=300)
        self.assertAlmostEqual(w, 0.0, places=9)
        self.assertLess(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_adjust(self):
        self.assertTrue(np.allclose(TL.adjust("rating", np.array([1.0]), np.array([2.0]), 0.5), [2.0]))
        self.assertAlmostEqual(float(TL.adjust("soon", np.array([0.5]), np.array([1.0]), np.log(3.0))[0]), 0.75)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_tracking_layer` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/tracking_layer.py`:

```python
"""The tracking layer: a hitter's base prediction moves by the part of his step-1
tracking score that the base prediction doesn't already explain, times a trust
weight learned from AAA cohorts whose answers were known at the vantage.

Everything is as-of: step 1 is refit on MLB rows whose outcome season is <= v, and
the AAA->MLB offsets use same-season pairs in seasons <= v.
"""
import numpy as np

from . import evaluate, step1

MIN_AAA_BBE = step1.MIN_BBE


def step1_keys(choice):
    """Step-1 features usable in AAA: the chosen keys minus Savant-only spray."""
    return [k for k in choice["score_keys"] if k not in step1.GROUPS["spray"]]


def step1_model(v, mlb_table, seasons, mlb_stats, keys, kind):
    """Step 1 refit as-of v: MLB rows whose outcome season (t+1) is <= v."""
    rows = step1.complete(step1.mlb_rows({k: m for k, m in mlb_table.items() if k[1] <= v - 1},
                                         seasons, mlb_stats, threshold=0.0), keys)
    return evaluate.fit(rows, keys, kind)


def offsets(v, aaa_table, mlb_table, keys):
    """AAA->MLB offsets from same-season pairs in seasons <= v."""
    return step1.fit_translation({k: m for k, m in aaa_table.items() if k[1] <= v},
                                 {k: m for k, m in mlb_table.items() if k[1] <= v}, keys)


def aaa_scores(aaa_table, aaa_stats, model, translation, keys, seasons_wanted):
    """{(player_id, season): tracking score} for AAA rows with >=100 batted balls."""
    out = {}
    for (pid, s), m in aaa_table.items():
        st = aaa_stats.get((pid, s))
        if s not in seasons_wanted or st is None or (m.get("bbe") or 0) < MIN_AAA_BBE:
            continue
        f = step1.translate(step1._features(m, st), translation)
        if all(f.get(k) is not None for k in keys):
            out[(pid, s)] = float(evaluate.predict(model, [{"f": f}], keys)[0])
    return out


def residualize(score, base):
    """The part of the score a straight line on the base prediction doesn't explain.
    Returns (resid, (a, b)); apply the same line to new rows: score - (a + b * base)."""
    b, a = np.polyfit(base, score, 1)
    return score - (a + b * base), (float(a), float(b))


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _w_ls(y, base, resid, wt):
    den = float(np.sum(wt * resid ** 2))
    return float(np.sum(wt * resid * (y - base)) / den) if den > 0 else 0.0


def _w_logit(y, base, resid, wt, iters=100):
    """One-coefficient logistic fit with the base log-odds as a fixed offset."""
    o, w = _logit(base), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(o + w * resid)))
        h = float(np.sum(wt * resid ** 2 * p * (1 - p)))
        if h <= 0:
            break
        step = float(np.clip(np.sum(wt * resid * (y - p)) / h, -1.0, 1.0))
        w += step
        if abs(step) < 1e-10:
            break
    return w


def trust_weight(target, y, base, resid, wt, pids, n_boot=1000, seed=0):
    """(w, lo, hi): the adjustment weight and a player-bootstrap 95% interval."""
    fit = _w_logit if target == "soon" else _w_ls
    y, base, resid, wt, pids = (np.asarray(a) for a in (y, base, resid, wt, pids))
    w = fit(y, base, resid, wt)
    uniq = np.unique(pids)
    rows_of = {p: np.where(pids == p)[0] for p in uniq}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = np.concatenate([rows_of[p] for p in rng.choice(uniq, len(uniq))])
        boots.append(fit(y[i], base[i], resid[i], wt[i]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(w), float(lo), float(hi)


def adjust(target, base, resid, w):
    if target == "soon":
        return 1 / (1 + np.exp(-(_logit(base) + w * resid)))
    return base + w * resid
```

- [ ] **Step 4: Run** the full suite → 169 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): as-of tracking layer with trust weights`.

---

### Task 4: Pulled-air parity

**Files:** Create `psmodel/spray.py`, `tests/test_spray.py`, `pulled_air_parity.py`

- [ ] **Step 1: Failing tests** — `tests/test_spray.py`:

```python
import unittest

from psmodel import spray


def e(x, y, side="R", traj="fly_ball", code="X"):
    return {"batter": 1, "code": code, "ev": 95.0, "traj": traj, "hc_x": x, "hc_y": y, "bat_side": side}


class TestSpray(unittest.TestCase):
    def test_angle_mirrors_lefties(self):
        self.assertLess(spray.angle(e(60.0, 100.0)), -15.0)            # RHB to left field: pulled
        self.assertGreater(spray.angle(e(60.0, 100.0, "L")), 15.0)     # LHB, same spot: opposite
        self.assertIsNone(spray.angle(e(None, 100.0)))

    def test_pull_and_fb(self):
        events = [e(60.0, 100.0), e(60.0, 100.0, traj="ground_ball"), e(125.42, 100.0),
                  e(190.0, 100.0, traj="line_drive"), e(60.0, 100.0, code="F")]   # a foul isn't a batted ball
        pull, fb, n = spray.pull_and_fb(events)[1]
        self.assertEqual(n, 4)
        self.assertAlmostEqual(pull, 50.0)
        self.assertAlmostEqual(fb, 50.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_spray` → `ImportError`.

- [ ] **Step 3: Implement** `psmodel/spray.py`:

```python
"""Spray direction from charted hit coordinates (Gameday coordX/coordY), with plan
A's geometry: home plate at (125.42, 198.27), angle mirrored for left-handed
batters, pulled = more than 15 degrees to the pull side. Plan A found overall
pull% from these coordinates caps near r 0.96 vs Savant; pulled_air_parity.py
tests whether pull% x FB% does better.
"""
import math

from .metrics import IN_PLAY

HOME_X, HOME_Y = 125.42, 198.27


def angle(e):
    x, y, side = e.get("hc_x"), e.get("hc_y"), e.get("bat_side")
    if x is None or y is None or side not in ("R", "L") or y >= HOME_Y:
        return None
    a = math.degrees(math.atan((x - HOME_X) / (HOME_Y - y)))
    return -a if side == "L" else a


def pull_and_fb(events, pull_deg=15.0):
    """{batter: (pull %, fly-ball %, batted balls)}. Bunts are included, as in Savant's rates."""
    acc = {}
    for e in events:
        if e.get("code") not in IN_PLAY or e.get("ev") is None:
            continue
        a = acc.setdefault(e["batter"], [0, 0, 0, 0])      # batted balls, with angle, pulled, fly balls
        a[0] += 1
        ang = angle(e)
        if ang is not None:
            a[1] += 1
            a[2] += ang < -pull_deg
        a[3] += e.get("traj") == "fly_ball"
    return {b: (100.0 * a[2] / a[1] if a[1] else None, 100.0 * a[3] / a[0], a[0]) for b, a in acc.items()}
```

- [ ] **Step 4:** Create `pulled_air_parity.py`:

```python
"""Pulled-air parity: does our pull% x FB% (charted coordinates, game records)
reproduce Savant's pull% x FB% for MLB hitters? Plan A's bar: r >= 0.98.
Only if it passes can pulled air be measured in AAA.

Usage:  python pulled_air_parity.py
Reads MLB game records 2023-2026 and cache/mlb_tracking.csv; writes
cache/pulled_air_parity.json. No network.
"""
import json
import os

import numpy as np

from psmodel import spray, step1, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "pulled_air_parity.json")
SEASONS = (2023, 2024, 2025, 2026)
BAR = 0.98


def main():
    savant = step1.load_table(os.path.join(HERE, "cache", "mlb_tracking.csv"))
    pairs = []
    for season in SEASONS:
        for pid, (pull, fb, n) in spray.pull_and_fb(tracking.season_events(season, 1)).items():
            sv = savant.get((pid, season)) or {}
            if n < 100 or pull is None or sv.get("pull_percent") is None or sv.get("flyballs_percent") is None:
                continue
            pairs.append((pull * fb / 100.0, sv["pull_percent"] * sv["flyballs_percent"] / 100.0,
                          pull, sv["pull_percent"]))
        print(f"{season}: {len(pairs)} hitter-seasons so far", flush=True)
    a = np.array(pairs)
    r_product = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    r_pull = float(np.corrcoef(a[:, 2], a[:, 3])[0, 1])
    out = {"n": len(pairs), "r_product": r_product, "r_pull": r_pull,
           "bias_product": float(np.mean(a[:, 0] - a[:, 1])), "bar": BAR, "passed": r_product >= BAR}
    print(json.dumps(out, indent=2))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run** the full suite → 171 pass. Then run `python pulled_air_parity.py` (no network; parses ~9,700 game records, several minutes). Expected: about 1,500+ hitter-seasons, `r_pull` near plan A's 0.93–0.96, and **likely `passed: false`**. **If `passed: true`, stop after committing and hand to Opus**: a follow-up plan adds pulled air to the tracking layer. Task 5's driver refuses to continue on a pass.
- [ ] **Step 6: Commit** `feat(prospects-model): pulled-air parity check`.

---

### Task 5: The final run

**Files:** Create `model3c_final.py`

- [ ] **Step 1: Create** `model3c_final.py`:

```python
"""3c-hitters plan B: the final run.

1. Tests the tree leads (age x SLG, swstr x SLG) as explicit terms on the decision
   vantages, under the same adoption rule.
2. Reads the pulled-air parity verdict (pulled_air_parity.py must have run).
3. OPENS THE SEALED 2024 COHORT, once, for "soon": decides the marginal
   contact+approach pair, reports the final "soon" metrics, and checks whether
   the tracking layer helps "soon". Both decisions follow rules fixed in advance.
4. Re-runs step 1's prospect gate with step 1 fit as-of each cohort.
5. Production fits as of 2026 -> cache/hitter_ratings.csv.

Usage:  python model3c_final.py
Reads only cached data. Writes cache/model3c_final_report.txt,
cache/model3c_final.json and cache/hitter_ratings.csv (gitignored).
"""
import csv
import json
import os
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset, evaluate, milb, statsapi, step1
from psmodel import tracking_layer as TL
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model3c_final_report.txt")
DECISIONS = os.path.join(CACHE, "model3c_final.json")
RATINGS = os.path.join(CACHE, "hitter_ratings.csv")
PRODUCTION = cohorts.CURRENT_SEASON
AAA_TRACKED = (2022, 2023, 2024, 2025, 2026)
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def load(name):
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return json.load(fh)


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['d']:+.4f} (z {W.z_score(r['d'], r['se']):+.1f}) "
                     f"t50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f}" for v, r in res.items())


def safe(text):
    """CSV-injection guard for the one free-text column."""
    s = "" if text is None else str(text)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def built_on(key, dropped):
    return key in cohorts.LEADS and any(p in dropped for p in cohorts.LEADS[key])


def scored(rows, scores):
    """(indices of AAA rows with a tracking score, their scores)."""
    idx = [i for i, r in enumerate(rows)
           if r["sport_id"] == statsapi.AAA and (r["player_id"], r["season"]) in scores]
    return idx, np.array([scores[(rows[i]["player_id"], rows[i]["season"])] for i in idx], dtype=float)


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    rows = cohorts.build_rows(cohorts.load_milb(), cohorts.mlb_pa_history(),
                              {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    cohorts.add_products(rows)
    choice, s1, parity = load("model3c_choice.json"), load("step1_choice.json"), load("pulled_air_parity.json")
    mlb_table = step1.load_table(os.path.join(CACHE, "mlb_tracking.csv"))
    aaa_table = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    seasons = step1.hitter_seasons(labels)
    mlb_stats = {(r["player_id"], s): r for s in range(2015, PRODUCTION)
                 for r in statsapi.season_stats(s, "hitting", statsapi.MLB)}
    aaa_stats = {(r["player_id"], s): r for s in AAA_TRACKED
                 for r in milb.season_rows(s, statsapi.AAA, "hitting")}
    s1_keys = TL.step1_keys(s1)

    def tracking_scores(v, wanted):
        model = TL.step1_model(v, mlb_table, seasons, mlb_stats, s1_keys, s1["kind"])
        off = TL.offsets(v, aaa_table, mlb_table, [k for k in s1_keys if k != "age"])
        return TL.aaa_scores(aaa_table, aaa_stats, model, off, s1_keys, set(wanted))

    L, decisions = ["3c-HITTERS FINAL RUN (plan B)", ""], {}
    keys = {t: list(choice[t]["keys"]) for t in ("rating", "soon")}
    vants = {"rating": W.RATING_VANTAGES, "soon": W.SOON_VANTAGES}

    L.append("1. Tree leads as explicit terms (decision vantages, same adoption rule):")
    for t in ("rating", "soon"):
        bars = {v: asof.useful_bar(labels, v) for v in vants[t]}
        for lead, parents in cohorts.LEADS.items():
            if not all(p in keys[t] for p in parents):
                L.append(f"  {t:6} {lead:12} not testable (a parent feature was dropped)")
                continue
            res = W.compare(rows, keys[t], [lead], t, choice[t]["kind"], bars, vants[t])
            ok, wins, avail = W.adopt(res)
            L.append(f"  {t:6} {lead:12} {'ADOPT' if ok else 'drop':5} {wins}/{avail}  {fmt(res)}")
            if ok:
                keys[t].append(lead)
    L.append("")

    L.append(f"2. Pulled-air parity: r(pull x FB, ours vs Savant) = {parity['r_product']:.4f}, "
             f"pull alone {parity['r_pull']:.4f} (n={parity['n']}) -> {'PASS' if parity['passed'] else 'FAIL'}")
    if parity["passed"]:
        print("\n".join(L))
        raise SystemExit("pulled-air parity PASSED -- stop and hand to Opus for the follow-up plan")
    L += ["   pulled air stays a documented hypothesis; not used for AAA", ""]

    kind_s = choice["soon"]["kind"]
    bar24 = asof.useful_bar(labels, 2024)
    L.append("3. SEALED 2024 COHORT OPENED (soon only; the rating's 4-year answers for 2024 aren't in yet)")
    ca = set(cohorts.GROUPS["contact"] + cohorts.GROUPS["approach"])
    if {"contact", "approach"} <= set(choice["soon"]["adopted"]):
        base_k = [k for k in keys["soon"] if k not in ca and not built_on(k, ca)]
        res = W.compare(rows, base_k, [k for k in keys["soon"] if k not in base_k], "soon", kind_s,
                        {2024: bar24}, (2024,), unseal=True)
        r = res[2024]
        keep = (W.z_score(r["d"], r["se"]) >= W.WIN_Z
                and r["fam"]["top50"] - r["base"]["top50"] >= -W.TOP50_TOLERANCE)
        L.append(f"  contact + approach (marginal pair): {'KEEP' if keep else 'DROP'}  {fmt(res)}")
        if not keep:
            keys["soon"] = base_k
    test24, p24 = W.predictions(rows, keys["soon"], "soon", kind_s, {2024: bar24}, (2024,), unseal=True)[2024]
    m = W.metrics(test24, p24, "soon", bar24)
    L.append(f"  final 'soon' model on 2024: AUC {m['rank']:.3f}, top25 {m['top25']:.2f}, "
             f"top50 {m['top50']:.2f}, top100 {m['top100']:.2f} (n={m['n']})")
    L += [f"    calibration {mp:.2f} -> {act:.2f} (n={n})" for mp, act, n in W.calibration(test24, p24)]

    scores24 = tracking_scores(2024, (2022, 2024))
    train, test = W.frames(rows, "soon", 2024, bar24, keys["soon"], unseal=True)
    oof = W.oof(train, keys["soon"], "soon", kind_s)
    _, pte = W.fit_predict(train, test, keys["soon"], "soon", kind_s)
    itr, s_tr = scored(train, scores24)
    ite, s_te = scored(test, scores24)
    resid_tr, (a, b) = TL.residualize(s_tr, oof[itr])
    w, lo, hi = TL.trust_weight("soon", [train[i]["y"] for i in itr], oof[itr], resid_tr,
                                np.ones(len(itr)), [train[i]["player_id"] for i in itr])
    b_te = pte[ite]
    adj = TL.adjust("soon", b_te, s_te - (a + b * b_te), w)
    sub = [test[i] for i in ite]
    d, se = W.paired_gain(sub, b_te, adj, "soon")
    mb, ma = W.metrics(sub, b_te, "soon", bar24), W.metrics(sub, adj, "soon", bar24)
    use_soon = (lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z
    L += [f"  tracking layer for 'soon': trained on {len(itr)} AAA-2022 hitters, w {w:+.3f} [{lo:+.3f}, {hi:+.3f}]",
          f"    on {len(ite)} AAA-2024 hitters: AUC {mb['rank']:.3f} -> {ma['rank']:.3f} "
          f"(z {W.z_score(d, se):+.1f}), top50 {mb['top50']:.2f} -> {ma['top50']:.2f} "
          f"-> {'USE' if use_soon else 'do not use'}", ""]

    gate_rows = step1.complete(step1.aaa_rows(aaa_table, aaa_stats, seasons, (2022, 2023), s1["threshold"]),
                               s1_keys)
    sc = {}
    for c in (2022, 2023):
        sc.update(tracking_scores(c, (c,)))
    gate = [r for r in gate_rows if r["arrived"] and (r["player_id"], r["season"]) in sc]
    rho, glo, ghi = step1.spearman_ci([sc[(r["player_id"], r["season"])] for r in gate], [r["target"] for r in gate])
    L += [f"4. Step-1 prospect gate, as-of (step 1 fit through each cohort's own year): {len(gate)} arrivals, "
          f"Spearman {rho:+.3f} [{glo:+.3f}, {ghi:+.3f}] (first run, fit through 2025: +0.391) "
          f"-> {'PASS' if glo > 0 else 'FAIL'}", ""]

    L.append(f"5. Production, as of {PRODUCTION}:")
    bar_now = asof.useful_bar(labels, PRODUCTION)
    scores_now = tracking_scores(PRODUCTION, AAA_TRACKED)
    out = {}
    for t in ("rating", "soon"):
        kind = choice[t]["kind"]
        m_t, train, test, pred = W.production(rows, keys[t], t, kind, bar_now, PRODUCTION)
        itr, s_tr = scored(train, scores_now)
        b_tr = W.oof(train, keys[t], t, kind)[itr]
        y_tr = np.array([train[i]["y"] for i in itr], dtype=float)
        wt = np.ones(len(itr))
        pids = [train[i]["player_id"] for i in itr]
        if t == "rating":       # add the partly observed 2023-24 AAA cohorts, weighted by the share known
            extra = [r for r in rows if r["season"] in (2023, 2024) and r["sport_id"] == statsapi.AAA
                     and (r["player_id"], r["season"]) in scores_now
                     and all(r["f"].get(k) is not None for k in keys[t])]
            if extra:
                s_tr = np.concatenate([s_tr, [scores_now[(r["player_id"], r["season"])] for r in extra]])
                b_tr = np.concatenate([b_tr, evaluate.predict(m_t, extra, keys[t])])
                y_tr = np.concatenate([y_tr, [asof.rating_target(r["mlb"], r["season"]) for r in extra]])
                wt = np.concatenate([wt, [(PRODUCTION - r["season"]) / asof.RATING_YEARS for r in extra]])
                pids += [r["player_id"] for r in extra]
        resid_tr, (a, b) = TL.residualize(s_tr, b_tr)
        w, lo, hi = TL.trust_weight(t, y_tr, b_tr, resid_tr, wt, pids)
        use = (lo > 0 or hi < 0) and (t == "rating" or use_soon)
        L.append(f"  {t}: {kind} on {len(train)} rows; tracking w {w:+.3f} [{lo:+.3f}, {hi:+.3f}] from "
                 f"{len(y_tr)} AAA hitter-seasons -> "
                 + (("applied" + (" (PROVISIONAL: no later complete cohort to check it)" if t == "rating" else ""))
                    if use else "not applied"))
        final = np.array(pred, dtype=float)
        ite, s_te = scored(test, scores_now)
        if use and ite:
            final[ite] = TL.adjust(t, final[ite], s_te - (a + b * final[ite]), w)
        out[t] = {"test": test, "pred": final, "tracked": set(ite) if use else set()}
        decisions[t] = {"kind": kind, "keys": keys[t], "tracking_w": w, "tracking_ci": [lo, hi],
                        "tracking_used": bool(use)}
    decisions["soon"]["tracking_2024_check"] = {"auc_gain": d, "se": se, "used": bool(use_soon)}
    decisions["step1_gate_asof"] = {"n": len(gate), "rho": rho, "ci": [glo, ghi]}

    by = {}
    for t in ("rating", "soon"):
        for i, (r, p) in enumerate(zip(out[t]["test"], out[t]["pred"])):
            e = by.setdefault((r["player_id"], r["sport_id"]), {"r": r})
            e[t], e[t + "_tracked"] = float(p), i in out[t]["tracked"]
    best = {}
    for (pid, sid), e in by.items():            # one row per player: the highest level (lowest sportId)
        if "rating" in e and "soon" in e and (pid not in best or sid < best[pid]["r"]["sport_id"]):
            best[pid] = e
    ranked = sorted(best.values(), key=lambda e: e["rating"])
    for i, e in enumerate(ranked):
        e["pct"] = 100.0 * (i + 1) / len(ranked)
    with open(RATINGS, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["player_id", "name", "level", "age", "rating_sgp", "rating_percentile",
                     "p_useful_within_2", "tracking_in_rating", "tracking_in_soon", "flags"])
        for e in sorted(ranked, key=lambda e: -e["rating"]):
            r = e["r"]
            wr.writerow([r["player_id"], safe(r["name"]), cohorts.LEVEL_NAMES[r["sport_id"]], r["age_raw"],
                         f"{e['rating']:.3f}", f"{e['pct']:.1f}", f"{e['soon']:.3f}",
                         "yes" if e["rating_tracked"] else "no", "yes" if e["soon_tracked"] else "no",
                         "rating tracking provisional" if e["rating_tracked"] else ""])
    L.append(f"  wrote {len(ranked)} hitters -> {RATINGS}")
    L.append("  top 15 by rating: " + "; ".join(
        f"{e['r']['name']} ({cohorts.LEVEL_NAMES[e['r']['sport_id']]}, {e['r']['age_raw']}) "
        f"{e['rating']:.2f}/{e['soon']:.0%}" for e in sorted(ranked, key=lambda e: -e["rating"])[:15]))

    with open(DECISIONS, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run** the full suite → 171 pass.
- [ ] **Step 3: Security audit** (above). The run should hit only the cache.
- [ ] **Step 4: Run** `python model3c_final.py` (several minutes). Sanity checks:
  - section 3's 2024 AUC is in the range of the decision vantages (0.88–0.94);
  - the tracking check trains on roughly 100–200 AAA-2022 hitters;
  - the as-of gate has ~150+ arrivals;
  - `hitter_ratings.csv` has ~1,500–1,700 hitters, and the top 15 are mostly young players at AA/AAA.

  If the top 15 are mostly old repeaters or Single-A unknowns, stop and report; that means a sign or standardization bug. **Don't tune anything.** Every decision here follows a rule fixed before 2024 was opened.
- [ ] **Step 5: Commit** `feat(prospects-model): 3c final run -- sealed 2024 check and hitter ratings` (the report, JSON and CSV live in gitignored `cache/`).
- [ ] **Step 6: Record, with an Opus check first.** Add a "Plan B result (run <date>)" section to the 3c spec and update memory. **Hand the summary to Opus before telling the user**, per the standing lesson. After that, commit `docs(spec): record 3c plan B result`, and tell the user that sub-project 4 (the `prospects.html` shopping list) and the pitcher track are the next options.

---

## Not in this plan

Pulled air in AAA (only if parity passes: a follow-up plan); pitchers; dollars and `prospects.html` (sub-project 4); FanGraphs FV grades.
