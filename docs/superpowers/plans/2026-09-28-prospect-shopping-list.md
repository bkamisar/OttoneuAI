# Prospect Shopping List (sub-project 4): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the model to the Prospects page so FanGraphs and the model are used together, following plan C's rules.

**Architecture:** All matching and math live in Python.
- `prospects-model/psmodel/shopping.py` holds pure, tested functions and reuses plan C's `consensus.py`.
- `build_shopping_list.py` writes `data/prospect_model.json`.
- `prospects.html` only displays it. It fetches the JSON directly (like `hot.json` in `hot.html`), so `shared.js` is not touched.

**Tech Stack:** Python 3 (stdlib, numpy, already installed), `unittest`; plain JS/HTML, `textContent`-only rendering.

**Spec:** `docs/superpowers/specs/2026-09-28-prospect-shopping-list-design.md`

---

## Ground rules

- **Where to run:**
  - Python: from `prospects-model/`. Tests: `python -m unittest discover -s tests`. Before this plan: **193 pass, 3 skipped**.
  - The page: from the repo root, served with the preview server (`.claude/launch.json`, config `test` = `python -m http.server 8000`).
- **No network steps.** Everything reads local files.
- **Nothing from `cache/` is ever committed.** `git ls-files prospects-model/cache` must print nothing before each commit. `data/prospect_model.json` **is** committed: it holds only model numbers, derived ranks, takes, flags and the board's own `Name|Org` key.
- **Git:**
  - Commit locally after each task, ending messages with the session's Co-Authored-By line.
  - **Never push, fetch or pull.**
- **Rendering:** new page code uses `textContent` only, never `innerHTML` with data.

## File structure

- Create `prospects-model/psmodel/shopping.py`: the board-file loader, ratings loader, odds rounding, take text, and the join/blend build.
- Create `prospects-model/tests/test_shopping.py`.
- Create `prospects-model/build_shopping_list.py`: the runner, which writes `data/prospect_model.json`.
- Modify `prospects.html`: the lens toggle, the Ungraded view, the two columns, and the note line.

Existing code used:
- `psmodel/consensus.py`: `norm_name`, `parse_fv`, `_num`, `_rank`, `fv_score`, `match`, `pct`, `load_board`, `board_path`.
- `psmodel/cohorts.py`: `CURRENT_SEASON`.
- `shared.js`: `normalizeName`, `loadData`, `autoLoadFromRepo`.
- `cache/hitter_ratings.csv` columns: `player_id,name,level,age,rating_sgp,rating_percentile,p_useful_within_2,tracking_in_rating,tracking_in_soon,flags`. Names carrying the CSV-injection guard start with `'` followed by one of `= + - @`.
- `data/prospects.csv`: the header row contains `Name` and `FV` (plus `Top 100, Org Rk, Org, Pos, Current Level, ETA, Age`, …). Pitchers have `Pos` in `P/SP/RP/RHP/LHP`.

---

### Task 0: Preflight

- [ ] **Step 1:** Run `python -m unittest discover -s tests` (in `prospects-model/`). Expected: `OK (skipped=3)`, 193 tests.
- [ ] **Step 2:** Run `ls cache/hitter_ratings.csv ../data/prospects.csv cache/fv/board_2026_hitters.csv && git ls-files cache`. Expected: the three paths, and nothing from `git ls-files`.

---

### Task 1: Loaders, odds and the take line

**Files:**
- Create: `prospects-model/psmodel/shopping.py`
- Test: `prospects-model/tests/test_shopping.py`

- [ ] **Step 1: Write the failing tests**

Create `prospects-model/tests/test_shopping.py`:

```python
import csv
import os
import tempfile
import unittest

from psmodel import consensus as C
from psmodel import shopping as S


def entry(name, age, fv, fg_id, top100=None, org_rk=None):
    return {"fg_id": fg_id, "name": name, "key": C.norm_name(name), "age": age,
            "fv": fv, "top100": top100, "org_rk": org_rk}


def rated(pid, name, age, rating, soon, rating_pct):
    return {"player_id": pid, "name": name, "level": "AA", "age": age, "rating": rating,
            "rating_pct": rating_pct, "soon": soon}


def write_csv(d, name, rows, encoding="utf-8"):
    path = os.path.join(d, name)
    with open(path, "w", encoding=encoding, newline="") as fh:
        csv.writer(fh).writerows(rows)
    return path


class TestBoardFile(unittest.TestCase):
    def test_load_current_board(self):
        header = ["Top 100", "Org Rk", "Name", "Org", "Pos", "Current Level", "ETA", "FV", "Age"]
        rows = [["Report", "x"],                                                  # preamble line
                header,
                ["", "3", "Ann Able", "SEA", "SS", "AA", "2027", "45+", "20.5"],
                ["", "4", "Pat Pitch", "SEA", "P", "AA", "2027", "50", "22.0"],     # pitcher: skipped
                ["", "3", "Ann Able", "SEA", "SS", "AA", "2027", "45+", "20.5"],    # duplicate: skipped
                ["", "9", "No Grade", "SEA", "C", "A", "2029", "", "19.0"]]         # no FV: skipped
        with tempfile.TemporaryDirectory() as d:
            board = S.load_current_board(write_csv(d, "prospects.csv", rows, "utf-8-sig"))
        self.assertEqual(len(board), 1)
        e = board[0]
        self.assertEqual(e["fg_id"], "Ann Able|SEA")
        self.assertEqual((e["fv"], e["age"], e["org_rk"], e["top100"], e["key"]),
                         (47.5, 20.5, 3, None, "ann able"))

    def test_missing_header_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_csv(d, "bad.csv", [["a", "b"], ["1", "2"]])
            with self.assertRaises(ValueError):
                S.load_current_board(path)

    def test_load_ratings_undoes_the_csv_guard(self):
        header = ["player_id", "name", "level", "age", "rating_sgp", "rating_percentile",
                  "p_useful_within_2", "tracking_in_rating", "tracking_in_soon", "flags"]
        rows = [header,
                ["1", "'=Odd Name", "AAA", "21", "0.5", "99.0", "0.25", "yes", "no", ""],
                ["2", "'Tis Name", "AA", "", "0.1", "10.0", "0.01", "no", "no", ""]]
        with tempfile.TemporaryDirectory() as d:
            r = S.load_ratings(write_csv(d, "ratings.csv", rows))
        self.assertEqual(r[0], {"player_id": 1, "name": "=Odd Name", "level": "AAA", "age": 21.0,
                                "rating": 0.5, "rating_pct": 0.99, "soon": 0.25})
        self.assertEqual((r[1]["name"], r[1]["age"]), ("'Tis Name", None))


class TestText(unittest.TestCase):
    def test_odds_round_to_five(self):
        self.assertEqual([S.odds(p) for p in (0.6, 0.188, 0.03, 0.024, 0.0)], [60, 20, 5, 0, 0])

    def test_take(self):
        self.assertEqual(S.take(0.3, 0.0), "Model: readier than the grade suggests")
        self.assertEqual(S.take(-0.3, 0.1), "Model: further away than the grade suggests")
        self.assertEqual(S.take(0.1, 0.4), "Model likes the bat more (ceiling: unproven)")
        self.assertEqual(S.take(0.0, -0.5), "Model likes the bat less (ceiling: unproven)")
        self.assertEqual(S.take(0.3, -0.3),
                         "Model: readier than the grade suggests; likes the bat less (ceiling: unproven)")
        self.assertEqual(S.take(0.2, -0.2), "Model agrees")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_shopping -v`
Expected: ERROR, `ImportError: cannot import name 'shopping'`.

- [ ] **Step 3: Write the implementation**

Create `prospects-model/psmodel/shopping.py`:

```python
"""Sub-project 4: the data behind the prospect shopping list.

Joins the model's hitter ratings to the site's current FanGraphs board with plan
C's tested matching, and applies plan C's rules: FanGraphs' order for "how good",
the average of the FV and model percentiles for "closest to helping", and the
model alone for hitters FanGraphs doesn't grade. Only derived numbers, flags and
the board's own Name|Org key are written -- never FanGraphs grades.
"""
import csv

import numpy as np

from . import consensus as C

PITCHER_POS = frozenset({"p", "sp", "rp", "rhp", "lhp"})
DISAGREE = 0.25      # percentile points before the take mentions a disagreement
NEVER_LISTED = "Never on a FanGraphs list"


def board_key(name, org):
    """The page's join key: rawName|org exactly as written in data/prospects.csv."""
    return f"{name.strip()}|{org.strip()}"


def _cell(row, idx, header):
    i = idx.get(header)
    return row[i].strip() if i is not None and i < len(row) else ""


def load_current_board(path):
    """Graded hitters from the site's board file, shaped like consensus.load_board
    entries, with fg_id = the Name|Org join key. Pitchers are skipped."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head = next((i for i, r in enumerate(rows[:6]) if "Name" in r and "FV" in r), None)
    if head is None:
        raise ValueError(f"no Name/FV header in {path}")
    idx = {h.strip(): i for i, h in enumerate(rows[head])}
    out, seen = [], set()
    for r in rows[head + 1:]:
        name, fv = _cell(r, idx, "Name"), C.parse_fv(_cell(r, idx, "FV"))
        if not name or fv is None or _cell(r, idx, "Pos").lower() in PITCHER_POS:
            continue
        key = board_key(name, _cell(r, idx, "Org"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"fg_id": key, "name": name, "key": C.norm_name(name), "age": C._num(_cell(r, idx, "Age")),
                    "fv": fv, "top100": C._rank(_cell(r, idx, "Top 100")),
                    "org_rk": C._rank(_cell(r, idx, "Org Rk"))})
    return out


def _unguard(s):
    """Undo the CSV-injection guard model3c_final.py puts on names."""
    return s[1:] if len(s) > 1 and s[0] == "'" and s[1] in "=+-@" else s


def load_ratings(path):
    """The model's hitters from cache/hitter_ratings.csv (model3c_final.py)."""
    with open(path, encoding="utf-8", newline="") as fh:
        return [{"player_id": int(r["player_id"]), "name": _unguard(r["name"]), "level": r["level"],
                 "age": C._num(r["age"]), "rating": float(r["rating_sgp"]),
                 "rating_pct": float(r["rating_percentile"]) / 100, "soon": float(r["p_useful_within_2"])}
                for r in csv.DictReader(fh)]


def odds(p):
    """The 2-year probability as a whole percent rounded to 5; 0 means under 2.5%."""
    return int(round(p * 20)) * 5


def take(d_soon, d_rating):
    """One plain-language line on where the model disagrees with FanGraphs.
    d_* = model percentile - FV percentile within the pool."""
    soon = ("Model: readier than the grade suggests" if d_soon >= DISAGREE else
            "Model: further away than the grade suggests" if d_soon <= -DISAGREE else None)
    bat = ("likes the bat more (ceiling: unproven)" if d_rating >= DISAGREE else
           "likes the bat less (ceiling: unproven)" if d_rating <= -DISAGREE else None)
    if soon and bat:
        return f"{soon}; {bat}"
    if soon:
        return soon
    if bat:
        return f"Model {bat}"
    return "Model agrees"
```

(`np` is used by Task 2; leave the import in.)

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_shopping -v`
Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/shopping.py tests/test_shopping.py
git commit -m "feat(shopping): board-file and ratings loaders, odds rounding and the take line"
```

---

### Task 2: The join and blend

**Files:**
- Modify: `prospects-model/psmodel/shopping.py` (append)
- Test: `prospects-model/tests/test_shopping.py` (add a class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_shopping.py`, above the `if __name__` line. The worked numbers are in the comments.

```python
class TestBuild(unittest.TestCase):
    def test_build(self):
        # Pool = Ann, Bo, Cy (on the board with a model read). Zed shares a board name
        # but is 10 years off; Dee was on the 2024 list; Eve was never listed.
        ratings = [rated(1, "Ann Able", 20, 0.5, 0.6, 0.9), rated(2, "Bo Baker", 21, 0.1, 0.4, 0.2),
                   rated(3, "Cy Cole", 22, 0.3, 0.1, 0.5), rated(4, "Dee Dunn", 23, 0.4, 0.05, 0.7),
                   rated(5, "Eve Ekk", 19, 0.2, 0.01, 0.3), rated(6, "Zed Zim", 20, 0.35, 0.2, 0.6)]
        board = [entry("Ann Able", 20.0, 45.0, "Ann Able|SEA"), entry("Bo Baker", 21.0, 55.0, "Bo Baker|NYY"),
                 entry("Cy Cole", 22.0, 50.0, "Cy Cole|BOS"), entry("Zed Zim", 30.0, 40.0, "Zed Zim|TEX")]
        history = {2024: [entry("Dee Dunn", 21.0, 45.0, "d")]}
        graded, ungraded, unreadable = S.build(ratings, board, history)
        # fv pct Ann 1/3 Cy 2/3 Bo 1; soon pct Cy 1/3 Bo 2/3 Ann 1; ready Bo .83, Ann .67, Cy .5
        self.assertEqual([(g["key"], g["ready_rank"], g["odds"]) for g in graded],
                         [("Bo Baker|NYY", 1, 40), ("Ann Able|SEA", 2, 60), ("Cy Cole|BOS", 3, 10)])
        takes = {g["key"]: g["take"] for g in graded}
        self.assertEqual(takes["Ann Able|SEA"],
                         "Model: readier than the grade suggests; likes the bat more (ceiling: unproven)")
        self.assertEqual(takes["Bo Baker|NYY"],
                         "Model: further away than the grade suggests; likes the bat less (ceiling: unproven)")
        self.assertEqual(takes["Cy Cole|BOS"], "Model: further away than the grade suggests")
        self.assertEqual([(u["name"], u["listed"], u["take"]) for u in ungraded],
                         [("Dee Dunn", 2024, "On the 2024 list, since dropped"),
                          ("Zed Zim", None, "Name matches a FanGraphs prospect of a different age — check"),
                          ("Eve Ekk", None, "Never on a FanGraphs list")])
        self.assertEqual(ungraded[0]["odds"], 5)
        self.assertEqual(unreadable, [])

    def test_shared_names_are_flagged_not_guessed(self):
        ratings = [rated(1, "Ann Able", 20, 0.5, 0.6, 0.9), rated(2, "Bo Baker", 21, 0.1, 0.4, 0.2),
                   rated(3, "Cy Cole", 22, 0.3, 0.1, 0.5), rated(7, "Luis García", 21, 0.3, 0.3, 0.8)]
        board = [entry("Ann Able", 20.0, 45.0, "A|SEA"), entry("Bo Baker", 21.0, 55.0, "B|NYY"),
                 entry("Cy Cole", 22.0, 50.0, "C|BOS"), entry("Luis Garcia", 21.0, 45.0, "LG1|SEA"),
                 entry("Luis Garcia", 21.5, 40.0, "LG2|NYY")]
        graded, ungraded, unreadable = S.build(ratings, board, {})
        self.assertEqual(len(graded), 3)
        self.assertEqual([(u["player_id"], u["take"]) for u in ungraded],
                         [(7, "Name shared with a FanGraphs prospect — check")])
        self.assertEqual(unreadable, ["LG1|SEA", "LG2|NYY"])
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_shopping -v`
Expected: the 2 new tests ERROR with `AttributeError: module 'psmodel.shopping' has no attribute 'build'`.

- [ ] **Step 3: Write the implementation**

Append to `psmodel/shopping.py`:

```python
def build(ratings, board, history):
    """(graded, ungraded, unreadable_keys).

    graded: board hitters with a model read, by ready_rank (1 = closest to helping,
    ranked on the average of FV and model 2-year percentiles within this pool).
    ungraded: model hitters not on the board, by model rating percentile, each with
    the latest earlier list they appeared on (history = {year: consensus.load_board}).
    unreadable_keys: board rows whose name is shared with a model hitter who can't
    be told apart."""
    people = [{"player_id": r["player_id"], "name": r["name"], "age": r["age"]} for r in ratings]
    by_id = {r["player_id"]: r for r in ratings}
    m = C.match(people, board)
    pids = list(m["matched"])
    graded = []
    if pids:
        rs = [by_id[p] for p in pids]
        es = [m["matched"][p] for p in pids]
        fv_p = C.pct([C.fv_score(e) for e in es])
        soon_p = C.pct([r["soon"] for r in rs])
        rat_p = C.pct([r["rating"] for r in rs])
        rank = np.empty(len(pids), dtype=int)
        rank[np.argsort(-(fv_p + soon_p) / 2, kind="stable")] = np.arange(1, len(pids) + 1)
        graded = sorted(({"key": e["fg_id"], "player_id": r["player_id"], "odds": odds(r["soon"]),
                          "ready_rank": int(k), "take": take(s - f, t - f)}
                         for r, e, f, s, t, k in zip(rs, es, fv_p, soon_p, rat_p, rank)),
                        key=lambda g: g["ready_rank"])

    listed = {}
    for y in sorted(history):                       # ascending, so the latest list wins
        for pid in C.match(people, history[y])["matched"]:
            listed[pid] = y
    amb = {a["player_id"] for a in m["ambiguous"]}
    ungraded = []
    for r in ratings:
        pid = r["player_id"]
        if pid in m["matched"]:
            continue
        if pid in amb:
            note = "Name shared with a FanGraphs prospect — check"
        elif pid in m["age_rejected"]:
            note = "Name matches a FanGraphs prospect of a different age — check"
        elif pid in listed:
            note = f"On the {listed[pid]} list, since dropped"
        else:
            note = NEVER_LISTED
        ungraded.append({"player_id": pid, "name": r["name"], "level": r["level"], "age": r["age"],
                         "rating_pct": r["rating_pct"], "odds": odds(r["soon"]), "listed": listed.get(pid),
                         "take": note})
    ungraded.sort(key=lambda u: -u["rating_pct"])
    amb_names = {C.norm_name(a["name"]) for a in m["ambiguous"]}
    unreadable = sorted(e["fg_id"] for e in board if e["key"] in amb_names)
    return graded, ungraded, unreadable
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_shopping -v` → 7 tests, OK.
Run: `python -m unittest discover -s tests` → `OK (skipped=3)`, 200 tests.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/shopping.py tests/test_shopping.py
git commit -m "feat(shopping): join model to the current board; ready rank, takes, earlier-list flags"
```

---

### Task 3: The runner, and writing `data/prospect_model.json`

**Files:**
- Create: `prospects-model/build_shopping_list.py`
- Create (output, committed): `data/prospect_model.json`

- [ ] **Step 1: Write the runner**

Create `prospects-model/build_shopping_list.py`:

```python
"""Sub-project 4: writes data/prospect_model.json for prospects.html.

Usage:  python build_shopping_list.py
Reads cache/hitter_ratings.csv (model3c_final.py), the site's current FanGraphs
board ../data/prospects.csv, and the old Board lists in cache/fv/ (earlier-list
flag only). No network. Rerun whenever data/prospects.csv or the ratings change,
then commit data/prospects.csv and data/prospect_model.json together.
"""
import datetime
import json
import os

from psmodel import cohorts
from psmodel import consensus as C
from psmodel import shopping as S

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
DATA = os.path.join(os.path.dirname(HERE), "data")
RATINGS = os.path.join(CACHE, "hitter_ratings.csv")
BOARD = os.path.join(DATA, "prospects.csv")
OUT = os.path.join(DATA, "prospect_model.json")
SEASON = cohorts.CURRENT_SEASON


def main():
    ratings = S.load_ratings(RATINGS)
    board = S.load_current_board(BOARD)
    history = {y: C.load_board(C.board_path(FV_DIR, y)) for y in range(2017, SEASON + 1)
               if os.path.exists(C.board_path(FV_DIR, y))}
    graded, ungraded, unreadable = S.build(ratings, board, history)
    counts = {"board_hitters": len(board), "graded_with_model": len(graded),
              "board_without_model": len(board) - len(graded), "ungraded": len(ungraded),
              "unreadable": len(unreadable)}
    out = {"generated": datetime.date.today().isoformat(), "season": SEASON, "counts": counts,
           "graded": graded, "ungraded": ungraded, "unreadable_keys": unreadable}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(json.dumps(counts))
    print("closest to helping, top 10:\n  " + "\n  ".join(
        f"{g['ready_rank']}. {g['key']}  ~{g['odds']}%  {g['take']}" for g in graded[:10]))
    print("ungraded, top 10 by model:\n  " + "\n  ".join(
        f"{u['name']} ({u['level']}, {u['age']}) {u['rating_pct']:.0%}  ~{u['odds']}%  {u['take']}"
        for u in ungraded[:10]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python build_shopping_list.py`

Sanity checks (stop and report if any fails; don't patch around it):
- **`board_hitters`:** several hundred. `graded_with_model` is a few hundred. `board_without_model` is large: rookie-ball and DSL players have no full-season line.
- **`ungraded`:** about 1,431 − `graded_with_model`, since every model hitter lands in one list.
- **Top 10 "closest to helping":** mostly AA/AAA names you'd recognize, not Single-A teenagers.
- **Top 10 ungraded:** mostly older AAA/AA hitters, many "On the <year> list, since dropped".
- **`unreadable`:** 0–5.

- [ ] **Step 3: Check the output is valid and small**

Run: `python -c "import json; d=json.load(open('../data/prospect_model.json', encoding='utf-8')); print(len(d['graded']), len(d['ungraded']), d['graded'][0])"` and `ls -la ../data/prospect_model.json`.
Expected: counts matching Step 2, a graded record with `key/player_id/odds/ready_rank/take`, and a file size under ~400 KB.

- [ ] **Step 4: Commit**

```bash
git ls-files cache
git add build_shopping_list.py ../data/prospect_model.json
git commit -m "feat(shopping): build_shopping_list.py writes data/prospect_model.json (model read joined to the board)"
```

---

### Task 4: The page (`prospects.html`)

**Files:**
- Modify: `prospects.html` (repo root)

Make each edit below with an exact find/replace.

- [ ] **Step 1: CSS.** After the line `    .grades-cell .tool { color: #888; font-weight: 600; }`, add:

```css
    .take-cell { text-align: left !important; font-size: 0.76rem; color: #444; min-width: 220px; }
    .model-note { font-size: 0.8rem; color: #555; margin: 0 0 10px; }
```

- [ ] **Step 2: Lens toggle.** Replace

```html
    <div class="title-row">
      <div class="view-toggle" id="viewToggle" style="display:none">
```
with
```html
    <div class="title-row">
      <div class="view-toggle" id="lensToggle" style="display:none">
        <button id="btnBest" class="active" onclick="setLens('best')">Best prospects</button>
        <button id="btnReady" onclick="setLens('ready')">Closest to helping</button>
      </div>
      <div class="view-toggle" id="viewToggle" style="display:none">
```

- [ ] **Step 3: Ungraded button.** Replace
`        <button class="type-btn" data-type="P">Pitchers</button>`
with
```html
        <button class="type-btn" data-type="P">Pitchers</button>
        <button class="type-btn" data-type="U">Ungraded (model only)</button>
```

- [ ] **Step 4: Note line and headers.** Replace
```html
    <div class="tbl-wrap">
      <table>
```
with
```html
    <div class="model-note" id="modelNote"></div>
    <div class="tbl-wrap">
      <table>
```
Replace `            <th data-col="fv">FV</th>` with `            <th data-col="fv" id="thFv">FV</th>`.
Replace `            <th class="grades-cell">Grades</th>` with
```html
            <th class="grades-cell">Grades</th>
            <th data-col="odds" title="Model: chance of a starter-quality season within 2 years">2-yr odds</th>
            <th class="take-cell">Take</th>
```

- [ ] **Step 5: State.** Replace `    var faOnly     = false;` with
```js
    var faOnly     = false;
    var lens         = 'best';   // 'best' = FanGraphs order; 'ready' = FV + model blend
    var ungradedRows = [];
    var modelInfo    = null;     // from data/prospect_model.json; null if absent
```

- [ ] **Step 6: Helpers.** Replace

```js
    function fvClass(fv) {
```
with
```js
    function setLens(l) {
      lens = l;
      document.getElementById('btnBest').classList.toggle('active', l === 'best');
      document.getElementById('btnReady').classList.toggle('active', l === 'ready');
      if (l === 'ready') { setType('H'); sortCol = 'ready'; sortDir = 1; }
      else { sortCol = 'fv'; sortDir = -1; }
      markSortHeader();
      render();
    }

    function setType(t) {
      typeFilter = t;
      document.querySelectorAll('.type-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.type === t);
      });
      document.getElementById('thFv').textContent = t === 'U' ? 'Model' : 'FV';
    }

    function markSortHeader() {
      document.querySelectorAll('th[data-col]').forEach(function(h) {
        h.classList.remove('sort-asc', 'sort-desc');
        if (h.dataset.col === sortCol) h.classList.add(sortDir === -1 ? 'sort-desc' : 'sort-asc');
      });
    }

    function fmtOdds(o) {
      if (o == null) return '—';
      return o === 0 ? '<5%' : '~' + o + '%';
    }

    // Plain-language model read for a board row (shopping-list spec).
    function boardTake(pr, model, isPitcher) {
      if (isPitcher) return 'FanGraphs only (no pitcher model)';
      if (!modelInfo) return '—';
      if (model) return model.take;
      if (modelInfo.unreadable[pr.rawName + '|' + pr.org]) return 'No model read: name shared by two players';
      return 'No model read: under 150 PA at a full-season level in ' + modelInfo.season;
    }

    function fvClass(fv) {
```

- [ ] **Step 7: Sorting.** Replace
`        case 'fv':      return row.prospect.fv;`
with
`        case 'fv':      return row.ungraded ? row.model.rating_pct : row.prospect.fv;`
and replace
`        case 'surplus': return rowSurplus(row);`
with
```js
        case 'surplus': return rowSurplus(row);
        case 'odds':    return row.model ? row.model.odds : -1;
        case 'ready':   return row.model && row.model.ready_rank ? row.model.ready_rank : 1e9;
```

- [ ] **Step 8: Filtering, count and note.** Replace

```js
      var filtered  = allRows.filter(function(r) {
        var t = r.projType || inferType(r.prospect.pos);
        if (typeFilter !== 'all' && t !== typeFilter) return false;
```
with
```js
      var base      = typeFilter === 'U' ? ungradedRows : allRows;
      var filtered  = base.filter(function(r) {
        var t = r.ungraded ? 'U' : (r.projType || inferType(r.prospect.pos));
        if (typeFilter !== 'all' && t !== typeFilter) return false;
        if (lens === 'ready' && !(r.model && r.model.ready_rank)) return false;
```
Replace
```js
      document.getElementById('countLine').textContent =
        'Showing ' + filtered.length + ' of ' + allRows.length;
```
with
```js
      document.getElementById('countLine').textContent =
        'Showing ' + filtered.length + ' of ' + base.length;

      var note = '';
      if (typeFilter === 'U') {
        note = 'Model only, no scouting grade. In backtests about 1–2.5% of never-listed hitters became ' +
               'starter-quality; most ungraded hits had been on an earlier list.';
      } else if (lens === 'ready') {
        note = 'Ranked by the average of FanGraphs\' order and the model\'s 2-year odds, which beat FanGraphs ' +
               'alone in 3 of 3 test years. ' + modelInfo.counts.board_without_model +
               ' board hitters have no model read.';
      } else if (modelInfo) {
        note = 'Sorted by FanGraphs. Take shows where the model disagrees; ceiling disagreements are unproven.';
      }
      document.getElementById('modelNote').textContent = note;
```

- [ ] **Step 9: Row cells.** Replace

```js
        var fvSpan = document.createElement('span');
        fvSpan.className = 'badge-fv ' + fvClass(pr.fv);
        fvSpan.textContent = pr.fv;
        tr.appendChild(tdNode(fvSpan));
```
with
```js
        var fvSpan = document.createElement('span');
        if (row.ungraded) {
          fvSpan.className = 'badge-fv badge-fv-low';
          fvSpan.textContent = Math.round(row.model.rating_pct * 100);
          fvSpan.title = 'Model rating percentile among ' + modelInfo.season + ' model hitters';
        } else {
          fvSpan.className = 'badge-fv ' + fvClass(pr.fv);
          fvSpan.textContent = pr.fv;
        }
        tr.appendChild(tdNode(fvSpan));
```
Replace
```js
        gradesCell.appendChild(buildGradesCell(pr));
        tr.appendChild(gradesCell);
```
with
```js
        gradesCell.appendChild(buildGradesCell(pr));
        tr.appendChild(gradesCell);

        tr.appendChild(td(fmtOdds(row.model ? row.model.odds : null), row.model ? '' : 'dim'));
        tr.appendChild(td(row.take, 'take-cell' + (row.model ? '' : ' dim')));
```

- [ ] **Step 10: Header and type-button handlers.** Replace
```js
        document.querySelectorAll('th').forEach(function(h) { h.className = ''; });
        this.dataset.col && (this.className = sortDir === -1 ? 'sort-desc' : 'sort-asc');
        render();
```
with
```js
        markSortHeader();
        render();
```
(The old code wiped every header's classes, including `grades-cell`/`take-cell`.)

Replace
```js
        typeFilter = this.dataset.type;
        document.querySelectorAll('.type-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        render();
```
with
```js
        var t = this.dataset.type;
        if (lens === 'ready' && t !== 'H') {
          lens = 'best';
          document.getElementById('btnBest').classList.add('active');
          document.getElementById('btnReady').classList.remove('active');
        }
        setType(t);
        document.getElementById('lensToggle').style.display = (modelInfo && t !== 'U') ? '' : 'none';
        if (lens !== 'ready') { sortCol = 'fv'; sortDir = -1; }
        markSortHeader();
        render();
```

- [ ] **Step 11: Load the model file and attach it to rows.** Replace
```js
      allRows = prospectList.map(function(pr) {
        var rp  = rosterByName[pr.name] || null;
```
with
```js
      // Model read (sub-project 4). If the file is absent the page works as before.
      var modelByKey = {};
      try {
        var mresp = await fetch('./data/prospect_model.json?t=' + Date.now(), { cache: 'no-store' });
        if (mresp.ok) {
          var mj = await mresp.json();
          var unreadable = {};
          (mj.unreadable_keys || []).forEach(function(k) { unreadable[k] = true; });
          modelInfo = { season: mj.season, counts: mj.counts, unreadable: unreadable };
          (mj.graded || []).forEach(function(g) { modelByKey[g.key] = g; });
          ungradedRows = (mj.ungraded || []).map(function(u) {
            var nm = normalizeName(u.name);
            var urp = rosterByName[nm] || null;
            return {
              prospect: { name: nm, rawName: u.name, org: '', pos: '', level: u.level, eta: '', fv: 0, age: u.age },
              ungraded: true, model: u, take: u.take,
              salary: urp ? (urp.salary || 0) : 0, team: urp ? (urp.team || 'FA') : 'FA',
              value: 0, surplus: 0, dynastyValue: 0, dynastySurplus: 0, hasProj: false, projType: 'H',
            };
          });
        }
      } catch (e) {
        console.warn('[prospects] no model data:', e);
      }

      allRows = prospectList.map(function(pr) {
        var rp  = rosterByName[pr.name] || null;
        var isP = inferType(pr.pos) === 'P';
        var mdl = isP ? null : (modelByKey[pr.rawName + '|' + pr.org] || null);
```
Replace
```js
          hasProj:        !!pm,
          projType:       pm ? pm.type : null,
        };
```
with
```js
          hasProj:        !!pm,
          projType:       pm ? pm.type : null,
          model:          mdl,
          take:           boardTake(pr, mdl, isP),
        };
```
Replace
`      document.querySelector('th[data-col="fv"]').className = 'sort-desc';`
with
```js
      if (modelInfo) document.getElementById('lensToggle').style.display = '';
      else document.querySelector('.type-btn[data-type="U"]').style.display = 'none';
      markSortHeader();
```

- [ ] **Step 12: Verify in the preview browser**

Start the server with preview_start `{name: "test"}` (it serves the repo root on port 8000), then open `http://localhost:8000/prospects.html`. Check:
1. `read_console_messages` with `onlyErrors: true`: no errors.
2. **Default lens:** sorted by FV. The note line reads "Sorted by FanGraphs…". Hitters show an odds value and a take. A pitcher row's take reads "FanGraphs only (no pitcher model)".
3. **"Closest to helping":** only hitters. The first three names match `graded[0..2].key` in `data/prospect_model.json`; confirm with `javascript_tool`:
   ```js
   fetch('./data/prospect_model.json').then(r => r.json()).then(d => d.graded.slice(0, 3).map(g => g.key))
   ```
   The note shows the "no model read" count.
4. **Clicking "Pitchers"** returns to "Best prospects" and shows pitchers only.
5. **"Ungraded (model only)":** the FV header reads "Model", rows are sorted by it, the caveat note shows, the takes read "On the <year> list…" / "Never on a FanGraphs list", and the lens toggle is hidden.
6. **Clicking the "2-yr odds" header** sorts by odds. The Grades/Take header styling survives the click.
7. Take a screenshot of the "Closest to helping" lens as proof.

If anything fails, fix it in `prospects.html` and re-check. Don't change the Python outputs to make the page look right.

- [ ] **Step 13: Commit**

```bash
git add prospects.html
git commit -m "feat(prospects): Best prospects / Closest to helping lenses, 2-yr odds, Take line, Ungraded view"
```

---

### Task 5: Wrap-up

- [ ] **Step 1:** Run `python -m unittest discover -s tests` (in `prospects-model/`). Expected: `OK (skipped=3)`, 200 tests.
- [ ] **Step 2:** In memory `project_prospect_model.md`, record that sub-project 4 has shipped: the files, how refresh works (export board → replace `data/prospects.csv` → `python build_shopping_list.py` → commit both), and the counts from Task 3.
- [ ] **Step 3:** Tell the user:
  - it's done, with the screenshot;
  - to push via GitHub Desktop (the page goes live on Pages after the push);
  - that the board is the Aug 24 copy until they export a fresh one.
