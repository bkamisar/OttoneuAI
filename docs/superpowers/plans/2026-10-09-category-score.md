# Roto Category Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate per-category 4x4 prospect scores (playing time x MLB rates, in league SGP units) per spec `docs/superpowers/specs/2026-10-09-category-score-design.md`, and write the report, verdict and 2026 scores.

**Architecture:**
- **Pure logic** in a new `psmodel/categories.py`:
  - per-category SGP terms;
  - 4-season outcomes from cached MLB stats;
  - expected-line valuation;
  - weighted ridge rate models;
  - walk-up ladder statistics.
- **Runner:** `category_run.py` reuses `fvplus_run.Data` (model rows, boards, graded classes, ground-ball z). It runs checkpointed phases (rates, race, ladder, scores) and writes `cache/category_report.txt`, `cache/category_verdict.json` and `cache/category_scores.csv`.

**Tech Stack:** Python 3.14, numpy, scipy, scikit-learn. Runs from `prospects-model/`. Executed inline on Opus.

**Build choices fixed here, before any result. Each is a clarification of the spec:**
1. **The K term scales linearly with innings in category scores:** `(SO - repl_SO * IP/repl_IP) / den`.
   - `labels.pitcher_sgp`'s `max(1, IP/repl_IP)` reliever docking is a single-season total-value convention.
   - In a 4-year expected line it would give a pitcher with 0 expected IP a large negative K score.
   - Hitter terms are already linear. The pitcher terms sum to `pitcher_sgp` whenever IP >= replacement IP (tested).
2. **Rate models weight each training row by its window PA (hitters) or IP (pitchers).** A rate over 600 PA is far more reliable than one over 200.
3. **Missing feature values are filled with the training mean** (rows are not dropped).
4. **Ladder pooling:** graded classes 2021 and 2022 are pooled into one ladder per category; ungraded vantages 2019, 2021 and 2022 are pooled into another. Scores share one unit (league SGP), so pooling is valid.
5. **Labels are given per population.**
   - Graded labels use the graded ladder; ungraded labels use the ungraded ladder.
   - "trustworthy" = Part 2 trustworthy AND the ladder passes.
   - "level only" = the ladder passes but Part 2 does not.
   - "not predictable" = the ladder fails.
6. **Expected values use the replacement level of season V** (the vantage) for the ladders, and 2026's for production.
7. **Part 1 FV-alone candidate:** ridge on `fv` only. **FV + stats:** ridge on `fv` + the age_level, contact, power and speed groups (hitters) or the age_level and strikeouts groups (pitchers). **Ungraded model:** ridge on those same stat groups, with the 4-year PA/IP target.

---

### Task 1: `psmodel/categories.py` + tests

**Files:**
- Create: `prospects-model/psmodel/categories.py`
- Create: `prospects-model/tests/test_categories.py`

- [ ] **Step 1: Write the failing tests** `tests/test_categories.py`:

```python
import unittest

import numpy as np

from psmodel import categories as K
from psmodel import labels

REPL_H = {"pa": 400.0, "hr": 10.0, "r": 45.0, "obp": .300, "slg": .380}
REPL_P = {"ip": 60.0, "so": 55.0, "era": 4.6, "whip": 1.35, "hr9": 1.3}
DEN = {"HR": 9.0, "R": 25.0, "OBP": .005, "SLG": .009, "SO": 40.0, "ERA": .25, "WHIP": .03, "HR9": .08}
AVG = {"H": 6000.0, "P": 1400.0}


def hit(pid, pa, ab, hr, r, obp, slg):
    return {"player_id": pid, "pa": pa, "ab": ab, "hr": hr, "r": r, "obp": obp, "slg": slg}


def pit(pid, ip, so, era, whip, hr):
    return {"player_id": pid, "ip": ip, "so": so, "era": era, "whip": whip, "hr": hr, "hr9": hr * 9 / ip}


class TestTerms(unittest.TestCase):
    def test_hitter_terms_sum_to_labels(self):
        r = hit(1, 550, 480, 25, 80, .350, .480)
        self.assertAlmostEqual(sum(K.hitter_terms(r, REPL_H, DEN, AVG["H"]).values()),
                               labels.hitter_sgp(r, REPL_H, DEN, AVG["H"]))

    def test_pitcher_terms_sum_to_labels_above_replacement_ip(self):
        r = pit(2, 150.0, 170, 3.40, 1.10, 15)
        self.assertAlmostEqual(sum(K.pitcher_terms(r, REPL_P, DEN, AVG["P"]).values()),
                               labels.pitcher_sgp(r, REPL_P, DEN, AVG["P"]))

    def test_k_term_is_linear_so_no_innings_means_zero(self):
        t = K.pitcher_terms({"ip": 0.0, "so": 0, "era": 0.0, "whip": 0.0, "hr9": 0.0}, REPL_P, DEN, AVG["P"])
        self.assertEqual(t, {"K": 0.0, "ERA": 0.0, "WHIP": 0.0, "HR9": 0.0})


class TestOutcome(unittest.TestCase):
    def tables(self):
        t = {s: {"H": {}, "P": {}, "repl": {"H": REPL_H, "P": REPL_P}} for s in range(2021, 2027)}
        t[2022]["H"][1] = hit(1, 300, 260, 10, 40, .340, .450)
        t[2024]["H"][1] = hit(1, 100, 90, 2, 10, .280, .350)
        return t

    def test_sums_window_terms_and_pools_rates(self):
        terms, pt, rates = K.outcome(1, "H", 2021, self.tables(), DEN, AVG)
        a = K.hitter_terms(hit(1, 300, 260, 10, 40, .340, .450), REPL_H, DEN, AVG["H"])
        b = K.hitter_terms(hit(1, 100, 90, 2, 10, .280, .350), REPL_H, DEN, AVG["H"])
        for c in K.HIT_CATS:
            self.assertAlmostEqual(terms[c], a[c] + b[c])
        self.assertEqual(pt, 400)
        self.assertAlmostEqual(rates["OBP"], (.340 * 300 + .280 * 100) / 400)
        self.assertAlmostEqual(rates["SLG"], (.450 * 260 + .350 * 90) / 350)
        self.assertAlmostEqual(rates["HR"], 12 / 400)

    def test_window_excludes_the_vantage_and_no_time_means_no_rates(self):
        terms, pt, rates = K.outcome(1, "H", 2024, self.tables(), DEN, AVG)   # window 2025-2028
        self.assertEqual((pt, rates), (0, None))
        self.assertEqual(set(terms.values()), {0.0})


class TestExpected(unittest.TestCase):
    def test_linear_in_playing_time(self):
        rates = {"HR": .04, "R": .13, "OBP": .340, "SLG": .460}
        one = K.expected_terms("H", 500, rates, REPL_H, DEN, AVG)
        two = K.expected_terms("H", 1000, rates, REPL_H, DEN, AVG)
        for c in K.HIT_CATS:
            self.assertAlmostEqual(two[c], 2 * one[c])
        self.assertEqual(set(K.expected_terms("H", 0, rates, REPL_H, DEN, AVG).values()), {0.0})
        p = K.expected_terms("P", 100, {"K": 1.0, "ERA": 4.0, "WHIP": 1.3, "HR9": 1.1}, REPL_P, DEN, AVG)
        self.assertAlmostEqual(p["K"], (100 - 55 * 100 / 60) / 40)


class TestModels(unittest.TestCase):
    def test_design_fill_and_weighted_ridge(self):
        rows = [{"f": {"a": float(i), "b": None if i % 3 == 0 else 1.0}} for i in range(60)]
        X, fill = K.design(rows, ["a", "b"])
        self.assertFalse(np.isnan(X).any())
        y = np.array([2.0 * i for i in range(60)])
        m, fill = K.fit_ridge(rows, ["a", "b"], y, w=np.ones(60))
        p = K.predict(m, fill, rows, ["a", "b"])
        self.assertGreater(np.corrcoef(p, y)[0, 1], 0.99)


class TestLadder(unittest.TestCase):
    def test_monotone_ladder(self):
        rng = np.random.default_rng(0)
        score = rng.normal(size=500)
        actual = score + rng.normal(scale=0.5, size=500)
        lad = K.ladder(score, actual)
        self.assertEqual(lad["inversions"], 0)
        self.assertEqual(sum(lad["counts"]), 500)
        self.assertGreater(lad["d"] - 1.96 * lad["se"], 0)
        self.assertTrue(K.ladder_pass(lad, 0.01))
        self.assertFalse(K.ladder_pass(lad, 0.2))

    def test_inversions(self):
        self.assertEqual(K.inversions([1, 2, 1.5, 3, 2.5]), 2)
```

- [ ] **Step 2:** Run `python -m pytest tests/test_categories.py -q`. Expected: collection error (no module).

- [ ] **Step 3: Write `psmodel/categories.py`:**

```python
"""Roto category scores (spec docs/superpowers/specs/2026-10-09-category-score-design.md).

A prospect's 4-year contribution in each 4x4 category = playing time x (rate vs
replacement), valued with labels.py's per-category terms. One difference, fixed
before any result: the K term scales linearly with innings (labels.pitcher_sgp
never scales replacement K down for low-inning pitchers, a single-season
convention that would make a non-arrival's expected K score negative).
"""
import warnings

import numpy as np
from scipy.stats import norm

from . import context, evaluate, statsapi

HIT_CATS = ("HR", "R", "OBP", "SLG")
PIT_CATS = ("K", "ERA", "WHIP", "HR9")
CATS = {"H": HIT_CATS, "P": PIT_CATS}
WINDOW = 4
MIN_PT = {"H": 200.0, "P": 50.0}
N_BUCKETS = 5
N_BOOT = 1000
HOLM_ALPHA = 0.05


def hitter_terms(row, repl, den, avg_pa):
    """labels.hitter_sgp split into its four categories (they sum to it)."""
    pa = row["pa"] or 0
    pa_ratio = (pa / repl["pa"]) if repl.get("pa") else 1.0
    return {"HR": (row["hr"] - repl["hr"] * pa_ratio) / den["HR"],
            "R": (row["r"] - repl["r"] * pa_ratio) / den["R"],
            "OBP": (row["obp"] - repl["obp"]) * pa / (avg_pa or 1) / den["OBP"],
            "SLG": (row["slg"] - repl["slg"]) * pa / (avg_pa or 1) / den["SLG"]}


def pitcher_terms(row, repl, den, avg_ip):
    """labels.pitcher_sgp's four categories, K scaled linearly with innings."""
    ip = row["ip"] or 0.0
    scale = ip / repl["ip"] if repl.get("ip") else 1.0
    return {"K": (row["so"] - repl["so"] * scale) / den["SO"],
            "ERA": (repl["era"] - row["era"]) * ip / (avg_ip or 1) / den["ERA"],
            "WHIP": (repl["whip"] - row["whip"]) * ip / (avg_ip or 1) / den["WHIP"],
            "HR9": (repl["hr9"] - row["hr9"]) * ip / (avg_ip or 1) / den["HR9"]}


TERMS = {"H": hitter_terms, "P": pitcher_terms}


def season_tables(first, last):
    """{season: {"H": {pid: MLB row}, "P": {...}, "repl": {"H": ..., "P": ...}}} from cached StatsAPI."""
    out = {}
    for s in range(first, last + 1):
        hs = statsapi.season_stats(s, "hitting", statsapi.MLB)
        ps = statsapi.season_stats(s, "pitching", statsapi.MLB)
        frac = context.season_fraction(s)
        out[s] = {"H": {r["player_id"]: r for r in hs}, "P": {r["player_id"]: r for r in ps},
                  "repl": {"H": context.hitter_replacement(hs, frac), "P": context.pitcher_replacement(ps, frac)}}
    return out


def averages():
    avg_pa, avg_ip = context.league_averages()
    return {"H": avg_pa, "P": avg_ip}


def outcome(pid, typ, v, tables, den, avg):
    """(category terms summed over seasons v+1..v+4, playing time, pooled rates or None)."""
    terms = dict.fromkeys(CATS[typ], 0.0)
    acc = {}
    for s in range(v + 1, v + WINDOW + 1):
        t = tables.get(s)
        r = t[typ].get(pid) if t else None
        if r is None:
            continue
        for k, x in TERMS[typ](r, t["repl"][typ], den, avg[typ]).items():
            terms[k] += x
        if typ == "H":
            for k, x in (("pa", r["pa"]), ("ab", r["ab"]), ("hr", r["hr"]), ("r", r["r"]),
                         ("obp_pa", r["obp"] * r["pa"]), ("slg_ab", r["slg"] * r["ab"])):
                acc[k] = acc.get(k, 0.0) + x
        else:
            for k, x in (("ip", r["ip"]), ("so", r["so"]), ("hr", r["hr"]),
                         ("era_ip", r["era"] * r["ip"]), ("whip_ip", r["whip"] * r["ip"])):
                acc[k] = acc.get(k, 0.0) + x
    pt = acc.get("pa" if typ == "H" else "ip", 0)
    if not pt:
        return terms, 0, None
    if typ == "H":
        rates = {"HR": acc["hr"] / pt, "R": acc["r"] / pt, "OBP": acc["obp_pa"] / pt,
                 "SLG": acc["slg_ab"] / acc["ab"] if acc["ab"] else 0.0}
    else:
        rates = {"K": acc["so"] / pt, "ERA": acc["era_ip"] / pt, "WHIP": acc["whip_ip"] / pt,
                 "HR9": 9.0 * acc["hr"] / pt}
    return terms, pt, rates


def expected_terms(typ, pt, rates, repl, den, avg):
    """Category terms of an expected 4-season line: playing time pt at the given rates."""
    if typ == "H":
        row = {"pa": pt, "hr": rates["HR"] * pt, "r": rates["R"] * pt, "obp": rates["OBP"], "slg": rates["SLG"]}
    else:
        row = {"ip": pt, "so": rates["K"] * pt, "era": rates["ERA"], "whip": rates["WHIP"], "hr9": rates["HR9"]}
    return TERMS[typ](row, repl, den, avg[typ])


def design(rows, keys, fill=None):
    X = np.array([[np.nan if r["f"].get(k) is None else float(r["f"][k]) for k in keys] for r in rows],
                 dtype=float)
    if fill is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fill = np.nan_to_num(np.nanmean(X, axis=0))
    i, j = np.where(np.isnan(X))
    X[i, j] = fill[j]
    return X, fill


def fit_ridge(rows, keys, y, w=None):
    X, fill = design(rows, keys)
    m = evaluate._model("ridge")
    m.fit(X, np.asarray(y, dtype=float), **({} if w is None else {"ridgecv__sample_weight": np.asarray(w)}))
    return m, fill


def predict(m, fill, rows, keys):
    return m.predict(design(rows, keys, fill)[0])


def _parts(score, n):
    return np.array_split(np.argsort(np.asarray(score, dtype=float), kind="stable"), n)


def inversions(means):
    return sum(1 for a, b in zip(means, means[1:]) if b < a)


def ladder(score, actual, n=N_BUCKETS, n_boot=N_BOOT, seed=0):
    """Walk-up ladder: bucket means low -> high score, counts, inversions, and the
    top-minus-bottom difference with its bootstrap SE (buckets fixed by score)."""
    actual = np.asarray(actual, dtype=float)
    parts = _parts(score, n)
    means = [float(actual[p].mean()) for p in parts]
    lo, hi = parts[0], parts[-1]
    rng = np.random.default_rng(seed)
    boot = [actual[rng.choice(hi, len(hi))].mean() - actual[rng.choice(lo, len(lo))].mean() for _ in range(n_boot)]
    d, se = means[-1] - means[0], float(np.std(boot))
    z = d / se if se > 0 else 0.0
    return {"means": means, "counts": [len(p) for p in parts], "inversions": inversions(means),
            "d": d, "se": se, "z": z, "p": float(2 * norm.sf(abs(z)))}


def ladder_pass(lad, holm_p):
    return lad["inversions"] <= 1 and lad["d"] - 1.96 * lad["se"] > 0 and holm_p < HOLM_ALPHA
```

- [ ] **Step 4:** Run `python -m pytest tests/test_categories.py -q`. Expected: all pass.
- [ ] **Step 5: Commit:** `feat(category-score): per-category SGP terms, 4-season outcomes, expected lines, weighted ridge, walk-up ladder`

---

### Task 2: The runner

**Files:** Create `prospects-model/category_run.py`.

- [ ] **Step 1: Write `category_run.py`:**

```python
"""Roto category scores (spec 2026-10-09-category-score-design.md).

Phases, checkpointed to cache/category_<phase>.json (skipped on relaunch;
--force redoes all):
  rates  -- Part 2: as-of rate models per category; trust at vantages 2019/2021/2022
  race   -- Part 1: FV alone vs FV + stats for 4-year playing time (graded classes 2021/2022)
  ladder -- walk-up ladders per category (graded 2021+2022; ungraded 2019+2021+2022)
  scores -- production for 2026 players -> cache/category_scores.csv
Report: cache/category_report.txt; verdict: cache/category_verdict.json. No network.

Usage:  python category_run.py [--force]
"""
import argparse
import csv
import datetime
import json
import os
import warnings

import numpy as np
from scipy.stats import spearmanr

import consensus_gate as CG
import fvplus_run as R
from psmodel import asof, cohorts, context, pcohorts
from psmodel import categories as K
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import shopping as S
from psmodel import walkforward as W

CACHE, NOW = R.CACHE, R.NOW
BOARD = os.path.join(os.path.dirname(R.HERE), "data", "prospects.csv")
REPORT = os.path.join(CACHE, "category_report.txt")
VERDICT = os.path.join(CACHE, "category_verdict.json")
SCORES = os.path.join(CACHE, "category_scores.csv")
RATE_VANTAGES = (2019, 2021, 2022)
RACE_CLASSES = (2021, 2022)
UNGRADED_VANTAGES = (2019, 2021, 2022)
LAST_COMPLETE = NOW - K.WINDOW                      # 2022: last cohort with a full 4-season window
RATE_KEYS = {"H": [k for g in cohorts.GROUPS.values() for k in g],
             "P": [k for g in pcohorts.GROUPS.values() for k in g] + ["gb"]}
PT_KEYS = {"H": [k for g in ("age_level", "contact", "power", "speed") for k in cohorts.GROUPS[g]],
           "P": [k for g in ("age_level", "strikeouts") for k in pcohorts.GROUPS[g]]}
BASELINE = {"H": {"HR": "hr_pa", "R": None, "OBP": "obp", "SLG": "slg"},
            "P": {"K": "k", "ERA": "era", "WHIP": "whip", "HR9": "hr9"}}
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


class Ctx:
    def __init__(self):
        self.d = R.Data()
        for r in self.d.rows["P"]:
            r["f"]["gb"] = self.d.gb.get((r["player_id"], r["season"], r["sport_id"]))
        self.den = context.load_league_denominators(R.STANDINGS)
        self.avg = K.averages()
        self.tables = K.season_tables(2013, NOW)
        self._out = {}

    def out(self, typ, pid, v):
        key = (typ, pid, v)
        if key not in self._out:
            self._out[key] = K.outcome(pid, typ, v, self.tables, self.den, self.avg)
        return self._out[key]

    def best(self, typ, season):
        """One row per player for a season: the highest level."""
        b = {}
        for r in self.d.rows[typ]:
            if r["season"] == season and (r["player_id"] not in b or r["sport_id"] < b[r["player_id"]]["sport_id"]):
                b[r["player_id"]] = r
        return list(b.values())

    def rate_models(self, typ, v, exclude=frozenset()):
        """{cat: (model, fill)} fit on rows whose window is complete by v, players reaching MIN_PT."""
        train = [r for r in self.d.rows[typ] if r["season"] + K.WINDOW <= v and r["player_id"] not in exclude
                 and self.out(typ, r["player_id"], r["season"])[1] >= K.MIN_PT[typ]]
        pts = np.array([self.out(typ, r["player_id"], r["season"])[1] for r in train])
        models = {}
        for c in K.CATS[typ]:
            y = [self.out(typ, r["player_id"], r["season"])[2][c] for r in train]
            models[c] = K.fit_ridge(train, RATE_KEYS[typ], y, w=pts)
        return models, len(train)

    def pt_stats_model(self, typ, v, exclude=frozenset()):
        train = [r for r in self.d.rows[typ] if r["season"] + K.WINDOW <= v and r["player_id"] not in exclude]
        y = [self.out(typ, r["player_id"], r["season"])[1] for r in train]
        return K.fit_ridge(train, PT_KEYS[typ], y), len(train)


def _graded_rows(players):
    """Graded players as rows whose features are FV plus the model-row stats."""
    return [{"player_id": p["player_id"], "f": dict(p["row"]["f"], fv=p["x"]["fv"]), "row": p["row"],
             "fv": p["x"]["fv"]} for p in players]


def race_split(cx, typ, v):
    classes = cx.d.classes[(typ, "rating")]
    test = _graded_rows(classes[v])
    ids = {p["player_id"] for p in test}
    train = _graded_rows([p for c, ps in classes.items() if c != v and asof.rating_known(c, v)
                          for p in ps if p["player_id"] not in ids])
    for r in train + test:
        r["y"] = cx.out(typ, r["player_id"], r["row"]["season"])[1]
    return train, test


def phase_rates(cx):
    out = {}
    for typ in ("H", "P"):
        res = {c: {} for c in K.CATS[typ]}
        for v in RATE_VANTAGES:
            test = [r for r in cx.best(typ, v) if cx.out(typ, r["player_id"], v)[1] >= K.MIN_PT[typ]]
            models, n_train = cx.rate_models(typ, v, exclude={r["player_id"] for r in test})
            for c in K.CATS[typ]:
                y = [cx.out(typ, r["player_id"], v)[2][c] for r in test]
                pred = K.predict(*models[c], test, RATE_KEYS[typ])
                ci = C.rank_ci([{"y": t} for t in y], pred, "rating")
                base = BASELINE[typ][c]
                raw = [r["f"].get(base) for r in test] if base else None
                ok = [(a, b) for a, b in zip(raw, y) if a is not None] if raw else []
                res[c][str(v)] = {"n_train": n_train, "n_test": len(test), "ci": ci,
                                  "raw_rho": float(spearmanr(*zip(*ok)).statistic) if len(ok) > 30 else None}
        out[typ] = {c: {"vantages": r, "trust": sum(1 for x in r.values() if x["ci"] and x["ci"][1] > 0) >= 2}
                    for c, r in res.items()}
    return out


def phase_race(cx):
    out = {}
    for typ in ("H", "P"):
        res, rhos = {}, {}
        for v in RACE_CLASSES:
            train, test = race_split(cx, typ, v)
            if len(train) < F.MIN_TRAIN_PLAYERS:
                raise SystemExit(f"{typ} race class {v}: {len(train)} training players < {F.MIN_TRAIN_PLAYERS} -- stop")
            y = [r["y"] for r in train]
            pa = K.predict(*K.fit_ridge(train, ["fv"], y), test, ["fv"])
            pb = K.predict(*K.fit_ridge(train, ["fv"] + PT_KEYS[typ], y), test, ["fv"] + PT_KEYS[typ])
            d, se = W.paired_gain(test, pa, pb, "rating")
            res[v] = {"d": d, "se": se}
            yt = [r["y"] for r in test]
            rhos[str(v)] = {"fv": float(spearmanr(pa, yt).statistic), "fv_stats": float(spearmanr(pb, yt).statistic),
                            "d": d, "se": se, "z": W.z_score(d, se), "n_train": len(train), "n_test": len(test)}
        dsum, z, n = F.pooled(res)
        harmed = any(W.z_score(r["d"], r["se"]) <= W.HARM_Z for r in res.values())
        out[typ] = {"classes": rhos, "pooled_d": dsum, "pooled_z": z,
                    "choice": "fv_stats" if (z >= W.WIN_Z and not harmed) else "fv"}
    return out


def phase_ladder(cx, race):
    out = {"graded": {}, "ungraded": {}}
    for typ in ("H", "P"):
        cols = ["fv"] + (PT_KEYS[typ] if race[typ]["choice"] == "fv_stats" else [])
        g_score, g_act, g_fv = {c: [] for c in K.CATS[typ]}, {c: [] for c in K.CATS[typ]}, []
        for v in RACE_CLASSES:
            train, test = race_split(cx, typ, v)
            pt = np.maximum(K.predict(*K.fit_ridge(train, cols, [r["y"] for r in train]), test, cols), 0.0)
            models, _ = cx.rate_models(typ, v, exclude={r["player_id"] for r in test})
            rates = {c: K.predict(*models[c], [r["row"] for r in test], RATE_KEYS[typ]) for c in K.CATS[typ]}
            repl = cx.tables[v]["repl"][typ]
            for i, r in enumerate(test):
                e = K.expected_terms(typ, pt[i], {c: rates[c][i] for c in K.CATS[typ]}, repl, cx.den, cx.avg)
                a = cx.out(typ, r["player_id"], v)[0]
                for c in K.CATS[typ]:
                    g_score[c].append(e[c])
                    g_act[c].append(a[c])
                g_fv.append(r["fv"])
        u_score, u_act = {c: [] for c in K.CATS[typ]}, {c: [] for c in K.CATS[typ]}
        for v in UNGRADED_VANTAGES:
            rows = cx.best(typ, v)
            m = C.match(CG.people(rows), cx.d.boards[typ][v + 1])
            skip = set(m["matched"]) | m["age_rejected"] | {a["player_id"] for a in m["ambiguous"]}
            test = [r for r in rows if r["player_id"] not in skip]
            ids = {r["player_id"] for r in test}
            (mp, fp), _ = cx.pt_stats_model(typ, v, exclude=ids)
            pt = np.maximum(K.predict(mp, fp, test, PT_KEYS[typ]), 0.0)
            models, _ = cx.rate_models(typ, v, exclude=ids)
            rates = {c: K.predict(*models[c], test, RATE_KEYS[typ]) for c in K.CATS[typ]}
            repl = cx.tables[v]["repl"][typ]
            for i, r in enumerate(test):
                e = K.expected_terms(typ, pt[i], {c: rates[c][i] for c in K.CATS[typ]}, repl, cx.den, cx.avg)
                a = cx.out(typ, r["player_id"], v)[0]
                for c in K.CATS[typ]:
                    u_score[c].append(e[c])
                    u_act[c].append(a[c])
        for c in K.CATS[typ]:
            lad = K.ladder(g_score[c], g_act[c])
            lad["rho_score"] = float(spearmanr(g_score[c], g_act[c]).statistic)
            lad["rho_fv"] = float(spearmanr(g_fv, g_act[c]).statistic)
            out["graded"][f"{typ}_{c}"] = lad
            out["ungraded"][f"{typ}_{c}"] = K.ladder(u_score[c], u_act[c])
    for pop in ("graded", "ungraded"):
        holm = F.holm_adjust({k: v["p"] for k, v in out[pop].items()})
        for k, v in out[pop].items():
            v["holm_p"] = holm[k]
            v["pass"] = K.ladder_pass(v, holm[k])
    return out


def labels(rates, ladder):
    out = {}
    for pop in ("graded", "ungraded"):
        for k, lad in ladder[pop].items():
            typ, c = k.split("_")
            trust = rates[typ][c]["trust"]
            out.setdefault(k, {})[pop] = ("trustworthy" if lad["pass"] and trust else
                                          "level only" if lad["pass"] else "not predictable")
    return out


def phase_scores(cx, race):
    rows_out = []
    for typ in ("H", "P"):
        rows = cx.best(typ, NOW)
        models, _ = cx.rate_models(typ, NOW)
        rates = {c: K.predict(*models[c], rows, RATE_KEYS[typ]) for c in K.CATS[typ]}
        board = S.load_current_board(BOARD, pitchers=typ == "P")
        matched = C.match(CG.people(rows), board)["matched"]
        cols = ["fv"] + (PT_KEYS[typ] if race[typ]["choice"] == "fv_stats" else [])
        classes = cx.d.classes[(typ, "rating")]
        train = _graded_rows([p for c, ps in classes.items() if asof.rating_known(c, NOW) for p in ps])
        for r in train:
            r["y"] = cx.out(typ, r["player_id"], r["row"]["season"])[1]
        mg, fg = K.fit_ridge(train, cols, [r["y"] for r in train])
        (ms, fs), _ = cx.pt_stats_model(typ, NOW)
        repl = cx.tables[NOW]["repl"][typ]
        for i, r in enumerate(rows):
            e = matched.get(r["player_id"])
            if e is not None:
                pt = K.predict(mg, fg, [{"f": dict(r["f"], fv=C.fv_score(e))}], cols)[0]
                path = "FV" if race[typ]["choice"] == "fv" else "FV+stats"
            else:
                pt = K.predict(ms, fs, [r], PT_KEYS[typ])[0]
                path = "stats"
            pt = max(pt, 0.0)
            terms = K.expected_terms(typ, pt, {c: rates[c][i] for c in K.CATS[typ]}, repl, cx.den, cx.avg)
            row = {"player_id": r["player_id"], "name": CG.safe(r["name"]), "type": typ,
                   "level": cohorts.LEVEL_NAMES.get(r["sport_id"], ""), "age": r.get("age_raw"),
                   "board_key": CG.safe(e["fg_id"]) if e else "", "pt_path": path, "expected_pt": round(pt, 1)}
            row.update({c: round(terms.get(c, 0.0), 3) if c in terms else "" for c in K.HIT_CATS + K.PIT_CATS})
            rows_out.append(row)
    with open(SCORES, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    return {"n": {t: sum(1 for r in rows_out if r["type"] == t) for t in ("H", "P")}}


def checkpoint(name, force, fn):
    path = os.path.join(CACHE, f"category_{name}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    print(f"phase {name} ...", flush=True)
    out = fn()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    os.replace(tmp, path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every phase")
    force = ap.parse_args().force
    holder = {}

    def cx():
        if "cx" not in holder:
            print("building data ...", flush=True)
            holder["cx"] = Ctx()
        return holder["cx"]

    rates = checkpoint("rates", force, lambda: phase_rates(cx()))
    race = checkpoint("race", force, lambda: phase_race(cx()))
    ladder = checkpoint("ladder", force, lambda: phase_ladder(cx(), race))
    scores = checkpoint("scores", force, lambda: phase_scores(cx(), race))
    lab = labels(rates, ladder)

    L = ["ROTO CATEGORY SCORES -- spec 2026-10-09-category-score-design.md", ""]
    L.append("1. PART 2 -- MLB rates when he plays (Spearman predicted vs actual rate; 95% CI; raw minor-league stat for reference)")
    for typ in ("H", "P"):
        for c, v in rates[typ].items():
            per = "; ".join(f"{y}: " + ("n/a" if x["ci"] is None else f"{x['ci'][0]:+.3f} [{x['ci'][1]:+.3f}, {x['ci'][2]:+.3f}]")
                            + (f" (raw {x['raw_rho']:+.3f})" if x["raw_rho"] is not None else "")
                            + f" n={x['n_test']}" for y, x in v["vantages"].items())
            L.append(f"  {typ} {c:4}: {per} -> {'TRUSTWORTHY' if v['trust'] else 'not trustworthy'}")
    L += ["", "2. PART 1 -- 4-year playing time race (graded; Spearman with actual PA/IP)"]
    for typ in ("H", "P"):
        v = race[typ]
        for y, x in v["classes"].items():
            L.append(f"  {typ} class {y}: FV {x['fv']:+.3f} vs FV+stats {x['fv_stats']:+.3f} "
                     f"(gain {x['d']:+.4f}, z {x['z']:+.1f}; train {x['n_train']}, test {x['n_test']})")
        L.append(f"  {typ}: pooled z {v['pooled_z']:+.2f} -> use {'FV + stats' if v['choice'] == 'fv_stats' else 'FV alone'}")
    for pop, title in (("graded", "graded classes 2021+2022"), ("ungraded", "ungraded, vantages 2019+2021+2022")):
        L += ["", f"3. WALK-UP LADDERS -- {title} (mean actual 4-year category SGP by score bucket, low -> high)"]
        for k, lad in ladder[pop].items():
            extra = f"; score rho {lad['rho_score']:+.3f} vs FV rho {lad['rho_fv']:+.3f}" if "rho_fv" in lad else ""
            L.append(f"  {k:6}: " + " < ".join(f"{m:+.2f}" for m in lad["means"])
                     + f"  (n {lad['counts'][0]}/bucket) top-bottom {lad['d']:+.2f} (z {lad['z']:+.1f}, Holm p "
                     f"{lad['holm_p']:.4f}), inversions {lad['inversions']} -> {'PASS' if lad['pass'] else 'fail'}{extra}")
    L += ["", "4. LABELS (per population)"]
    for k, v in lab.items():
        L.append(f"  {k:6}: graded {v['graded']}; ungraded {v['ungraded']}")
    L += ["", f"5. SCORES: {SCORES} ({scores['n']['H']} hitters, {scores['n']['P']} pitchers, 2026 rows)"]
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump({"generated": datetime.date.today().isoformat(), "labels": lab,
                   "pt_choice": {t: race[t]["choice"] for t in ("H", "P")}}, fh, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Import smoke test:** `python -c "import category_run"`. Expected: no error.
- [ ] **Step 3: Commit:** `feat(category-score): checkpointed runner -- rate trust, playing-time race, walk-up ladders, 2026 scores`

---

### Task 3: Run, review, record

- [ ] **Step 1:** Confirm no stray python process is running. Then run `python category_run.py > cache/category_log.txt 2>&1` in the background.
  - It stops if a race class has fewer than 300 training players; bring that to the user.
  - On a crash: fix, relaunch; completed phases are skipped.
- [ ] **Step 2: Opus review, plumbing first.**
  - Every graded race class should have the counts expected from the FV+ counts (classes 2021 and 2022 ~331/312 hitters, ~317/345 pitchers).
  - Part 2 test n should be plausible (a few hundred arrivals per vantage).
  - The ladders' bucket counts should be equal (±1).
  - Spot-check: the top 10 2026 hitters by HR score should look like power prospects, and by OBP like walk-heavy hitters.
- [ ] **Step 3: Read the results.**
  - Trustworthy categories, the race verdict, the ladders, and score vs FV per category.
  - Surprises are reported as surprises.
- [ ] **Step 4: Record.**
  - Write a "Result" section in the spec and update memory. Commit the spec (the cache outputs are gitignored).
  - Tell the user plainly which categories are trustworthy and what that means.
  - Remind them to push.
