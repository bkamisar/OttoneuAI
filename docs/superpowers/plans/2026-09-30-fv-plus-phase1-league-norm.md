# FV+ Phase 1: League-Season Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Z-score minor-league stats within (level, season, league) instead of (level, season), rerun the whole prospect chain, and report old vs new. This is spec `docs/superpowers/specs/2026-09-30-fv-plus-design.md`, section "Phase 1".

**Architecture:**
- A new `features.standardize_within_league` replaces `standardize_within` in the two row builders, `cohorts.build_rows` (hitters) and `pcohorts.build_rows` (pitchers). The old function stays for `whiff_test.py`.
- Rows now carry `league`.
- The audit's independent re-derivation switches to league groups.
- A checkpointed runner reruns the chain. A compare script diffs a snapshot of the old outputs against the new ones.

**Tech Stack:** Python 3.14, stdlib, numpy, scipy (already used). Runs from `prospects-model/`.

**Executed inline on Opus (the user's choice, 2026-09-30).**

**Facts measured before writing this plan** (cached data, 2026-09-30):
- Every minor-league row has a league name (0 missing).
- There are 146 level-season-league groups for hitters and 146 for pitchers. The smallest has 110 players, so the 30-row fallback is a guard and never triggers today.
- StatsAPI returns one split per player per level, so there are no combined multi-team rows (`team == "multiple"` count is 0).

**Pre-registered consequences (from the spec; do not change after seeing results):**
- Vantage-level group adoption is re-made by the unchanged rules.
- The 2024 decisions stay frozen:
  - pitchers: `cache/model_p_2024_decisions.json`, already read by `model_p_final.py`;
  - hitters: contact+approach kept for "soon", and tracking-for-soon off. Task 4 enforces the contact+approach part.
- If a consensus verdict changes, the new verdict takes effect. The page's lenses depend on it, so **stop after Task 6 and bring any verdict change to the user** before touching `prospects.html`.

---

### Task 1: Snapshot the current outputs

**Files:**
- Create: `prospects-model/cache/phase1_before/` (gitignored with the rest of `cache/`)

- [ ] **Step 1: Copy the outputs the rerun will overwrite**

```bash
cd /c/Users/bkami/Documents/OttoneuAI/prospects-model
mkdir -p cache/phase1_before
cp cache/model3c_base_report.txt cache/model3c_choice.json cache/model3c_final.json \
   cache/model3c_final_report.txt cache/hitter_ratings.csv \
   cache/model_p_base_report.txt cache/model_p_choice.json cache/model_p_final.json \
   cache/model_p_final_report.txt cache/pitcher_ratings.csv cache/model_p_2024_decisions.json \
   cache/consensus_report.txt cache/consensus_verdict.json \
   cache/consensus_p_report.txt cache/consensus_p_verdict.json \
   cache/audit_report.txt ../data/prospect_model.json cache/phase1_before/
ls cache/phase1_before | wc -l
```

Expected: `17`

- [ ] **Step 2: Confirm `cache/` is gitignored** (nothing to commit)

Run: `git status --short prospects-model/cache | head -3`
Expected: no output.

---

### Task 2: `standardize_within_league`

**Files:**
- Modify: `prospects-model/psmodel/features.py` (docstring, lines 1-5; new function after `standardize_within`)
- Test: `prospects-model/tests/test_features.py`

- [ ] **Step 1: Write the failing tests.** Add `import statistics` at the top of `tests/test_features.py`, and this class before `if __name__ == "__main__":`

```python
class TestStandardizeLeague(unittest.TestCase):
    def rows(self):
        out = []
        for lg, ks in (("PCL", (.10, .20)), ("INT", (.30, .40))):
            out += [{"sport_id": 11, "season": 2023, "league": lg, "f": {"k": k, "is_aaa": 1.0}} for k in ks]
        return out

    def test_each_league_centred_on_its_own_mean(self):
        rows = F.standardize_within_league(self.rows(), ["k", "is_aaa"], min_rows=2)
        self.assertEqual([round(r["f"]["k"], 9) for r in rows], [-1.0, 1.0, -1.0, 1.0])
        self.assertEqual([r["f"]["is_aaa"] for r in rows], [1.0] * 4)

    def test_small_league_falls_back_to_level_season(self):
        rows = F.standardize_within_league(self.rows(), ["k"], min_rows=3)
        mu, sd = .25, statistics.pstdev([.1, .2, .3, .4])
        self.assertAlmostEqual(rows[0]["f"]["k"], (.10 - mu) / sd)

    def test_no_league_falls_back_and_missing_stays_missing(self):
        rows = self.rows() + [{"sport_id": 11, "season": 2023, "league": None, "f": {"k": .25}},
                              {"sport_id": 11, "season": 2023, "league": "PCL", "f": {"k": None}}]
        F.standardize_within_league(rows, ["k"], min_rows=2)
        self.assertAlmostEqual(rows[4]["f"]["k"], 0.0)
        self.assertIsNone(rows[5]["f"]["k"])
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python -m pytest tests/test_features.py -q`
Expected: 3 failures, `AttributeError: module 'psmodel.features' has no attribute 'standardize_within_league'`

- [ ] **Step 3: Implement.** Replace the module docstring (lines 1-5) with:

```python
"""Per-row features, z-scored within groups.

Within-level-season z-scores are what make a 2016 AA line comparable to a 2019
AAA line, and what absorb derived CSW's constant +1 pt offset. The 3c and pitcher
models go one step further and z-score within (level, season, league)
(standardize_within_league): the Pacific Coast League's offense is not the
International League's. Each group is a single season, so the 2021 league-level
changes don't matter. standardize_within stays for whiff_test.py.
"""
```

Then add after `standardize_within`:

```python
LEAGUE_MIN_ROWS = 30


def _group_stats(members, keys):
    out = {}
    for k in keys:
        vals = [m["f"][k] for m in members if m["f"].get(k) is not None]
        out[k] = (statistics.fmean(vals) if vals else 0.0,
                  statistics.pstdev(vals) if len(vals) > 1 else 0.0)
    return out


def standardize_within_league(rows, keys, min_rows=LEAGUE_MIN_ROWS):
    """z-score each feature within its (level, season, league) group, in place. A
    row with no league, or in a league-season under min_rows, uses its (level,
    season) group. All group stats are taken before any value is replaced."""
    keys = [k for k in keys if k not in NOT_STANDARDIZED]
    level, league = {}, {}
    for r in rows:
        level.setdefault((r["sport_id"], r["season"]), []).append(r)
        if r.get("league") is not None:
            league.setdefault((r["sport_id"], r["season"], r["league"]), []).append(r)
    stats = {g: _group_stats(m, keys) for g, m in level.items()}
    stats.update({g: _group_stats(m, keys) for g, m in league.items() if len(m) >= min_rows})
    for r in rows:
        st = stats.get((r["sport_id"], r["season"], r.get("league"))) or stats[(r["sport_id"], r["season"])]
        for k in keys:
            v = r["f"].get(k)
            mu, sd = st[k]
            r["f"][k] = None if v is None else ((v - mu) / sd if sd else 0.0)
    return rows
```

- [ ] **Step 4: Run and confirm they pass**

Run: `python -m pytest tests/test_features.py -q`
Expected: all pass (6 tests).

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/features.py prospects-model/tests/test_features.py
git commit -m "feat(fv-plus): standardize_within_league -- z-scores within level-season-league, level-season fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Hitter and pitcher rows use it

**Files:**
- Modify: `prospects-model/psmodel/cohorts.py:66-88`
- Modify: `prospects-model/psmodel/pcohorts.py:59-83`
- Create: `prospects-model/tests/test_league_rows.py`

- [ ] **Step 1: Write the failing test** in `tests/test_league_rows.py`:

```python
import unittest
from psmodel import cohorts, pcohorts


def hit(pid, league, so):
    return {"player_id": pid, "name": f"h{pid}", "season": 2023, "sport_id": 11, "league": league,
            "age": 24, "pa": 400, "ab": 350, "h": 90, "hr": 12, "bb": 40, "so": so, "sb": 5,
            "obp": .330, "slg": .420, "np": 1600, "swings": 700, "whiffs": 170}


def pit(pid, league, so):
    return {"player_id": pid, "name": f"p{pid}", "season": 2023, "sport_id": 11, "league": league,
            "age": 24, "g": 20, "gs": 20, "ip": 100.0, "so": so, "bb": 35, "bf": 430, "hr": 10,
            "hr9": .9, "era": 4.0, "whip": 1.3, "np": 1700, "strikes": 1080, "swings": 780, "whiffs": 190}


class TestLeagueRows(unittest.TestCase):
    """30 per league (the fallback threshold); INT strikes out far more than PCL."""

    def check(self, rows):
        for lg in ("PCL", "INT"):
            mine = [r for r in rows if r["league"] == lg]
            self.assertEqual(len(mine), 30)
            self.assertAlmostEqual(sum(r["f"]["k"] for r in mine), 0.0, places=9)

    def test_hitter_rows_normalized_within_league(self):
        raw = [hit(i, "PCL", 60 + i) for i in range(30)] + [hit(100 + i, "INT", 120 + i) for i in range(30)]
        self.check(cohorts.build_rows(raw, {}, {}))

    def test_pitcher_rows_normalized_within_league(self):
        raw = [pit(i, "PCL", 60 + i) for i in range(30)] + [pit(100 + i, "INT", 120 + i) for i in range(30)]
        self.check(pcohorts.build_rows(raw, {}, {}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m pytest tests/test_league_rows.py -q`
Expected: 2 failures, `KeyError: 'league'`.

- [ ] **Step 3: Implement.**

In `cohorts.build_rows`:
- In the docstring, change "Continuous features are z-scored within level-season, so age becomes age relative to the level." to "Continuous features are z-scored within level-season-league, so age becomes age relative to the league."
- Add `"league": r.get("league"),` to the appended dict, after `"sport_id": r["sport_id"],`.
- Replace the last call with:

```python
    F.standardize_within_league(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
```

In `pcohorts.build_rows`:
- In the docstring, change "z-scored within level-season, as for hitters." to "z-scored within level-season-league, as for hitters."
- Add `"league": r.get("league"),` to the appended dict, after `"sport_id": r["sport_id"],`.
- Replace the last call with:

```python
    F.standardize_within_league(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
```

- [ ] **Step 4: Run the new test and the full suite**

Run: `python -m pytest tests/test_league_rows.py -q` → 2 pass.
Run: `python -m pytest -q` → 255 passed, 3 skipped (250 before, plus 3 + 2 new). If an older test builds rows without `league`, it falls back to level-season and must still pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/cohorts.py prospects-model/psmodel/pcohorts.py prospects-model/tests/test_league_rows.py
git commit -m "feat(fv-plus): hitter and pitcher rows carry league and z-score within level-season-league

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Audit re-derivation and the hitter 2024 freeze

**Files:**
- Modify: `prospects-model/audit_pipeline.py:101-120`
- Modify: `prospects-model/model3c_final.py` (constant near line 34; after line 84)

- [ ] **Step 1: The audit re-derives within league.** Replace `audit_pipeline.py` lines 101-120 (from `groups = {}` through the `a.check("every feature = ...` call) with:

```python
    groups = {}
    for r, s in zip(rows, src):
        if s is not None:
            groups.setdefault((r["sport_id"], r["season"], r["league"]), []).append((r, s))
    small = [g for g, m in groups.items() if g[2] is None or len(m) < F.LEAGUE_MIN_ROWS]
    a.check(f"every row has a league and every league-season has >= {F.LEAGUE_MIN_ROWS} rows (no fallback in use)",
            not small, f"{len(small)} groups: {small[:5]}")
    worst, where = 0.0, ""
    for g, members in groups.items():
        raw_f = [F.hitter_features(s) for _, s in members]
        for k in continuous_keys():
            vals = [f[k] for f in raw_f if f[k] is not None]
            mu = statistics.fmean(vals) if vals else 0.0
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            for (r, _), f in zip(members, raw_f):
                want = None if f[k] is None else ((f[k] - mu) / sd if sd else 0.0)
                got = r["f"].get(k)
                diff = float("inf") if (want is None) != (got is None) else (
                    0.0 if want is None else abs(want - got))
                if diff > worst:
                    worst, where = diff, f"{k} in {g[0]} {g[1]} {g[2]} ({r['name']})"
    a.check("every feature = its raw stat z-scored within level-season-league (all rows re-derived)",
            worst < TOL, f"max diff {worst:.2e}" + (f" at {where}" if worst >= TOL else ""))
```

- [ ] **Step 2: Enforce the hitter 2024 freeze in `model3c_final.py`.** After `AAA_TRACKED = (...)` add:

```python
FROZEN_SOON_GROUPS = ("contact", "approach")   # kept at 2024's first opening (2026-09-27); never re-decided
```

After `keys = {t: list(choice[t]["keys"]) for t in ("rating", "soon")}` add:

```python
    for g in FROZEN_SOON_GROUPS:
        if g not in choice["soon"]["adopted"]:
            keys["soon"] += [k for k in cohorts.GROUPS[g] if k not in keys["soon"]]
            L.append(f"NOTE: the base run dropped '{g}' for soon; restored by the 2024 freeze")
```

- [ ] **Step 3: Run the suite** (nothing here has its own unit test; the audit runs in Task 6)

Run: `python -m pytest -q` → 255 passed, 3 skipped.

- [ ] **Step 4: Commit**

```bash
git add prospects-model/audit_pipeline.py prospects-model/model3c_final.py
git commit -m "feat(fv-plus): audit re-derives features within league; model3c_final enforces the 2024 contact+approach freeze

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Checkpointed chain runner and old-vs-new compare

**Files:**
- Create: `prospects-model/rerun_chain.py`
- Create: `prospects-model/phase1_compare.py`

- [ ] **Step 1: Write `rerun_chain.py`**

```python
"""FV+ Phase 1: rerun the whole prospect chain after the league-season fix.

Usage:  python rerun_chain.py [--force]
Runs each step as its own process, in order. Finished steps are recorded in
cache/rerun_chain_state.json, so a relaunch skips them (--force redoes all).
Stops at the first failing step. Every step's output goes to
cache/rerun_chain_log.txt.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cache", "rerun_chain_state.json")
LOG = os.path.join(HERE, "cache", "rerun_chain_log.txt")
STEPS = [
    ("hitter base", ["model3c_base.py"]),
    ("hitter final", ["model3c_final.py"]),
    ("pitcher base", ["model_p_base.py"]),
    ("pitcher final", ["model_p_final.py"]),
    ("hitter consensus", ["consensus_gate.py"]),
    ("pitcher consensus", ["consensus_gate.py", "--pitchers"]),
    ("shopping list", ["build_shopping_list.py"]),
    ("audit", ["audit_pipeline.py"]),
]


def load_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every step")
    state = {} if ap.parse_args().force else load_state()
    for name, cmd in STEPS:
        if state.get(name) == "done":
            print(f"skip  {name} (done)", flush=True)
            continue
        print(f"run   {name}: {' '.join(cmd)}", flush=True)
        t0 = time.time()
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(f"\n===== {name}: {' '.join(cmd)}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.flush()
            rc = subprocess.run([sys.executable, *cmd], cwd=HERE, stdout=log, stderr=subprocess.STDOUT).returncode
        if rc != 0:
            raise SystemExit(f"FAILED {name} (exit {rc}) after {time.time() - t0:.0f}s -- see {LOG}")
        state[name] = "done"
        save_state(state)
        print(f"done  {name} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `phase1_compare.py`**

```python
"""FV+ Phase 1: old vs new after the league-season fix.

Usage:  python phase1_compare.py
Reads cache/phase1_before/ (the snapshot) and the current cache outputs; writes
cache/phase1_compare.txt (gitignored) and prints it.
"""
import csv
import difflib
import json
import os

from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
BEFORE = os.path.join(CACHE, "phase1_before")
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(CACHE, "phase1_compare.txt")
VERDICT_FIELDS = ("verdict", "verdict_graded", "verdict_restored", "unstable", "show_model_for_ungraded")
REPORTS = ("model3c_base_report.txt", "model3c_final_report.txt", "model_p_base_report.txt",
           "model_p_final_report.txt", "consensus_report.txt", "consensus_p_report.txt")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ratings(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["player_id"]: r for r in csv.DictReader(fh)}


def text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def main():
    L = ["FV+ PHASE 1 -- old (level-season) vs new (level-season-league) normalization", ""]
    L.append("1. Adopted groups (vantage decisions, unchanged rules):")
    for name in ("model3c_choice.json", "model_p_choice.json"):
        old, new = load(os.path.join(BEFORE, name)), load(os.path.join(CACHE, name))
        for t in ("rating", "soon"):
            o, n = old[t], new[t]
            L.append(f"  {name:22} {t:6} {o['kind']} {o['adopted']} -> {n['kind']} {n['adopted']}"
                     + ("" if (o["kind"], o["adopted"]) == (n["kind"], n["adopted"]) else "   CHANGED"))
    L += ["", "2. Consensus verdicts:"]
    for name in ("consensus_verdict.json", "consensus_p_verdict.json"):
        old, new = load(os.path.join(BEFORE, name)), load(os.path.join(CACHE, name))
        for t in ("rating", "soon"):
            o, n = old[t], new[t]
            changed = any(o[f] != n[f] for f in VERDICT_FIELDS)
            L.append(f"  {name:24} {t:6} " + ", ".join(f"{f} {o[f]} -> {n[f]}" for f in VERDICT_FIELDS)
                     + ("   CHANGED" if changed else ""))
    L += ["", "3. Production ratings, old vs new:"]
    for name in ("hitter_ratings.csv", "pitcher_ratings.csv"):
        old, new = ratings(os.path.join(BEFORE, name)), ratings(os.path.join(CACHE, name))
        common = sorted(set(old) & set(new))
        for col in ("rating_percentile", "p_useful_within_2"):
            a = [float(old[p][col]) for p in common]
            b = [float(new[p][col]) for p in common]
            top_o = set(sorted(common, key=lambda p: -float(old[p][col]))[:50])
            top_n = set(sorted(common, key=lambda p: -float(new[p][col]))[:50])
            L.append(f"  {name:20} {col:18} Spearman {spearmanr(a, b).statistic:.3f} over {len(common)}; "
                     f"top-50 overlap {len(top_o & top_n)}/50")
        L.append(f"  {name:20} players only in old {len(set(old) - set(new))}, only in new {len(set(new) - set(old))}")
    old, new = load(os.path.join(BEFORE, "prospect_model.json")), load(os.path.join(DATA, "prospect_model.json"))
    L += ["", "4. Shopping list counts:",
          f"  hitters  {old['counts']} -> {new['counts']}",
          f"  pitchers {old['pitchers']['counts']} -> {new['pitchers']['counts']}", ""]
    for name in REPORTS:
        diff = list(difflib.unified_diff(text(os.path.join(BEFORE, name)), text(os.path.join(CACHE, name)),
                                         "old/" + name, "new/" + name, lineterm="", n=0))
        L += [f"=== diff {name} ({'no change' if not diff else f'{len(diff)} lines'})"] + diff + [""]
    out = "\n".join(L)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-test the compare script against the snapshot.** No chain has run yet, so old equals new.

Run: `python phase1_compare.py | head -20`
Expected: no `CHANGED` anywhere; Spearman 1.000 and top-50 overlap 50/50 for every column; every diff says `no change`.

- [ ] **Step 4: Commit**

```bash
git add prospects-model/rerun_chain.py prospects-model/phase1_compare.py
git commit -m "feat(fv-plus): checkpointed chain runner and Phase 1 old-vs-new compare

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Run the chain

- [ ] **Step 1: Make sure no stray python process is running** (the orphaned-fetch lesson)

Run: `tasklist | grep -i python`
Expected: nothing, or only processes you can account for.

- [ ] **Step 2: Run in the background** (it can take a long time; relaunching resumes)

Run (background): `python rerun_chain.py`
Expected: `done` for all 8 steps. On a failure, read the log's tail, fix the cause, and relaunch; finished steps are skipped.

- [ ] **Step 3: Check the audit**

Run: `grep -c FAIL cache/audit_report.txt; grep -n "league" cache/audit_report.txt`
Expected: `0` FAILs, and both league checks PASS.

- [ ] **Step 4: Compare**

Run: `python phase1_compare.py`

- [ ] **Step 5: Full test suite**

Run: `python -m pytest -q` → 255 passed, 3 skipped.

---

### Task 7: Review and record (Opus)

- [ ] **Step 1: Review `cache/phase1_compare.txt`:**
  - Did adopted groups change? Did rank accuracy move at each vantage?
  - Did either consensus verdict change?
  - How much did production ratings move (Spearman; top-50 overlap)?
  - Which players moved most? Are PCL hitters down and PCL pitchers up, as expected? Spot-check a few.
- [ ] **Step 2: If a consensus verdict changed, STOP.** Tell the user what changed and what it means for the page's lenses before editing `prospects.html`.
- [ ] **Step 3: Record.**
  - Add a "Phase 1 result" section to the spec, with the numbers.
  - Update the memory file `project_prospect_model.md`.
- [ ] **Step 4: Commit.** Commit the spec, plus `data/prospect_model.json` if it changed (it will, because the ratings moved).

```bash
git add docs/superpowers/specs/2026-09-30-fv-plus-design.md data/prospect_model.json
git commit -m "docs(fv-plus): Phase 1 result -- league-season normalization rerun

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5:** Next is the Phase 2 plan (FV+ tests), written on Opus.
