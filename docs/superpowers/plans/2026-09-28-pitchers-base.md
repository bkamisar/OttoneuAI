# Pitchers Plan P-A: Base Model Backtests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Cleared to build (the user approved, 2026-09-28):** the recommended defaults in `docs/superpowers/specs/2026-09-28-pitchers-design.md`, with D2 set to a **30 IP** floor per level. The draft's 40 IP lost about 21% of reliever seasons to mid-season promotions.

**Goal:** As-of walk-forward backtests of a pitcher base model on box stats, the pitcher counterpart of 3c plan A. It covers the model choice, group adoption, interactions and calibration for both outputs. 2024 stays sealed.

**Architecture:**
- Generalize `asof.py` and `walkforward.py` with a `typ` that defaults to `"H"`, so hitter behavior is byte-identical and the full existing suite proves it.
- Add `psmodel/pcohorts.py` (pitcher rows).
- Add `model_p_base.py`, which mirrors `model3c_base.py`.

**Tech Stack:** Python 3, numpy, scikit-learn (installed); `unittest`.

---

## Ground rules

- **Where to run:** from `prospects-model/`. Tests: `python -m unittest discover -s tests`. Before this plan: **203 pass, 3 skipped**.
- **No network.** The pitching data is already cached (`pull_pitcher_data.py` ran 2026-09-28). If any step tries to fetch, stop: that means a cache miss, which is a bug to report.
- **`cache/` is never committed.**
- **Commits:** commit locally after each task. **Never push, fetch or pull.**
- **After the run, hand to Opus.** Don't interpret group adoption or change groups on a cheaper model.

---

### Task 1: `asof.py` learns pitchers

**Files:** Modify `prospects-model/psmodel/asof.py`; Test `prospects-model/tests/test_asof.py`.

- [ ] **Step 1: Failing tests.** Add above `if __name__ == "__main__":` in `tests/test_asof.py`:

```python
def p(season, value, ip=60.0, rank=None):
    d = {"season": season, "value": value, "pa": 0, "ip": ip}
    if rank is not None:
        d["rank"] = rank
    return d


class TestPitchers(unittest.TestCase):
    def test_attach_ranks_by_type(self):
        labels = {(1, "P"): [p(2020, 1.0)], (2, "P"): [p(2020, 3.0)], (1, "H"): [s(2020, 9.0)]}
        asof.attach_ranks(labels, "P")
        self.assertEqual([labels[(1, "P")][0]["rank"], labels[(2, "P")][0]["rank"]], [2, 1])
        self.assertNotIn("rank", labels[(1, "H")][0])

    def test_ref_curve_uses_only_the_type(self):
        labels = {(i, "P"): [p(2013, float(10 - i)), p(2014, float(20 - 2 * i))] for i in range(3)}
        labels[(9, "H")] = [s(2013, 99.0), s(2014, 99.0)]
        self.assertEqual(asof.ref_curve(labels, 2014, "P"), [15.0, 13.5, 12.0])

    def test_rating_eligibility_is_by_innings(self):
        mlb = [p(2019, 0, ip=20.0, rank=1), p(2020, 0, ip=30.0, rank=3)]
        self.assertEqual(asof.rating_target(mlb, 2018, CURVE, "P"), 3.0)   # the 20-IP season doesn't count
        self.assertEqual(asof.rating_target(mlb, 2018, CURVE), 0.0)        # as hitter seasons: 0 PA, none count

    def test_soon_and_useful_line_are_top_120_for_pitchers(self):
        self.assertTrue(asof.soon_target([p(2020, 0, rank=120)], 2018, "P"))
        self.assertFalse(asof.soon_target([p(2020, 0, rank=121)], 2018, "P"))
        self.assertTrue(asof.soon_target([p(2020, 0, rank=121)], 2018))     # hitters: top 144
        self.assertEqual(asof.useful_value(list(range(200, 0, -1)), "P"), 81)
```

- [ ] **Step 2:** Run `python -m unittest tests.test_asof -v`. Expected: the 4 new tests ERROR or FAIL (with a `TypeError` for the extra argument).

- [ ] **Step 3: Implement.** In `psmodel/asof.py`:

Replace `STARTERS = 144          # 12 teams x 12 lineup slots` with:
```python
STARTERS = 144          # 12 teams x 12 lineup slots
STARTERS_BY = {"H": STARTERS, "P": 120}   # pitchers: 12 teams x ~10 arms under the 1,500 IP cap
```

Replace the whole `attach_ranks` function with:
```python
def attach_ranks(labels, typ="H"):
    """Adds 'rank' (1 = best that year, by total SGP) to every season of one
    player type (hitters by default), in place."""
    by = {}
    for (pid, t), rows in labels.items():
        if t == typ:
            for r in rows:
                by.setdefault(r["season"], []).append(r)
    for recs in by.values():
        for i, r in enumerate(sorted(recs, key=lambda r: -r["value"]), 1):
            r["rank"] = i
    return labels
```

Replace the whole `ref_curve` function with:
```python
def ref_curve(labels, v, typ="H"):
    """Typical SGP of the season ranked r (index r-1) for one player type: the
    median across seasons FIRST_LABEL..v, 2020 excluded. Ranks are valued on this
    common scale."""
    by = {}
    for (pid, t), rows in labels.items():
        if t == typ:
            for r in rows:
                if FIRST_LABEL <= r["season"] <= v and r["season"] != 2020:
                    by.setdefault(r["season"], []).append(r["value"])
    n = min(len(x) for x in by.values())
    cols = [sorted(x, reverse=True)[:n] for x in by.values()]
    return [float(np.median(c)) for c in zip(*cols)]
```

Replace `useful_value`, `rating_target` and `soon_target` with:
```python
def useful_value(curve, typ="H"):
    """The typical value of the last starter-quality rank (144th hitter, 120th pitcher)."""
    return curve[STARTERS_BY[typ] - 1]


def _eligible(r, typ):
    if typ == "H":
        return (r.get("pa") or 0) >= targets.MIN_PA
    return (r.get("ip") or 0.0) >= targets.MIN_IP


def rating_target(mlb, cohort, curve, typ="H"):
    """Best season in cohort+1..cohort+4 with enough volume (100 PA / 25 IP), valued
    at the typical value of its rank, floored at 0."""
    vals = [curve[min(r["rank"], len(curve)) - 1] for r in mlb
            if cohort < r["season"] <= cohort + RATING_YEARS and _eligible(r, typ)]
    return max(0.0, max(vals)) if vals else 0.0


def soon_target(mlb, cohort, typ="H"):
    """A starter-quality season (top 144 hitters / top 120 pitchers that year) in
    cohort+1..cohort+2."""
    return any(r["rank"] <= STARTERS_BY[typ] for r in mlb if cohort < r["season"] <= cohort + SOON_YEARS)
```

- [ ] **Step 4:** Run `python -m unittest tests.test_asof -v` (all OK), then `python -m unittest discover -s tests`. Expected: **207 pass**, 3 skipped. Every pre-existing test must still pass: that's the proof hitters are unchanged.

- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/asof.py tests/test_asof.py
git commit -m "feat(pitchers): as-of targets take a player type -- top 120 / 25 IP for pitchers, hitters unchanged"
```

### Task 2: `walkforward.py` reads the row's type

**Files:** Modify `prospects-model/psmodel/walkforward.py`; Test `prospects-model/tests/test_walkforward.py`.

- [ ] **Step 1: Failing test.** Add above `if __name__ == "__main__":` in `tests/test_walkforward.py`:

```python
class TestPlayerType(unittest.TestCase):
    def test_targets_follow_the_row_type(self):
        mlb = [{"season": 2020, "value": 0.0, "pa": 0, "ip": 60.0, "rank": 130}]
        self.assertEqual(W._y({"mlb": mlb, "season": 2019, "typ": "P"}, "soon", None), 0.0)   # pitchers: top 120
        self.assertEqual(W._y({"mlb": mlb, "season": 2019}, "soon", None), 1.0)               # hitters: top 144
```

- [ ] **Step 2:** Run `python -m unittest tests.test_walkforward -v`. Expected: the new test FAILS (the pitcher row returns 1.0).

- [ ] **Step 3: Implement.** In `psmodel/walkforward.py`, replace the body of `_y`:
```python
def _y(r, target, ctx):
    """ctx is the as-of target context: the rank-value curve for the rating; unused for soon.
    Rows carry typ 'P' for pitchers; hitters rows have no typ (default 'H')."""
    typ = r.get("typ", "H")
    if target == "rating":
        return asof.rating_target(r["mlb"], r["season"], ctx, typ)
    return 1.0 if asof.soon_target(r["mlb"], r["season"], typ) else 0.0
```
and in `metrics`, replace
```python
        useful = r["y"] >= asof.useful_value(ctx) if target == "rating" else r["y"] == 1.0
```
with
```python
        useful = r["y"] >= asof.useful_value(ctx, r.get("typ", "H")) if target == "rating" else r["y"] == 1.0
```

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **208 pass**, 3 skipped.

- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/walkforward.py tests/test_walkforward.py
git commit -m "feat(pitchers): walk-forward targets and top-N lines follow the row's player type"
```

### Task 3: Pitcher rows (`psmodel/pcohorts.py`)

**Files:** Create `prospects-model/psmodel/pcohorts.py`; Test `prospects-model/tests/test_pcohorts.py`.

- [ ] **Step 1: Failing tests.** Create `tests/test_pcohorts.py`:

```python
import unittest

from psmodel import pcohorts


def milb_p(pid, season, sid, ip=60.0, g=20, gs=10, age=22):
    return {"player_id": pid, "name": f"P{pid}", "season": season, "sport_id": sid, "age": age,
            "g": g, "gs": gs, "ip": ip, "so": 60, "bb": 20, "hr": 5, "era": 3.5, "whip": 1.2,
            "hr9": 5 * 9.0 / ip, "np": int(ip * 16), "strikes": int(ip * 10), "bf": int(ip * 4.3),
            "swings": int(ip * 7), "whiffs": int(ip * 2)}


class TestPriorIp(unittest.TestCase):
    def test_counts_only_earlier_seasons(self):
        hist = {1: {2010: 60.0, 2011: 50.5, 2013: 20.0}}
        self.assertEqual(pcohorts.prior_mlb_ip(hist, 1, 2012), 110.5)
        self.assertEqual(pcohorts.prior_mlb_ip(hist, 2, 2012), 0)


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        milb = [milb_p(1, 2019, 12, gs=20), milb_p(2, 2019, 12, gs=0),   # starter vs reliever, same level-season
                milb_p(3, 2019, 12, ip=25.0),                             # under 30 IP: dropped
                milb_p(4, 2019, 11), milb_p(1, 2021, 12)]
        hist = {4: {2017: 120.0}}                                         # 100+ prior MLB IP: dropped
        mlb = {1: [{"season": 2022, "value": 1.0, "pa": 0, "ip": 80.0}]}
        rows = pcohorts.build_rows(milb, hist, mlb)
        self.by = {(r["player_id"], r["season"], r["sport_id"]): r for r in rows}

    def test_volume_floor_and_established_cut(self):
        self.assertEqual(sorted(self.by), [(1, 2019, 12), (1, 2021, 12), (2, 2019, 12)])

    def test_role_features_rank_starter_above_reliever(self):
        self.assertGreater(self.by[(1, 2019, 12)]["f"]["gs_share"], self.by[(2, 2019, 12)]["f"]["gs_share"])

    def test_rows_are_pitchers_with_labels_flags_and_every_grouped_feature(self):
        r = self.by[(1, 2021, 12)]
        self.assertEqual((r["typ"], r["mlb"][0]["season"], r["age_raw"]), ("P", 2022, 22))
        self.assertEqual((r["f"]["repeat_level"], r["f"]["multi_level"], r["f"]["is_aa"]), (1.0, 0.0, 1.0))
        self.assertEqual({k for g in pcohorts.GROUPS.values() for k in g}, set(r["f"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** Run `python -m unittest tests.test_pcohorts -v`. Expected: ERROR (`cannot import name 'pcohorts'`).

- [ ] **Step 3: Implement.** Create `psmodel/pcohorts.py`:

```python
"""Pitcher rows: every minor-league pitcher-season-level from 2012 with 30+ IP at
the level, for pitchers not yet established in MLB, with the features the pitcher
base model tests and the pitcher's MLB labels attached. Mirrors cohorts.py.
Targets are attached later, per vantage, by walkforward.py -- rows carry typ 'P'
so the as-of targets use the pitcher line (top 120, 25 IP).
"""
from . import cohorts, milb, statsapi
from . import features as F

# 30 IP at the level (~130 batters faced, close to hitters' 150 PA). Measured
# 2026-09-28 on coverage only: 40 IP per level dropped ~21% of reliever seasons,
# because promoted relievers split their innings across levels; 30 drops ~6%.
MIN_IP = 30.0
ESTABLISHED_IP = 100.0         # prior MLB IP that ends prospect status (dataset.ESTABLISHED_IP)

GROUPS = {
    "age_level": ["age", "is_aaa", "is_aa", "is_higha"],
    "strikeouts": ["k", "whiff", "swstr", "csw"],
    "control": ["bb"],
    "run_prevention": ["era", "whip", "hr9"],
    "role": ["gs_share", "ip_per_g", "ip"],
    "trajectory": ["repeat_level", "multi_level"],
}
BINARY = {"is_aaa", "is_aa", "is_higha", "repeat_level", "multi_level"}
_BOX = ("age", "ip", "k", "bb", "era", "whip", "hr9", "whiff", "swstr", "csw")


def mlb_ip_history(first=cohorts.PA_HISTORY_FIRST, last=cohorts.CURRENT_SEASON):
    """{player_id: {season: MLB IP}}. MLB season stats are one row per player-season."""
    out = {}
    for s in range(first, last + 1):
        for r in statsapi.season_stats(s, "pitching", statsapi.MLB):
            out.setdefault(r["player_id"], {})[s] = r["ip"]
    return out


def prior_mlb_ip(history, pid, season):
    return sum(ip for s, ip in history.get(pid, {}).items() if s < season)


def load_milb(seasons=cohorts.MILB_SEASONS, levels=cohorts.LEVELS):
    rows = []
    for s in seasons:
        for sid in levels:
            rows += milb.season_rows(s, sid, "pitching", advanced=True)
    return rows


def build_rows(milb_rows, ip_history, mlb_seasons):
    """Rows {player_id, name, season, sport_id, typ, age_raw, f, mlb} for pitchers
    with 30+ IP at a level who weren't established in MLB. Continuous features are
    z-scored within level-season, as for hitters."""
    seen = {}
    for r in milb_rows:
        seen.setdefault((r["player_id"], r["season"]), set()).add(r["sport_id"])
    rows = []
    for r in milb_rows:
        pid, s = r["player_id"], r["season"]
        if r["ip"] < MIN_IP or prior_mlb_ip(ip_history, pid, s) >= ESTABLISHED_IP:
            continue
        base = F.pitcher_features(r)
        f = {k: base[k] for k in _BOX}
        for sid, name in cohorts.LEVEL_FLAGS.items():
            f[name] = 1.0 if r["sport_id"] == sid else 0.0
        f["gs_share"] = r["gs"] / r["g"] if r.get("g") else None
        f["ip_per_g"] = r["ip"] / r["g"] if r.get("g") else None
        f["repeat_level"] = 1.0 if r["sport_id"] in seen.get((pid, cohorts.previous_season(s)), ()) else 0.0
        f["multi_level"] = 1.0 if len(seen[(pid, s)]) > 1 else 0.0
        rows.append({"player_id": pid, "name": r["name"], "season": s, "sport_id": r["sport_id"],
                     "typ": "P", "age_raw": r.get("age"), "f": f, "mlb": mlb_seasons.get(pid, [])})
    F.standardize_within(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
    return rows
```

- [ ] **Step 4:** Run `python -m unittest tests.test_pcohorts -v` (4 OK), then `python -m unittest discover -s tests`. Expected: **212 pass**, 3 skipped.

- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/pcohorts.py tests/test_pcohorts.py
git commit -m "feat(pitchers): pitcher rows -- 30+ IP at a level, <100 prior MLB IP, box features incl. role, typ P"
```

### Task 4: The runner, run it, hand to Opus

**Files:** Create `prospects-model/model_p_base.py`.

- [ ] **Step 1: Create the file**

```python
"""Pitchers plan P-A: as-of walk-forward backtests of the pitcher base model, for
both outputs -- rating (best pitcher season in the next 4, 25+ IP) and soon (a
top-120 pitcher season within 2). Model choice, group importance, interactions,
calibration. 2024 stays sealed for the final check.

Usage:  python model_p_base.py
Reads only cached data (pull_pitcher_data.py and build_labels.py first).
Writes cache/model_p_base_report.txt and cache/model_p_choice.json (gitignored).
"""
import json
import os
import statistics
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset, pcohorts
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model_p_base_report.txt")
CHOICE = os.path.join(CACHE, "model_p_choice.json")
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['d']:+.4f} (z {W.z_score(r['d'], r['se']):+.1f}) "
                     f"t50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f} "
                     f"t100 {r['base']['top100']:.2f}->{r['fam']['top100']:.2f}"
                     for v, r in res.items())


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels, "P")
    mlb = {pid: rows for (pid, typ), rows in labels.items() if typ == "P"}
    rows = pcohorts.build_rows(pcohorts.load_milb(), pcohorts.mlb_ip_history(), mlb)
    L = ["PITCHERS BASE MODEL -- as-of walk-forward backtests (2024 sealed)",
         f"rows: {len(rows)} pitcher-season-levels, {len({r['player_id'] for r in rows})} players",
         "per season: " + ", ".join(f"{s} {sum(1 for r in rows if r['season'] == s)}"
                                    for s in cohorts.MILB_SEASONS), ""]
    all_keys = [k for g in pcohorts.GROUPS.values() for k in g]
    choice = {}
    for target, vantages in (("rating", W.RATING_VANTAGES), ("soon", W.SOON_VANTAGES)):
        bars = {v: asof.ref_curve(labels, v, "P") for v in vantages}
        simple, complex_ = W.KINDS[target]
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; useful line (typical value of pitcher rank "
                 f"{asof.STARTERS_BY['P']}) as-of: "
                 + ", ".join(f"{v} {asof.useful_value(b, 'P'):.3f}" for v, b in bars.items()))
        kind, kres = W.choose_kind(rows, all_keys, target, bars, vantages)
        L.append(f"model: {kind}  (" + "; ".join(
            f"{v}: n/a" if r is None else f"{v}: {simple} {r[0]['rank']:.3f} vs {complex_} {r[1]['rank']:.3f}"
            for v, r in kres.items()) + ")")
        L.append(f"groups -- drop-and-refit; KEEP = rank gain >= {W.WIN_Z:g} SE at >=2 vantages, none <= "
                 f"{W.HARM_Z:g} SE, mean top-50 change >= -{W.TOP50_TOLERANCE:g}:")
        adopted = set()
        for gs, res in W.group_importance(rows, pcohorts.GROUPS, target, kind, bars, vantages).items():
            ok, wins, avail = W.adopt(res)
            L.append(f"  {' + '.join(gs):28} {'KEEP' if ok else 'drop':4} {wins}/{avail}  {fmt(res)}")
            if ok:
                adopted.update(gs)
        keys = [k for g in pcohorts.GROUPS if g in adopted for k in pcohorts.GROUPS[g]]
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
        tree_wins = sum(1 for r in kres.values() if r is not None and r[1]["rank"] > r[0]["rank"])
        L.append(f"patterns the TREE model leans on ({complex_} beat {simple} at {tree_wins}/{len(vantages)} "
                 f"vantages; leads to test as explicit terms, not findings; 'replicated' = top-10 at >=2):")
        for (a, b), vs in sorted(hits.items(), key=lambda t: (-len(t[1]), -statistics.fmean(h for _, h in t[1])))[:10]:
            L.append(f"  {a} x {b}: {len(vs)} vantage(s), strength {statistics.fmean(h for _, h in vs):.3f} "
                     f"-> {'replicated' if len(vs) >= 2 else 'one vantage'}")
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

- [ ] **Step 2:** Run `python -c "import model_p_base"` (no error). Commit:
```bash
git ls-files cache
git add model_p_base.py
git commit -m "feat(pitchers): base-model walk-forward runner (mirrors model3c_base)"
```

- [ ] **Step 3: Run.** Run `python model_p_base.py`. It takes several minutes.

  Sanity checks (report, don't patch):
  - **Rows:** about 1,400–1,900 pitcher-season-levels per season. At a 40 IP floor it was about 1,380; 30 IP adds mostly relievers.
  - **The useful line** (value of pitcher rank 120) is positive at every vantage.
  - **Soon AUC** is well above 0.5 at every vantage.
  - **Age/level** is kept for at least one output (it dominated for hitters). If it's dropped for both, report that as surprising.
  - **No network activity:** every input is cached.

- [ ] **Step 4:** Run `git status --short; git ls-files cache`. Expected: no `cache/` paths.

- [ ] **Step 5: Hand to Opus.** Opus reviews:
  - which groups were kept;
  - whether the role group behaves sensibly;
  - how the 3a result ("swing rates add nothing for pitchers") holds up here.

  Opus then records a "P-A result" section in the pitcher spec, and designs P-B (tracking parity) and P-C (stuff score).
