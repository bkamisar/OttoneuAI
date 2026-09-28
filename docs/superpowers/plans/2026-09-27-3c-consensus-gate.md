# 3c Plan C: The Consensus Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether the 3c hitter model beats just following FanGraphs' FV. This is the NFLU test: across past prospect classes, is blindly following consensus as good as the model?

**Architecture:** `psmodel/consensus.py` holds pure, unit-tested pieces:
- Board loading and the FV order.
- Name + age matching.
- Percentile ranks and the head-to-head scoring.
- The pre-registered verdict.

`consensus_gate.py` wires them to the existing walk-forward harness (`psmodel/walkforward.py`), one class per test year. The verdict rules come from the spec (`docs/superpowers/specs/2026-09-27-3c-hitters-design.md`, "Plan C design: the consensus gate, detailed") and must not be changed after seeing results.

**Tech Stack:** Python 3 stdlib, numpy, scipy, scikit-learn (all already installed). Tests use `unittest`.

---

## Ground rules (read first)

- Run everything from `prospects-model/`.
  - Tests: `python -m unittest discover -s tests`. Before this plan: **172 pass, 3 skipped**.
- **No network step anywhere in this plan.** The runner reads only cached data and the user's Board exports.
- **FanGraphs data is never committed.**
  - It lives in the gitignored `prospects-model/cache/fv/` (`board_<year>_hitters.csv`, 2017–2026).
  - Before every commit, `git ls-files prospects-model/cache` must print nothing.
- Git: commit locally after each task. **Never push, fetch or pull** (the user pushes via GitHub Desktop).
- The model tested is the **base** model. It uses `cache/model3c_final.json` keys/kind, fit as-of each class through `W.predictions`.
  - Tracking is excluded: the rating tracking weight can't be tested as-of, and tracking is off for "soon".
- **2024 "soon" (list 2025) is information only.** It was opened in plan B. It is reported, never counted in a verdict.
- Board ages are taken at a date that varies by list, so they are **never** used as as-of age. They serve only as a matching guard, via a per-list calibrated offset.

## File structure

- Create `prospects-model/psmodel/consensus.py`: Board loading, FV order, matching, scoring, verdict.
- Create `prospects-model/tests/test_consensus.py`: unit tests for all of the above.
- Create `prospects-model/consensus_gate.py`: the runner. It writes these gitignored files:
  - `cache/consensus_report.txt`
  - `cache/consensus_verdict.json`
  - `cache/consensus_ambiguous.csv`

Existing code used (read-only):
- `psmodel/walkforward.py`:
  - `predictions(rows, keys, target, kind, ctxs, vantages, unseal)` → `{v: (test rows, preds)}`
  - `_y(r, target, ctx)`, `metrics`, `paired_gain`, `adopt`, `z_score`, `_rank`, `RATING_VANTAGES`, `SOON_VANTAGES`
- `psmodel/asof.py`: `ref_curve`, `rating_known`, `soon_known`, `attach_ranks`.
- `psmodel/cohorts.py`: `build_rows`, `load_milb`, `mlb_pa_history`, `add_products`, `MILB_SEASONS`.
- `psmodel/dataset.py`: `load_labels`.

Row shape from `cohorts.build_rows`: `{player_id, name, season, sport_id, age_raw, f, mlb}`. Walk-forward frames add `y`.

---

### Task 0: Preflight

- [ ] **Step 1: Confirm the baseline**

Run: `python -m unittest discover -s tests`
Expected: `OK (skipped=3)`, 172 tests.

- [ ] **Step 2: Confirm the inputs exist and nothing from cache is tracked**

Run (PowerShell):
```powershell
Test-Path cache\model3c_final.json, cache\labels.csv; (Get-ChildItem cache\fv\board_*_hitters.csv).Name; git ls-files cache
```
Expected:
- `True` twice.
- Ten files, `board_2017_hitters.csv` … `board_2026_hitters.csv`.
- Nothing from `git ls-files`.

If any board file is missing, stop and tell the user.

---

### Task 1: Board loading, names and the FV order

**Files:**
- Create: `prospects-model/psmodel/consensus.py`
- Test: `prospects-model/tests/test_consensus.py`

- [ ] **Step 1: Write the failing tests**

Create `prospects-model/tests/test_consensus.py`:

```python
import csv
import os
import tempfile
import unittest

import numpy as np

from psmodel import consensus as C

HEADER = ["Name", "Org", "Pos", "Current Level", "Age", "Top 100", "Org Rk", "Hit", "Game Pwr", "Raw Pwr",
          "Spd", "FV", "PA", "OBP", "SLG", "ISO", "BB%", "K%", "wRC+", "playerId"]


def entry(name, age, fv, top100=None, org_rk=None, fg_id=None):
    return {"fg_id": fg_id or name, "name": name, "key": C.norm_name(name), "age": age,
            "fv": fv, "top100": top100, "org_rk": org_rk}


def player(pid, name, age):
    return {"player_id": pid, "name": name, "age": age}


class TestNames(unittest.TestCase):
    def test_accents_case_punctuation_suffixes(self):
        self.assertEqual(C.norm_name("Jesús  Báez"), "jesus baez")
        self.assertEqual(C.norm_name("Bobby Witt Jr."), "bobby witt")
        self.assertEqual(C.norm_name("J.C. Escarra"), "jc escarra")
        self.assertEqual(C.norm_name("Logan O'Hoppe"), "logan ohoppe")
        self.assertEqual(C.norm_name("Jean-Carlos Mejia"), "jean carlos mejia")
        self.assertEqual(C.norm_name("James Tibbs III"), "james tibbs")

    def test_witt_is_not_witte(self):
        self.assertNotEqual(C.norm_name("Bobby Witt Jr."), C.norm_name("Bobby Witte"))


class TestBoard(unittest.TestCase):
    def test_parse_fv(self):
        self.assertEqual(C.parse_fv("45+"), 47.5)
        self.assertEqual(C.parse_fv("50"), 50.0)
        self.assertIsNone(C.parse_fv(""))
        self.assertIsNone(C.parse_fv(None))

    def test_load_board(self):
        def row(name, age, top, org, fv, pid):
            r = dict.fromkeys(HEADER, "")
            r.update({"Name": name, "Age": age, "Top 100": top, "Org Rk": org, "FV": fv, "playerId": pid})
            return r
        rows = [row("Dixon Machado", "24", "0", "7", "45", "11472"),     # 2017/18 style: 0 = unranked
                row("Top Guy", "20.5", "3", "1", "60", "sa1"),
                row("Top Guy", "20.5", "3", "1", "60", "sa1"),           # duplicate id: kept once
                row("No Grade", "19", "", "", "", "sa2")]                # no FV: not graded
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=HEADER)
                w.writeheader()
                w.writerows(rows)
            board = C.load_board(path)
        self.assertEqual([e["fg_id"] for e in board], ["11472", "sa1"])
        self.assertIsNone(board[0]["top100"])
        self.assertEqual(board[0]["org_rk"], 7)
        self.assertEqual(board[1]["top100"], 3)
        self.assertEqual(board[1]["age"], 20.5)
        self.assertEqual(board[1]["key"], "top guy")

    def test_fv_order(self):
        # FV first; within a grade any Top 100 player beats any unranked one; then org rank
        e = C.fv_score(entry("e", 20, 50.0, top100=1, org_rk=1))
        a = C.fv_score(entry("a", 20, 50.0, top100=90, org_rk=3))
        b = C.fv_score(entry("b", 20, 50.0, org_rk=1))
        c = C.fv_score(entry("c", 20, 50.0, org_rk=2))
        d = C.fv_score(entry("d", 20, 47.5, top100=1, org_rk=1))
        self.assertTrue(e > a > b > c > d)
        self.assertEqual(C.fv_score(entry("f", 20, 40.0)), 40.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_consensus -v`
Expected: ERROR, `ModuleNotFoundError` / `ImportError` for `psmodel.consensus`.

- [ ] **Step 3: Write the implementation**

Create `prospects-model/psmodel/consensus.py`:

```python
"""Plan C: does the model beat just following FanGraphs' FV?

The Board lists are the user's manual exports (cache/fv/board_<year>_hitters.csv,
gitignored, never committed). Only the grade columns (FV, Top 100, Org Rk) and the
name and age for matching are read; the Board's stat columns aren't as-of. The
Board carries no MLBAM id, so players are matched by name with an age guard, and
every same-name case is listed, never guessed (the Witt -> Witte lesson).
"""
import csv
import os
import unicodedata

import numpy as np
from scipy.stats import rankdata
from sklearn.linear_model import LinearRegression, LogisticRegression

from . import walkforward as W

AGE_TOLERANCE = 1.5      # years either side of the list's calibrated age offset
SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})
VERDICTS = ("follow FV", "model as tiebreaker", "model leads")     # most cautious first
CHANCE = {"rating": 0.0, "soon": 0.5}                              # Spearman, AUC
MIN_H2H = 30
N_BOOT = 300


def board_path(root, year):
    return os.path.join(root, f"board_{year}_hitters.csv")


def norm_name(name):
    """Accents folded, lowercase, punctuation and Jr./II-style suffixes dropped."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace("-", " ")
    for ch in ".,'’":
        s = s.replace(ch, "")
    return " ".join(t for t in s.split() if t not in SUFFIXES)


def parse_fv(text):
    """'45+' -> 47.5; blank -> None."""
    s = (text or "").strip()
    if not s:
        return None
    fv = float(s.rstrip("+")) + (2.5 if s.endswith("+") else 0.0)
    return fv if fv > 0 else None


def _rank(text):
    """Top 100 / Org Rk: blank, or 0 on the 2017-18 lists, means unranked."""
    s = (text or "").strip()
    return int(float(s)) if s and float(s) > 0 else None


def _num(text):
    s = (text or "").strip()
    return float(s) if s else None


def load_board(path):
    """Graded hitters from one Board export: [{fg_id, name, key, age, fv, top100, org_rk}]."""
    out, seen = [], set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            fv = parse_fv(r.get("FV"))
            if fv is None or r["playerId"] in seen:
                continue
            seen.add(r["playerId"])
            out.append({"fg_id": r["playerId"], "name": r["Name"], "key": norm_name(r["Name"]),
                        "age": _num(r.get("Age")), "fv": fv,
                        "top100": _rank(r.get("Top 100")), "org_rk": _rank(r.get("Org Rk"))})
    return out


def fv_score(e):
    """FanGraphs' order as one number, higher = better: FV, then Top 100, then org
    rank. Grades sit >= 2.5 apart and the tiebreaks add < 2, so they never cross a grade."""
    if e["top100"]:
        return e["fv"] + 1.0 + (101 - e["top100"]) / 101
    if e["org_rk"]:
        return e["fv"] + 0.9 * (1000 - min(e["org_rk"], 999)) / 1000
    return e["fv"]
```

(`np`, `rankdata`, `LinearRegression`, `LogisticRegression` and `W` are used by Tasks 2–4; leave the imports in.)

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_consensus -v`
Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/consensus.py tests/test_consensus.py
git commit -m "feat(3c-C): Board loading, name normalization and FanGraphs' FV order"
```
`git ls-files cache` must print nothing before the commit.

---

### Task 2: Matching our class to a Board list

**Files:**
- Modify: `prospects-model/psmodel/consensus.py` (append)
- Test: `prospects-model/tests/test_consensus.py` (add a class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_consensus.py`, above the `if __name__` line:

```python
class TestMatch(unittest.TestCase):
    def test_offset_calibrated_and_age_guard(self):
        # this list's ages run ~0.85 yr above StatsAPI season age
        board = [entry("Ann Able", 20.8, 50), entry("Bo Baker", 22.9, 45), entry("Cy Cole", 19.7, 40),
                 entry("Dee Dunn", 27.0, 40)]
        ours = [player(1, "Ann Able", 20), player(2, "Bo Baker", 22), player(3, "Cy Cole", 19),
                player(4, "Dee Dunn", 21), player(5, "Eve Ekk", 20), player(6, "Ann Able", None)]
        m = C.match(ours[:5], board)
        self.assertAlmostEqual(m["offset"], 0.85)          # median of 0.8, 0.9, 0.7, 6.0
        self.assertEqual(set(m["matched"]), {1, 2, 3})
        self.assertEqual(m["matched"][2]["name"], "Bo Baker")
        self.assertEqual(m["age_rejected"], {4})           # same name, 5 years off: a different person
        self.assertEqual(m["ambiguous"], [])
        self.assertIn(6, C.match([ours[5]], board)["age_rejected"])   # no age: never accepted

    def test_same_name_is_ambiguous_never_guessed(self):
        board = [entry("Luis Garcia", 21.0, 45, fg_id="x"), entry("Luis Garcia", 21.5, 40, fg_id="y"),
                 entry("Ann Able", 20.0, 50)]
        m = C.match([player(1, "Luis García", 21), player(2, "Ann Able", 20)], board)
        self.assertEqual(set(m["matched"]), {2})
        self.assertEqual([a["player_id"] for a in m["ambiguous"]], [1])
        self.assertEqual(len(m["ambiguous"][0]["candidates"]), 2)

    def test_two_of_ours_claiming_one_entry_are_ambiguous(self):
        board = [entry("Jose Ramos", 20.0, 45), entry("Ann Able", 20.0, 50)]
        ours = [player(1, "Jose Ramos", 20), player(2, "José Ramos", 21), player(3, "Ann Able", 20)]
        m = C.match(ours, board)
        self.assertEqual(set(m["matched"]), {3})
        self.assertEqual(sorted(a["player_id"] for a in m["ambiguous"]), [1, 2])
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_consensus -v`
Expected: the 3 new tests ERROR with `AttributeError: module 'psmodel.consensus' has no attribute 'match'`.

- [ ] **Step 3: Write the implementation**

Append to `psmodel/consensus.py`:

```python
def _cand(e):
    return f"{e['name']} ({e['fg_id']}, age {e['age']}, FV {e['fv']:g})"


def match(players, board):
    """Link our players [{player_id, name, age}] to one Board list by name, guarded by age.

    The Board's age is taken at a date that differs by list, so the offset (Board
    age - StatsAPI season age) is calibrated as the median over names unique on both
    sides; a candidate must sit within AGE_TOLERANCE of it. Returns
    {"matched": {player_id: entry}, "ambiguous": [{player_id, name, age, candidates}],
     "age_rejected": {player_id}, "offset": float}. A name with no Board entry at all
    is simply absent from every field (ungraded)."""
    by_key = {}
    for e in board:
        by_key.setdefault(e["key"], []).append(e)
    ours = {}
    for p in players:
        ours.setdefault(norm_name(p["name"]), []).append(p)
    diffs = [by_key[k][0]["age"] - ps[0]["age"] for k, ps in ours.items()
             if len(ps) == 1 and len(by_key.get(k, ())) == 1
             and by_key[k][0]["age"] is not None and ps[0]["age"] is not None]
    offset = float(np.median(diffs)) if diffs else 0.0

    ambiguous, rejected, claims = [], set(), {}
    for p in players:
        named = by_key.get(norm_name(p["name"]), [])
        if not named:
            continue
        cands = [e for e in named if p["age"] is not None and e["age"] is not None
                 and abs(e["age"] - p["age"] - offset) <= AGE_TOLERANCE]
        if not cands:
            rejected.add(p["player_id"])
        elif len(cands) > 1:
            ambiguous.append({"player_id": p["player_id"], "name": p["name"], "age": p["age"],
                              "candidates": [_cand(e) for e in cands]})
        else:
            claims.setdefault(cands[0]["fg_id"], (cands[0], []))[1].append(p)
    matched = {}
    for e, ps in claims.values():
        if len(ps) == 1:
            matched[ps[0]["player_id"]] = e
        else:
            ambiguous += [{"player_id": p["player_id"], "name": p["name"], "age": p["age"],
                           "candidates": [_cand(e)]} for p in ps]
    return {"matched": matched, "ambiguous": ambiguous, "age_rejected": rejected, "offset": offset}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_consensus -v`
Expected: 8 tests, OK.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/consensus.py tests/test_consensus.py
git commit -m "feat(3c-C): name + calibrated-age matching to a Board list; same names listed, never guessed"
```

---

### Task 3: Scoring, verdict and the fitted blend

**Files:**
- Modify: `prospects-model/psmodel/consensus.py` (append)
- Test: `prospects-model/tests/test_consensus.py` (add classes)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_consensus.py`, above the `if __name__` line:

```python
def soon_rows(y):
    return [{"player_id": i, "y": float(v)} for i, v in enumerate(y)]


def cls(d, se, t50_base=0.5, t50_fam=0.5):
    return {"base": {"top50": t50_base}, "fam": {"top50": t50_fam}, "d": d, "se": se}


WIN = {2021: cls(0.05, 0.01), 2022: cls(0.03, 0.01), 2023: cls(0.0, 0.01)}
LOSE = {2021: cls(-0.01, 0.01), 2022: cls(0.0, 0.01), 2023: cls(0.005, 0.01)}


class TestScoring(unittest.TestCase):
    def test_pct_averages_ties(self):
        np.testing.assert_allclose(C.pct([3, 1, 1, 2]), [1.0, 0.375, 0.375, 0.75])

    def test_head_to_head_positive_when_challenger_is_better(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 200)
        res = C.head_to_head(soon_rows(y), y + rng.normal(0, 3.0, 200), y + rng.normal(0, 0.3, 200),
                             "soon", None)
        self.assertGreater(res["d"], 0)
        self.assertGreater(res["fam"]["rank"], res["base"]["rank"])
        self.assertIn("top50", res["base"])

    def test_head_to_head_none_when_untestable(self):
        self.assertIsNone(C.head_to_head(soon_rows([0] * 40), np.arange(40), np.arange(40), "soon", None))
        self.assertIsNone(C.head_to_head(soon_rows([0, 1] * 10), np.arange(20), np.arange(20), "soon", None))

    def test_rank_ci_brackets_point_and_clears_chance_for_a_good_ranker(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, 150)
        pt, lo, hi = C.rank_ci(soon_rows(y), y + rng.normal(0, 0.5, 150), "soon")
        self.assertTrue(lo <= pt <= hi)
        self.assertGreater(lo, 0.5)

    def test_rank_ci_none_when_one_outcome(self):
        self.assertIsNone(C.rank_ci(soon_rows([0] * 50), np.arange(50), "soon"))


class TestVerdict(unittest.TestCase):
    def test_model_leads(self):
        self.assertEqual(C.verdict(WIN, LOSE), "model leads")

    def test_tiebreaker_when_only_the_blend_wins(self):
        self.assertEqual(C.verdict(LOSE, WIN), "model as tiebreaker")

    def test_harm_veto_means_follow_fv(self):
        harm = {2021: cls(0.05, 0.01), 2022: cls(0.03, 0.01), 2023: cls(-0.03, 0.01)}
        self.assertEqual(C.verdict(harm, harm), "follow FV")

    def test_top50_tolerance(self):
        drop = {v: cls(r["d"], r["se"], 0.5, 0.4) for v, r in WIN.items()}
        self.assertEqual(C.verdict(drop, drop), "follow FV")

    def test_missing_classes_are_unavailable(self):
        one = {2019: None, 2021: cls(0.05, 0.01), 2022: None}
        self.assertEqual(C.verdict(one, one), "follow FV")

    def test_cautious(self):
        self.assertEqual(C.cautious("model leads", "model as tiebreaker"), "model as tiebreaker")
        self.assertEqual(C.cautious("follow FV", "model leads"), "follow FV")

    def test_sleepers_ok(self):
        self.assertTrue(C.sleepers_ok({1: (0.2, 0.05, 0.3), 2: (0.1, 0.01, 0.2), 3: None}, "rating"))
        self.assertFalse(C.sleepers_ok({1: (0.6, 0.45, 0.7), 2: (0.7, 0.55, 0.8), 3: None}, "soon"))


class TestBlend(unittest.TestCase):
    def test_fitted_blend_leans_on_the_informative_input(self):
        rng = np.random.default_rng(2)
        y = rng.integers(0, 2, 400).astype(float)
        pm = C.pct(y + rng.normal(0, 0.3, 400))
        pf = C.pct(rng.normal(0, 1, 400))
        m = C.fit_blend(pm, pf, y, "soon")
        self.assertGreater(m.coef_[0][0], abs(m.coef_[0][1]))
        self.assertEqual(C.apply_blend(m, pm, pf, "soon").shape, (400,))
        r = C.fit_blend(pm, pf, y * 3.0, "rating")
        self.assertGreater(r.coef_[0], abs(r.coef_[1]))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_consensus -v`
Expected: the new tests ERROR with `AttributeError` (`pct`, `head_to_head`, …).

- [ ] **Step 3: Write the implementation**

Append to `psmodel/consensus.py`:

```python
def pct(x):
    """Percentile ranks in (0, 1], ties averaged."""
    x = np.asarray(x, dtype=float)
    return rankdata(x) / len(x)


def head_to_head(test, base, alt, target, ctx):
    """One class in W.adopt's shape: base = FanGraphs' order, alt = the challenger.
    test holds one row per player with 'y'. None if too few players, or (soon)
    only one outcome."""
    if len(test) < MIN_H2H or (target == "soon" and len({r["y"] for r in test}) < 2):
        return None
    base, alt = np.asarray(base, dtype=float), np.asarray(alt, dtype=float)
    d, se = W.paired_gain(test, base, alt, target)
    return {"base": W.metrics(test, base, target, ctx), "fam": W.metrics(test, alt, target, ctx),
            "d": d, "se": se}


def rank_ci(test, pred, target, n_boot=N_BOOT, seed=0):
    """(rank accuracy, 2.5%, 97.5%) from a bootstrap over players (one row each);
    None if untestable."""
    y = np.array([r["y"] for r in test], dtype=float)
    p = np.asarray(pred, dtype=float)
    if len(y) < MIN_H2H or len(set(y)) < 2:
        return None
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) < 2:
            continue
        s = W._rank(target, y[i], p[i])
        if np.isfinite(s):
            stats.append(s)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(W._rank(target, y, p)), float(lo), float(hi)


def verdict(model_res, blend_res):
    """Pre-registered (spec, plan C). {class: head_to_head | None} for each challenger.
    The model leads if it beats FV by the adoption rule; else it's a tiebreaker if
    the simple blend does; else follow FV."""
    if W.adopt(model_res)[0]:
        return VERDICTS[2]
    if W.adopt(blend_res)[0]:
        return VERDICTS[1]
    return VERDICTS[0]


def cautious(a, b):
    return VERDICTS[min(VERDICTS.index(a), VERDICTS.index(b))]


def sleepers_ok(cis, target):
    """Show the model for ungraded hitters only if its sleeper interval clears
    chance at >= 2 classes."""
    return sum(1 for c in cis.values() if c is not None and c[1] > CHANCE[target]) >= 2


def fit_blend(pm, pf, y, target):
    """Information only: a second-stage fit on the two percentile ranks."""
    m = LogisticRegression() if target == "soon" else LinearRegression()
    return m.fit(np.column_stack([pm, pf]), y)


def apply_blend(m, pm, pf, target):
    X = np.column_stack([pm, pf])
    return m.predict_proba(X)[:, 1] if target == "soon" else m.predict(X)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_consensus -v`
Expected: 21 tests, OK.

Run: `python -m unittest discover -s tests`
Expected: `OK (skipped=3)`, 193 tests.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/consensus.py tests/test_consensus.py
git commit -m "feat(3c-C): head-to-head scoring, sleeper interval and the pre-registered verdict"
```

---

### Task 4: The runner

**Files:**
- Create: `prospects-model/consensus_gate.py`

The runner is glue over already-tested pieces. It is verified by running it (Task 5), matching the other `model3c_*.py` runners, which have no unit tests.

- [ ] **Step 1: Write the runner**

Create `prospects-model/consensus_gate.py`:

```python
"""3c-hitters plan C: the consensus gate -- does the model beat just following FV?

For each test class Y, the prospects that Board list Y+1 grades are ranked three
ways -- FanGraphs' order, the model (fit as-of Y), and the average of the two
percentile ranks -- and scored on the same targets and adoption rule as the
backtests. The verdict rules were fixed in the spec before this ran.

Groups per class: graded (decides); graduates restored from list Y (the guard);
sleepers, i.e. ungraded players (is the model better than chance there?).

Usage:  python consensus_gate.py
Reads cached data and the user's Board exports (cache/fv/). No network. Writes
cache/consensus_report.txt, cache/consensus_verdict.json and
cache/consensus_ambiguous.csv (all gitignored).
"""
import csv
import datetime
import json
import os
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset
from psmodel import consensus as C
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
REPORT = os.path.join(CACHE, "consensus_report.txt")
VERDICT = os.path.join(CACHE, "consensus_verdict.json")
AMBIGUOUS = os.path.join(CACHE, "consensus_ambiguous.csv")
TESTS = {"rating": W.RATING_VANTAGES, "soon": W.SOON_VANTAGES}
INFO = {"rating": (), "soon": (2024,)}      # opened in plan B: reported, never decides
FIRST_LIST, LAST_LIST = 2017, 2026
GRADUATE_PA = 100               # MLB PA in Y+1 marking a player missing from list Y+1 as a graduate
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def safe(text):
    """CSV-injection guard for free-text columns."""
    s = "" if text is None else str(text)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def one_per_player(test, pred):
    """Each player's row at the highest level of that season (lowest sportId)."""
    best = {}
    for r, p in zip(test, pred):
        if r["player_id"] not in best or r["sport_id"] < best[r["player_id"]][0]["sport_id"]:
            best[r["player_id"]] = (r, float(p))
    return [b[0] for b in best.values()], np.array([b[1] for b in best.values()])


def people(test):
    return [{"player_id": r["player_id"], "name": r["name"],
             "age": None if r["age_raw"] is None else float(r["age_raw"])} for r in test]


def fmt(m):
    return f"{m['rank']:.3f} t25 {m['top25']:.2f} t50 {m['top50']:.2f}"


def line(label, res):
    if res is None:
        return f"    {label}: n/a"
    return (f"    {label}: FV {fmt(res['base'])} | challenger {fmt(res['fam'])} | "
            f"gain {res['d']:+.4f} (z {W.z_score(res['d'], res['se']):+.1f})")


def summary(res):
    if res is None:
        return None
    return {"fv": res["base"], "challenger": res["fam"], "gain": res["d"], "se": res["se"],
            "z": W.z_score(res["d"], res["se"])}


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels)
    pa_history = cohorts.mlb_pa_history()
    rows = cohorts.build_rows(cohorts.load_milb(), pa_history,
                              {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    cohorts.add_products(rows)
    with open(os.path.join(CACHE, "model3c_final.json"), encoding="utf-8") as fh:
        dec = json.load(fh)
    boards = {y: C.load_board(C.board_path(FV_DIR, y)) for y in range(FIRST_LIST, LAST_LIST + 1)
              if os.path.exists(C.board_path(FV_DIR, y))}
    missing = sorted({v + 1 for t in TESTS for v in TESTS[t] + INFO[t]} - set(boards))
    if missing:
        raise SystemExit(f"Board lists missing from {FV_DIR}: {missing}")

    memo = {}

    def scored(t, c, ctx_y):
        """(one row per player, y on ctx_y; model score) for class c, the model fit as-of c."""
        if (t, c) not in memo:
            got = W.predictions(rows, dec[t]["keys"], t, dec[t]["kind"], {c: asof.ref_curve(labels, c)}, (c,),
                                unseal=c in INFO[t])
            memo[(t, c)] = one_per_player(*got[c]) if c in got else ([], np.array([]))
        test, pred = memo[(t, c)]
        return [dict(r, y=W._y(r, t, ctx_y)) for r in test], pred

    def groups(t, c, ctx_y):
        test, pred = scored(t, c, ctx_y)
        nxt = C.match(people(test), boards[c + 1])
        prev = C.match(people(test), boards[c]) if c in boards else None
        skip = nxt["age_rejected"] | {a["player_id"] for a in nxt["ambiguous"]}
        graded, restored, sleepers = [], [], []
        for r, p in zip(test, pred):
            pid = r["player_id"]
            if pid in nxt["matched"]:
                graded.append((r, p, C.fv_score(nxt["matched"][pid])))
            elif pid in skip:
                continue
            elif prev and pid in prev["matched"] and pa_history.get(pid, {}).get(c + 1, 0) >= GRADUATE_PA:
                restored.append((r, p, C.fv_score(prev["matched"][pid])))
            else:
                sleepers.append((r, p))
        return nxt, graded, restored, sleepers

    def challenge(group, t, ctx):
        """(model vs FV, simple blend vs FV) on one group of graded players."""
        if not group:
            return None, None
        test = [g[0] for g in group]
        pm, pf = C.pct([g[1] for g in group]), C.pct([g[2] for g in group])
        return C.head_to_head(test, pf, pm, t, ctx), C.head_to_head(test, pf, (pm + pf) / 2, t, ctx)

    def fitted(t, v, ctx, group):
        """Information only: a blend fit on earlier classes that have a list, each
        scored by its own as-of model."""
        known = asof.rating_known if t == "rating" else asof.soon_known
        pm_all, pf_all, ys = [], [], []
        for c in range(FIRST_LIST - 1, v):
            if c not in cohorts.MILB_SEASONS or c + 1 not in boards or not known(c, v):
                continue
            _, g, _, _ = groups(t, c, ctx)
            if g:
                pm_all += list(C.pct([x[1] for x in g]))
                pf_all += list(C.pct([x[2] for x in g]))
                ys += [x[0]["y"] for x in g]
        if not group or len(ys) < C.MIN_H2H or (t == "soon" and len(set(ys)) < 2):
            return None
        m = C.fit_blend(np.array(pm_all), np.array(pf_all), np.array(ys), t)
        test = [g[0] for g in group]
        pm, pf = C.pct([g[1] for g in group]), C.pct([g[2] for g in group])
        return C.head_to_head(test, pf, C.apply_blend(m, pm, pf, t), t, ctx)

    L = ["3c-HITTERS CONSENSUS GATE (plan C): does the model beat just following FV?",
         "Class Y vs Board list Y+1 (preseason; built from information through Y). Base model, fit as-of Y.",
         "Each line: FanGraphs' order vs the challenger on the same players; z = gain in noise-widths.", ""]
    out, ambiguous = {"generated": datetime.date.today().isoformat()}, {}
    for t in ("rating", "soon"):
        L.append(f"{t.upper()} ({dec[t]['kind']}; features: {', '.join(dec[t]['keys'])})")
        res = {k: {} for k in ("model", "blend", "model_r", "blend_r")}
        cis, classes = {}, {}
        for v in TESTS[t] + INFO[t]:
            ctx = asof.ref_curve(labels, v)
            nxt, graded, restored, sleepers = groups(t, v, ctx)
            for a in nxt["ambiguous"]:
                ambiguous[(v + 1, a["player_id"])] = a
            mo, bl = challenge(graded, t, ctx)
            mo_r, bl_r = challenge(graded + restored, t, ctx)
            ci = C.rank_ci([s[0] for s in sleepers], [s[1] for s in sleepers], t) if sleepers else None
            fit = fitted(t, v, ctx, graded)
            info = v in INFO[t]
            if not info:
                res["model"][v], res["blend"][v], res["model_r"][v], res["blend_r"][v] = mo, bl, mo_r, bl_r
                cis[v] = ci
            L.append(f"  class {v} vs list {v + 1}{'  (INFORMATION ONLY: opened in plan B)' if info else ''}: "
                     f"graded {len(graded)}, ungraded {len(sleepers)}, graduates restored {len(restored)}, "
                     f"ambiguous {len(nxt['ambiguous'])}, age-rejected {len(nxt['age_rejected'])}, "
                     f"age offset {nxt['offset']:+.2f}")
            L += [line("model", mo), line("blend (average of percentiles)", bl),
                  line("model, graduates restored", mo_r), line("blend, graduates restored", bl_r),
                  line("fitted blend (information only)", fit),
                  "    sleepers: n/a" if ci is None else
                  f"    sleepers: model rank accuracy {ci[0]:.3f} [{ci[1]:.3f}, {ci[2]:.3f}] "
                  f"(chance {C.CHANCE[t]:.1f}, n={len(sleepers)})"]
            classes[str(v)] = {"list": v + 1, "information_only": info, "n_graded": len(graded),
                               "n_ungraded": len(sleepers), "n_restored": len(restored),
                               "n_ambiguous": len(nxt["ambiguous"]), "n_age_rejected": len(nxt["age_rejected"]),
                               "age_offset": nxt["offset"], "model": summary(mo), "blend": summary(bl),
                               "model_restored": summary(mo_r), "blend_restored": summary(bl_r),
                               "fitted_blend": summary(fit), "sleepers": ci}
        main_v = C.verdict(res["model"], res["blend"])
        rest_v = C.verdict(res["model_r"], res["blend_r"])
        final, show = C.cautious(main_v, rest_v), C.sleepers_ok(cis, t)
        _, mw, ma = W.adopt(res["model"])
        _, bw, ba = W.adopt(res["blend"])
        L += [f"  model beat FV (>= 1 SE) in {mw}/{ma} classes; blend beat FV in {bw}/{ba}",
              f"  VERDICT ({t}): {final.upper()}"
              + (f"  [UNSTABLE: graded-only says '{main_v}', graduates-restored says '{rest_v}'; "
                 f"the more cautious stands]" if main_v != rest_v else ""),
              f"  model shown for ungraded hitters: {'yes' if show else 'no'}", ""]
        out[t] = {"verdict": final, "verdict_graded": main_v, "verdict_restored": rest_v,
                  "unstable": main_v != rest_v, "show_model_for_ungraded": show, "classes": classes}

    with open(AMBIGUOUS, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["list", "player_id", "name", "age", "board_candidates"])
        for (lst, pid), a in sorted(ambiguous.items()):
            wr.writerow([lst, pid, safe(a["name"]), a["age"], safe("; ".join(a["candidates"]))])
    L.append(f"{len(ambiguous)} ambiguous same-name cases left out -> {AMBIGUOUS}")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Static check**

Run: `python -c "import consensus_gate"`
Expected: no output, no error.

- [ ] **Step 3: Commit**

```bash
git ls-files cache
git add consensus_gate.py
git commit -m "feat(3c-C): consensus gate runner -- model vs FV on graded, restored and ungraded groups"
```

---

### Task 5: Run it, then hand to Opus

- [ ] **Step 1: Run**

Run: `python consensus_gate.py`
Expected: it finishes in a few minutes and prints the report, which has:
- A block for RATING and one for SOON.
- Per class: the group counts and five head-to-head lines (model, blend, both restored, fitted blend) plus a sleepers line.
- Per output: a `VERDICT` line and a "model shown for ungraded hitters" line.
- A closing count of ambiguous cases.

Sanity checks (stop and report if any fails; don't patch around it):
- **Graded count per class:** roughly 250–450 (the 2023 dry run matched 396 of 544 Board hitters, before key completeness and one-per-player).
- **Age offset:** within about −0.5 … +1.5 for every list. The 2023/2024 lists carry mid-season ages; 2025/2026 share one date.
- **Ambiguous:** a handful per list, not dozens.
- **Classes:** rating uses 2019/2021/2022, soon uses 2021/2022/2023, and soon 2024 is labelled INFORMATION ONLY.

- [ ] **Step 2: Confirm outputs stayed out of git**

Run: `git status --short; git ls-files cache`
Expected: no `cache/` paths listed by either.

- [ ] **Step 3: Stop and hand to Opus**

Do not write the result into the spec or memory on a cheaper model. Tell the user the run is done and ask them to switch to Opus to review:
- `cache/consensus_report.txt`
- `cache/consensus_ambiguous.csv`

The Opus review:
- Spot-checks matches (Witt-style cases) and the restored graduates.
- Writes "Plan C result" into the 3c spec and updates `project_prospect_model.md`.
- Tells the user what the verdict means for the shopping list (sub-project 4).

The verdict itself is mechanical and pre-registered; the review checks the plumbing, not whether we like the answer.
