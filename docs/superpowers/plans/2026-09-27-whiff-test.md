# Whiff-Family Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether minor-league whiff rate / CSW predict MLB value in this league's 4×4 beyond K% and BB%, and report which traits carry weight.

**Architecture:** MiLB season rows (basic `season` + `seasonAdvanced` stats, AA + affiliated AAA, 2016–2019) become per-row features normalized within (level, season). Each row joins to that player's MLB peak value from `cache/labels.csv` via `targets.build_target`. Two ridge models — baseline vs baseline + whiff family — are compared with player-grouped cross-validation over 10 shuffles; the family is adopted only if it wins consistently. A standardized-coefficient ranking answers "which traits matter."

**Tech Stack:** Python 3.14 stdlib + already-installed numpy 2.4.3, scipy 1.17.1, scikit-learn 1.8.0. Tests: stdlib `unittest`. Nothing new installed.

Spec: `docs/superpowers/specs/2026-09-26-prospect-model-design.md` — see "Sub-project 2 — what the data actually offers" and the whiff/CSW validation notes.

---

## Context the implementer needs

- Run everything from `prospects-model/`. Tests: `python -m unittest discover -s tests -v` (currently 70 pass, 2 live-only skipped). Live tests: set `PROSPECTS_LIVE=1`.
- **Existing modules you'll use:** `psmodel.http` (cached, throttled fetch; `require_rows`), `psmodel.statsapi` (`season_stats`, `num`, `normalize_hitter`, `normalize_pitcher`, `BASE`, `PAGE`), `psmodel.targets.build_target(mlb_rows, current_season, snapshot_season)` → `{peak_value, completeness, labeled, ...}` (peak floored at 0; a no-show ≥5 seasons after the snapshot is a labeled 0).
- **`cache/labels.csv`** (from `build_labels.py`, gitignored): columns `player_id,name,season,type,pa,ip,value`. `type` is `H` or `P`. Pitchers who batted before 2022 also appear as `H` rows — always join a prospect to labels of HIS type.
- **Validated facts this plan relies on (don't re-litigate):**
  - `stats=seasonAdvanced` gives `totalSwings`, `swingAndMisses` per player-season at every MiLB level; MLB whiff rate from it vs Savant: r = 0.9997.
  - CSW = `(strikes − totalSwings + swingAndMisses) / numberOfPitches`, where `strikes` and `numberOfPitches` come from **basic** `season` pitching (not `seasonAdvanced`). Validated vs pitch-by-pitch: r = 0.994, constant +1 pt offset that within-group normalization removes.
  - Exclude the Mexican League (`league == "MEX"`); it was 32% of qualified 2019 "AAA" hitters.
  - Normalize within **(sport_id, season)**, never by league name (leagues changed levels in 2021).
- **Security posture (user requirement — re-run before any network run):** stdlib + already-installed packages only; only `statsapi.mlb.com` contacted; outputs under `cache/` (gitignored).
- Commits: local only, never push. End messages with `Co-Authored-By: <current model> <noreply@anthropic.com>`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `psmodel/statsapi.py` | Modify | Keep `numberOfPitches`, `strikes`, `battersFaced`; add `season_advanced()` |
| `psmodel/milb.py` | Create | MiLB rows: MEX excluded, team splits combined, swings/whiffs attached |
| `psmodel/features.py` | Create | Per-row features, feature lists, within-(level, season) z-scores |
| `psmodel/dataset.py` | Create | Label join, established-player filter, "useful" threshold, complete cases |
| `psmodel/evaluate.py` | Create | Player-grouped CV, metrics, adoption rule, trait ranking, phantom guard |
| `whiff_test.py` | Create | Driver; writes `cache/whiff_test_report.txt` |
| `tests/test_statsapi.py`, `test_milb.py`, `test_features.py`, `test_dataset.py`, `test_evaluate.py` | Modify/Create | Unit tests |

---

### Task 1: StatsAPI — pitch counts and `season_advanced`

**Files:** Modify `psmodel/statsapi.py`, `tests/test_statsapi.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_statsapi.py` before `if __name__`:

```python
class TestPitchCountFields(unittest.TestCase):
    def test_pitcher_keeps_pitches_strikes_and_batters_faced(self):
        split = {"player": {"id": 7, "fullName": "p"},
                 "stat": {"inningsPitched": "100.0", "numberOfPitches": 1600,
                          "strikes": 1020, "battersFaced": 420}}
        r = statsapi.normalize_pitcher(split, 2018, 12)
        self.assertEqual((r["np"], r["strikes"], r["bf"]), (1600, 1020, 420))

    def test_hitter_keeps_pitches_seen(self):
        split = {"player": {"id": 8, "fullName": "h"}, "stat": {"numberOfPitches": 2111}}
        self.assertEqual(statsapi.normalize_hitter(split, 2019, 12)["np"], 2111)


class TestSeasonAdvanced(unittest.TestCase):
    def setUp(self):
        self._orig = statsapi.http.fetch_json

    def tearDown(self):
        statsapi.http.fetch_json = self._orig

    def test_sums_team_splits_per_player(self):
        """A player traded within a level can appear as several splits."""
        payload = {"stats": [{"splits": [
            {"player": {"id": 1}, "stat": {"totalSwings": 500, "swingAndMisses": 120}},
            {"player": {"id": 1}, "stat": {"totalSwings": 300, "swingAndMisses": 60}},
            {"player": {"id": 2}, "stat": {"totalSwings": 900, "swingAndMisses": 200}}]}]}
        statsapi.http.fetch_json = lambda url: payload
        got = statsapi.season_advanced(2018, "hitting", 12)
        self.assertEqual(got[1], {"swings": 800, "whiffs": 180})
        self.assertEqual(got[2], {"swings": 900, "whiffs": 200})

    def test_empty_is_an_error(self):
        statsapi.http.fetch_json = lambda url: {"stats": [{"splits": []}]}
        with self.assertRaises(statsapi.http.DataError):
            statsapi.season_advanced(2018, "hitting", 12)


@unittest.skipUnless(os.environ.get("PROSPECTS_LIVE") == "1", "set PROSPECTS_LIVE=1 for network tests")
class TestSeasonAdvancedLive(unittest.TestCase):
    def test_aa_2019_is_populated_and_sane(self):
        got = statsapi.season_advanced(2019, "hitting", 12)
        self.assertGreater(len(got), 500)
        self.assertTrue(all(v["whiffs"] <= v["swings"] for v in got.values()))
```

- [ ] **Step 2: Run** `python -m unittest tests.test_statsapi -v` → expect `KeyError: 'np'` / `AttributeError: ... season_advanced`.

- [ ] **Step 3: Implement.** In `normalize_hitter`'s `row.update({...})`, add after `"sb": ...`:

```python
        "np": int(num(st.get("numberOfPitches"))),
```

In `normalize_pitcher`'s `row.update({...})`, add after `"bb": ...`:

```python
        "np": int(num(st.get("numberOfPitches"))),
        "strikes": int(num(st.get("strikes"))),
        "bf": int(num(st.get("battersFaced"))),
```

Append to the end of `psmodel/statsapi.py`:

```python
def season_advanced(season: int, group: str, sport_id: int):
    """{player_id: {"swings", "whiffs"}} from stats=seasonAdvanced, summed
    across team splits. Validated: MLB 2024 whiff rate from this endpoint vs
    Savant's whiff_percent, r = 0.9997 over 397 hitters."""
    out, offset = {}, 0
    while True:
        url = (f"{BASE}?stats=seasonAdvanced&season={season}&group={group}"
               f"&sportId={sport_id}&limit={PAGE}&offset={offset}&playerPool=all")
        stats = http.fetch_json(url).get("stats") or []
        splits = (stats[0].get("splits") if stats else None) or []
        if offset == 0:
            http.require_rows(splits, f"seasonAdvanced {season}/{group}/sport{sport_id}")
        for s in splits:
            pid = (s.get("player") or {}).get("id")
            if pid is None:
                continue
            st = s.get("stat") or {}
            cur = out.setdefault(pid, {"swings": 0, "whiffs": 0})
            cur["swings"] += int(num(st.get("totalSwings")))
            cur["whiffs"] += int(num(st.get("swingAndMisses")))
        if len(splits) < PAGE:
            break
        offset += PAGE
    return out
```

- [ ] **Step 4: Run** full suite → all pass. Then `PROSPECTS_LIVE=1 python -m unittest tests.test_statsapi -v` → live tests pass.
- [ ] **Step 5: Parity** — `python parity/compare.py` → `PASS` (labels must be unaffected).
- [ ] **Step 6: Commit** `feat(prospects-model): keep pitch counts; add seasonAdvanced swings/whiffs`.

---

### Task 2: MiLB rows

**Files:** Create `psmodel/milb.py`, `tests/test_milb.py`

- [ ] **Step 1: Failing tests** — `tests/test_milb.py`:

```python
import unittest
from psmodel import milb


def hit(pid, pa, ab, obp, slg, league="INT", **kw):
    r = {"player_id": pid, "name": f"p{pid}", "season": 2018, "sport_id": 11, "team": "T",
         "league": league, "age": 23, "g": 50, "pa": pa, "ab": ab, "h": 50, "hr": 5, "r": 20,
         "bb": 20, "so": 40, "sb": 3, "np": pa * 4, "hbp": 2, "obp": obp, "slg": slg}
    r.update(kw)
    return r


class TestCombine(unittest.TestCase):
    def test_team_splits_become_one_row(self):
        rows = milb.combine_by_player([hit(1, 200, 180, .300, .400), hit(1, 100, 90, .360, .500)], "hitting")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["pa"], 300)
        self.assertAlmostEqual(r["obp"], (.300 * 200 + .360 * 100) / 300, places=9)
        self.assertAlmostEqual(r["slg"], (.400 * 180 + .500 * 90) / 270, places=9)
        self.assertEqual(r["team"], "multiple")

    def test_single_split_unchanged(self):
        r = hit(2, 400, 360, .320, .450)
        self.assertEqual(milb.combine_by_player([r], "hitting")[0]["obp"], .320)

    def test_pitcher_rates_weighted_by_innings(self):
        a = {"player_id": 3, "name": "x", "team": "A", "g": 10, "gs": 10, "ip": 60.0, "so": 60, "bb": 20,
             "hr": 6, "np": 1000, "strikes": 640, "bf": 250, "era": 3.00, "whip": 1.10, "hr9": 0.9}
        b = dict(a, ip=30.0, so=30, bb=12, hr=6, np=500, strikes=310, bf=130, era=6.00, whip=1.50)
        r = milb.combine_by_player([a, b], "pitching")[0]
        self.assertAlmostEqual(r["ip"], 90.0)
        self.assertAlmostEqual(r["era"], (3.00 * 60 + 6.00 * 30) / 90, places=9)
        self.assertAlmostEqual(r["hr9"], 12 * 9 / 90, places=9)
        self.assertEqual(r["strikes"], 950)


class TestSeasonRows(unittest.TestCase):
    def setUp(self):
        self._s, self._a = milb.statsapi.season_stats, milb.statsapi.season_advanced

    def tearDown(self):
        milb.statsapi.season_stats, milb.statsapi.season_advanced = self._s, self._a

    def test_excludes_mexican_league_and_attaches_swings(self):
        milb.statsapi.season_stats = lambda s, g, sp: [hit(1, 300, 270, .3, .4),
                                                       hit(2, 300, 270, .3, .4, league="MEX")]
        milb.statsapi.season_advanced = lambda s, g, sp: {1: {"swings": 600, "whiffs": 150},
                                                          2: {"swings": 1, "whiffs": 1}}
        rows = milb.season_rows(2018, 11, "hitting")
        self.assertEqual([r["player_id"] for r in rows], [1])
        self.assertEqual((rows[0]["swings"], rows[0]["whiffs"]), (600, 150))

    def test_missing_advanced_is_zero_not_crash(self):
        milb.statsapi.season_stats = lambda s, g, sp: [hit(1, 300, 270, .3, .4)]
        milb.statsapi.season_advanced = lambda s, g, sp: {}
        self.assertEqual(milb.season_rows(2018, 11, "hitting")[0]["swings"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError: psmodel.milb`.
- [ ] **Step 3: Implement** `psmodel/milb.py`:

```python
"""Minor-league season rows: basic stats plus seasonAdvanced swing data, one row
per player x season x level.

The Mexican League (classified AAA until 2021) is excluded. A player who changed
teams within one level can appear as several StatsAPI splits; those are combined
so each player has at most one row per (season, level).
"""
from . import statsapi

MEX_LEAGUES = {"MEX", "Mexican League"}
_HIT_SUM = ("g", "pa", "ab", "h", "hr", "r", "bb", "so", "sb", "np", "hbp")
_PIT_SUM = ("g", "gs", "ip", "so", "bb", "hr", "np", "strikes", "bf")


def _combine(rows, group):
    out = dict(rows[0])
    if len(rows) == 1:
        return out
    for k in (_HIT_SUM if group == "hitting" else _PIT_SUM):
        out[k] = sum(r.get(k) or 0 for r in rows)
    if group == "hitting":
        pa, ab = out["pa"] or 1, out["ab"] or 1
        out["obp"] = sum(r["obp"] * r["pa"] for r in rows) / pa
        out["slg"] = sum(r["slg"] * r["ab"] for r in rows) / ab
    else:
        ip = out["ip"] or 1
        out["era"] = sum(r["era"] * r["ip"] for r in rows) / ip
        out["whip"] = sum(r["whip"] * r["ip"] for r in rows) / ip
        out["hr9"] = out["hr"] * 9.0 / out["ip"] if out["ip"] else 0.0
    out["team"] = "multiple"
    return out


def combine_by_player(rows, group):
    by = {}
    for r in rows:
        by.setdefault(r["player_id"], []).append(r)
    return [_combine(v, group) for v in by.values()]


def season_rows(season, sport_id, group):
    basic = [r for r in statsapi.season_stats(season, group, sport_id)
             if r.get("league") not in MEX_LEAGUES]
    rows = combine_by_player(basic, group)
    adv = statsapi.season_advanced(season, group, sport_id)
    for r in rows:
        a = adv.get(r["player_id"], {})
        r["swings"] = a.get("swings", 0)
        r["whiffs"] = a.get("whiffs", 0)
    return rows
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): MiLB season rows with MEX excluded and splits combined`.

---

### Task 3: Features

**Files:** Create `psmodel/features.py`, `tests/test_features.py`

- [ ] **Step 1: Failing tests** — `tests/test_features.py`:

```python
import unittest
from psmodel import features as F


def hrow(**kw):
    r = {"sport_id": 11, "age": 23, "pa": 400, "ab": 350, "h": 100, "hr": 16, "bb": 40,
         "so": 90, "sb": 8, "obp": .340, "slg": .460, "np": 1600, "swings": 720, "whiffs": 180}
    r.update(kw)
    return r


class TestHitter(unittest.TestCase):
    def test_rates(self):
        f = F.hitter_features(hrow())
        self.assertAlmostEqual(f["k"], 90 / 400)
        self.assertAlmostEqual(f["bb"], 40 / 400)
        self.assertAlmostEqual(f["iso"], .460 - 100 / 350)
        self.assertAlmostEqual(f["whiff"], 180 / 720)
        self.assertAlmostEqual(f["swing"], 720 / 1600)
        self.assertAlmostEqual(f["swstr"], 180 / 1600)
        self.assertEqual(f["is_aaa"], 1.0)

    def test_zero_denominators_are_missing_not_zero(self):
        f = F.hitter_features(hrow(swings=0, whiffs=0, np=0))
        self.assertIsNone(f["whiff"]); self.assertIsNone(f["swing"]); self.assertIsNone(f["swstr"])

    def test_aa_flag(self):
        self.assertEqual(F.hitter_features(hrow(sport_id=12))["is_aaa"], 0.0)


class TestPitcher(unittest.TestCase):
    def test_csw_uses_strikes_minus_swings(self):
        """Every swing is a strike, so called = strikes - swings (validated r=0.994)."""
        r = {"sport_id": 12, "age": 22, "ip": 100.0, "so": 110, "bb": 35, "bf": 420, "hr9": .9,
             "era": 3.5, "whip": 1.2, "np": 1000, "strikes": 600, "swings": 450, "whiffs": 120}
        f = F.pitcher_features(r)
        self.assertAlmostEqual(f["csw"], (600 - 450 + 120) / 1000)
        self.assertAlmostEqual(f["k"], 110 / 420)
        self.assertAlmostEqual(f["kbb"], (110 - 35) / 420)
        self.assertAlmostEqual(f["whiff"], 120 / 450)


class TestStandardize(unittest.TestCase):
    def test_within_level_season_mean_zero_and_flags_untouched(self):
        rows = [{"sport_id": s, "season": 2018, "f": {"k": v, "is_aaa": 1.0 if s == 11 else 0.0}}
                for s, v in ((11, .20), (11, .30), (12, .10), (12, .40))]
        F.standardize_within(rows, ["k", "is_aaa"])
        for s in (11, 12):
            ks = [r["f"]["k"] for r in rows if r["sport_id"] == s]
            self.assertAlmostEqual(sum(ks), 0.0, places=9)
        self.assertEqual([r["f"]["is_aaa"] for r in rows], [1.0, 1.0, 0.0, 0.0])

    def test_missing_stays_missing(self):
        rows = [{"sport_id": 11, "season": 2018, "f": {"k": v}} for v in (.2, .3, None)]
        F.standardize_within(rows, ["k"])
        self.assertIsNone(rows[2]["f"]["k"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/features.py`:

```python
"""Per-row features for the whiff test, normalized within (level, season).

Within-(sport_id, season) z-scores are what make a 2016 AA line comparable to a
2019 AAA line, and what absorb derived CSW's constant +1 pt offset. Never
normalize by league name: leagues changed levels in 2021.
"""
import statistics

HIT_MIN_PA = 150
PIT_MIN_IP = 40.0

BASE_H = ["age", "pa", "k", "bb", "iso", "hr_pa", "obp", "slg", "sb_pa", "is_aaa"]
FAMILY_H = ["whiff", "swing", "swstr"]
BASE_P = ["age", "ip", "k", "bb", "kbb", "hr9", "era", "whip", "is_aaa"]
FAMILY_P = ["whiff", "swstr", "csw"]
NOT_STANDARDIZED = {"is_aaa"}


def _ratio(a, b):
    return (a / b) if b else None


def hitter_features(r):
    avg = _ratio(r["h"], r["ab"])
    return {
        "age": r.get("age"), "pa": r["pa"],
        "k": _ratio(r["so"], r["pa"]), "bb": _ratio(r["bb"], r["pa"]),
        "iso": (r["slg"] - avg) if avg is not None else None,
        "hr_pa": _ratio(r["hr"], r["pa"]), "obp": r["obp"], "slg": r["slg"],
        "sb_pa": _ratio(r["sb"], r["pa"]),
        "whiff": _ratio(r.get("whiffs", 0), r.get("swings", 0)),
        "swing": _ratio(r.get("swings", 0), r.get("np", 0)),
        "swstr": _ratio(r.get("whiffs", 0), r.get("np", 0)),
        "is_aaa": 1.0 if r["sport_id"] == 11 else 0.0,
    }


def pitcher_features(r):
    k = _ratio(r["so"], r.get("bf", 0))
    bb = _ratio(r["bb"], r.get("bf", 0))
    np_ = r.get("np", 0)
    # Every swing is a strike, so called = strikes - swings. Validated vs
    # pitch-by-pitch at r = 0.994 with a constant +1 pt offset (bunts).
    called = (r.get("strikes", 0) - r.get("swings", 0)) if np_ else None
    return {
        "age": r.get("age"), "ip": r["ip"], "k": k, "bb": bb,
        "kbb": (k - bb) if (k is not None and bb is not None) else None,
        "hr9": r["hr9"], "era": r["era"], "whip": r["whip"],
        "whiff": _ratio(r.get("whiffs", 0), r.get("swings", 0)),
        "swstr": _ratio(r.get("whiffs", 0), np_),
        "csw": _ratio(called + r.get("whiffs", 0), np_) if called is not None else None,
        "is_aaa": 1.0 if r["sport_id"] == 11 else 0.0,
    }


def standardize_within(rows, keys, group=("sport_id", "season")):
    """z-score each feature within its (level, season) group, in place."""
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[g] for g in group), []).append(r)
    for members in groups.values():
        for k in keys:
            if k in NOT_STANDARDIZED:
                continue
            vals = [m["f"][k] for m in members if m["f"].get(k) is not None]
            mu = statistics.fmean(vals) if vals else 0.0
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            for m in members:
                v = m["f"].get(k)
                m["f"][k] = None if v is None else ((v - mu) / sd if sd else 0.0)
    return rows
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): whiff-test features normalized within level-season`.

---

### Task 4: Dataset

**Files:** Create `psmodel/dataset.py`, `tests/test_dataset.py`

- [ ] **Step 1: Failing tests** — `tests/test_dataset.py`:

```python
import unittest
from psmodel import dataset


def milb_hitter(pid, season=2017, pa=400, **kw):
    r = {"player_id": pid, "name": f"p{pid}", "season": season, "sport_id": 12, "age": 22,
         "pa": pa, "ab": 360, "h": 100, "hr": 12, "bb": 35, "so": 80, "sb": 5,
         "obp": .340, "slg": .450, "np": 1600, "swings": 700, "whiffs": 170}
    r.update(kw)
    return r


def lab(season, value, pa=500, ip=0.0):
    return {"season": season, "value": value, "pa": pa, "ip": ip}


class TestBuild(unittest.TestCase):
    def test_target_is_mlb_peak(self):
        labels = {(1, "H"): [lab(2019, 1.0), lab(2020, 3.0), lab(2021, 2.0)]}
        rows = dataset.build([milb_hitter(1)], "H", labels, threshold=2.5)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["target"], 3.0)
        self.assertTrue(rows[0]["useful"])

    def test_never_arrived_is_a_labeled_zero(self):
        rows = dataset.build([milb_hitter(2)], "H", {}, threshold=1.0)
        self.assertEqual(rows[0]["target"], 0.0)
        self.assertFalse(rows[0]["useful"])

    def test_established_major_leaguer_is_not_a_prospect(self):
        """A rehab stint by an MLB regular must not teach 'AAA -> star'."""
        labels = {(3, "H"): [lab(2014, 4.0, pa=350), lab(2018, 5.0)]}
        self.assertEqual(dataset.build([milb_hitter(3, season=2017)], "H", labels, 1.0), [])
        labels = {(4, "H"): [lab(2016, 0.5, pa=200), lab(2018, 2.0)]}
        self.assertEqual(len(dataset.build([milb_hitter(4, season=2017)], "H", labels, 1.0)), 1)

    def test_pitcher_uses_pitcher_labels_only(self):
        """Pitchers batted before 2022 and have H rows; they must be ignored."""
        r = {"player_id": 5, "name": "p", "season": 2017, "sport_id": 12, "age": 23, "ip": 120.0,
             "so": 120, "bb": 40, "bf": 500, "hr9": .8, "era": 3.2, "whip": 1.15,
             "np": 1900, "strikes": 1200, "swings": 850, "whiffs": 210}
        labels = {(5, "H"): [lab(2019, 9.9, pa=20)], (5, "P"): [lab(2019, 1.5, pa=0, ip=150.0)]}
        rows = dataset.build([r], "P", labels, threshold=1.0)
        self.assertAlmostEqual(rows[0]["target"], 1.5)

    def test_volume_floor(self):
        self.assertEqual(dataset.build([milb_hitter(6, pa=120)], "H", {}, 1.0), [])


class TestThreshold(unittest.TestCase):
    def test_median_of_nth_best_across_full_seasons(self):
        labels = {}
        for season, vals in ((2016, [5, 3, 1]), (2017, [6, 4, 2]), (2020, [9, 9, 9]), (2018, [7, 5, 3])):
            for i, v in enumerate(vals):
                labels.setdefault((season * 10 + i, "H"), []).append(lab(season, v))
        old = dataset.USEFUL_N["H"]
        try:
            dataset.USEFUL_N["H"] = 2          # 2nd-best: 3, 4, 5 -> median 4 (2020 excluded)
            self.assertEqual(dataset.useful_threshold(labels, "H"), 4)
        finally:
            dataset.USEFUL_N["H"] = old


class TestCompleteCases(unittest.TestCase):
    def test_drops_rows_missing_any_feature(self):
        rows = [{"f": {"a": 1, "b": 2}}, {"f": {"a": 1, "b": None}}]
        self.assertEqual(len(dataset.complete_cases(rows, ["a", "b"])), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/dataset.py`:

```python
"""Joins minor-league feature rows to MLB outcomes for the whiff test."""
import csv
import statistics

from . import features as F
from . import targets

CURRENT_SEASON = 2026
ESTABLISHED_PA = 300    # MLB volume before the row's season that makes him not a prospect
ESTABLISHED_IP = 100
# "Good enough to start for one of 12 teams": 12 teams x 12 lineup slots for
# hitters; 12 x ~10 arms under the 1,500 IP cap for pitchers.
USEFUL_N = {"H": 144, "P": 120}


def load_labels(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault((int(r["player_id"]), r["type"]), []).append({
                "season": int(r["season"]), "value": float(r["value"]),
                "pa": int(float(r["pa"])), "ip": float(r["ip"])})
    return out


def useful_threshold(labels, typ, first=2015, last=2025):
    """Median over full seasons of the Nth-best season value by type."""
    by_season = {}
    for (_pid, t), rows in labels.items():
        if t != typ:
            continue
        for r in rows:
            if first <= r["season"] <= last and r["season"] != 2020:
                by_season.setdefault(r["season"], []).append(r["value"])
    n = USEFUL_N[typ]
    cuts = [sorted(v, reverse=True)[n - 1] for v in by_season.values() if len(v) >= n]
    if not cuts:
        raise ValueError(f"no season has {n} {typ} labels")
    return statistics.median(cuts)


def _prior_volume(mlb_rows, season, typ):
    return sum((r["pa"] if typ == "H" else r["ip"]) for r in mlb_rows if r["season"] < season)


def build(milb_rows, typ, labels, threshold):
    """Dataset rows {player_id, name, season, sport_id, f, target, weight, useful}.
    Applies the volume floor and drops established major leaguers (rehab stints)."""
    feat = F.hitter_features if typ == "H" else F.pitcher_features
    limit = ESTABLISHED_PA if typ == "H" else ESTABLISHED_IP
    out = []
    for r in milb_rows:
        if typ == "H" and r["pa"] < F.HIT_MIN_PA:
            continue
        if typ == "P" and r["ip"] < F.PIT_MIN_IP:
            continue
        mlb = labels.get((r["player_id"], typ), [])
        if _prior_volume(mlb, r["season"], typ) >= limit:
            continue
        t = targets.build_target(mlb, CURRENT_SEASON, snapshot_season=r["season"])
        if not t["labeled"]:
            continue
        out.append({"player_id": r["player_id"], "name": r["name"], "season": r["season"],
                    "sport_id": r["sport_id"], "f": feat(r), "target": t["peak_value"],
                    "weight": t["completeness"], "useful": t["peak_value"] >= threshold})
    return out


def complete_cases(rows, keys):
    """Both models must see IDENTICAL rows, or a 'win' could just be a different
    sample. Drop any row missing any feature in the union."""
    return [r for r in rows if all(r["f"].get(k) is not None for k in keys)]
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): whiff-test dataset with rehab filter and league-grounded 'useful'`.

---

### Task 5: Evaluation harness

**Files:** Create `psmodel/evaluate.py`, `tests/test_evaluate.py`

- [ ] **Step 1: Failing tests** — `tests/test_evaluate.py`:

```python
import unittest
import numpy as np
from psmodel import evaluate


def synth(n_players, family_matters, seed=7):
    """One row per player. Base feature b always predicts; family feature q
    predicts only when family_matters."""
    rng = np.random.default_rng(seed)
    b, q, e = rng.normal(size=n_players), rng.normal(size=n_players), rng.normal(size=n_players)
    y = 0.6 * b + (1.2 * q if family_matters else 0.0) + 0.8 * e
    cut = np.quantile(y, 0.8)
    return [{"player_id": i, "f": {"b": float(b[i]), "q": float(q[i])}, "target": float(y[i]),
             "weight": 1.0, "useful": bool(y[i] >= cut)} for i in range(n_players)]


class TestFolds(unittest.TestCase):
    def test_a_player_never_spans_folds(self):
        rows = [{"player_id": p} for p in (1, 1, 2, 3, 3, 3, 4)]
        folds = evaluate.assign_folds(rows, k=2, seed=0)
        by = {}
        for r, f in zip(rows, folds):
            by.setdefault(r["player_id"], set()).add(f)
        self.assertTrue(all(len(s) == 1 for s in by.values()))


class TestTopN(unittest.TestCase):
    def test_counts_players_not_rows(self):
        rows = [{"player_id": 1, "useful": True}, {"player_id": 1, "useful": True},
                {"player_id": 2, "useful": False}]
        self.assertAlmostEqual(evaluate.top_n_precision(rows, [0.9, 0.8, 0.7], n=2), 0.5)


class TestGuard(unittest.TestCase):
    def test_constant_feature_is_a_phantom(self):
        rows = [{"f": {"a": 1.0, "c": 5.0}}, {"f": {"a": 2.0, "c": 5.0}}]
        with self.assertRaises(ValueError):
            evaluate.guard_features(rows, ["a", "c"])

    def test_missing_value_raises(self):
        with self.assertRaises(ValueError):
            evaluate.guard_features([{"f": {"a": 1.0}}, {"f": {"a": None}}], ["a"])


class TestHarnessIsHonest(unittest.TestCase):
    """The harness itself is tested the way the parity gate was: it must adopt
    a feature that truly predicts and refuse one that is pure noise."""

    def test_adopts_a_real_signal(self):
        res = evaluate.compare(synth(1000, True), ["b"], ["q"], seeds=10, top_n=50)
        ok, wins = evaluate.adopt(res)
        self.assertTrue(ok, f"only {wins}/10 wins for a genuinely predictive feature")

    def test_rejects_pure_noise(self):
        res = evaluate.compare(synth(1000, False), ["b"], ["q"], seeds=10, top_n=50)
        ok, wins = evaluate.adopt(res)
        self.assertFalse(ok, f"adopted pure noise ({wins}/10 wins)")

    def test_trait_ranking_orders_by_weight(self):
        ranked = evaluate.trait_ranking(synth(1000, True), ["b", "q"])
        self.assertEqual(ranked[0][0], "q")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/evaluate.py`:

```python
"""Does a feature family add signal? Player-grouped cross-validation."""
import random

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ALPHAS = np.logspace(-2, 3, 20)


def assign_folds(rows, k, seed):
    """Every row of a player lands in the SAME fold. A prospect's 2017 AA and
    2018 AAA rows carry the same outcome; splitting them would leak it."""
    players = sorted({r["player_id"] for r in rows})
    random.Random(seed).shuffle(players)
    fold = {p: i % k for i, p in enumerate(players)}
    return [fold[r["player_id"]] for r in rows]


def guard_features(rows, keys):
    """NFLU's phantom-feature lesson: a declared feature that is missing or
    constant silently contributes nothing. Fail loudly instead."""
    for k in keys:
        vals = [r["f"].get(k) for r in rows]
        if any(v is None for v in vals):
            raise ValueError(f"feature {k!r} has missing values in the fit matrix")
        if len(set(vals)) < 2:
            raise ValueError(f"feature {k!r} is constant -- phantom feature")


def _model():
    return make_pipeline(StandardScaler(), RidgeCV(alphas=ALPHAS))


def _xyw(rows, keys):
    X = np.array([[r["f"][k] for k in keys] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows], dtype=float)
    w = np.array([r["weight"] for r in rows], dtype=float)
    return X, y, w


def oof_predictions(rows, keys, k=5, seed=0):
    guard_features(rows, keys)
    X, y, w = _xyw(rows, keys)
    folds = np.array(assign_folds(rows, k, seed))
    pred = np.zeros(len(rows))
    for f in range(k):
        tr, te = folds != f, folds == f
        m = _model()
        m.fit(X[tr], y[tr], ridgecv__sample_weight=w[tr])
        pred[te] = m.predict(X[te])
    return pred


def top_n_precision(rows, pred, n):
    """Share of the n players the model likes most who became useful. Counts
    PLAYERS: a prospect with an AA and an AAA row must not fill two slots."""
    best = {}
    for r, p in zip(rows, pred):
        pid = r["player_id"]
        if pid not in best or p > best[pid][0]:
            best[pid] = (p, r["useful"])
    top = sorted(best.values(), key=lambda t: -t[0])[:n]
    return sum(1 for _, u in top if u) / len(top)


def compare(rows, base, family, seeds=10, k=5, top_n=50):
    y = [r["target"] for r in rows]
    out = []
    for s in range(seeds):
        pb = oof_predictions(rows, base, k, s)
        pf = oof_predictions(rows, base + family, k, s)
        out.append({"seed": s,
                    "rho_base": float(spearmanr(pb, y).statistic),
                    "rho_fam": float(spearmanr(pf, y).statistic),
                    "top_base": top_n_precision(rows, pb, top_n),
                    "top_fam": top_n_precision(rows, pf, top_n)})
    return out


def adopt(results, min_wins=8):
    """Adopted only if the family improves rank accuracy WITHOUT lowering the
    top-N hit rate, in at least min_wins of the shuffles. Top-N moves in coarse
    2-point steps at n=50, so ties there are allowed."""
    wins = sum(1 for r in results if r["rho_fam"] > r["rho_base"] and r["top_fam"] >= r["top_base"])
    return wins >= min_wins, wins


def trait_ranking(rows, keys):
    """Standardized ridge coefficients on all rows, largest magnitude first."""
    guard_features(rows, keys)
    X, y, w = _xyw(rows, keys)
    m = _model().fit(X, y, ridgecv__sample_weight=w)
    coef = m.named_steps["ridgecv"].coef_
    return sorted(zip(keys, (float(c) for c in coef)), key=lambda t: -abs(t[1]))
```

- [ ] **Step 4: Run** full suite → pass. **If `test_rejects_pure_noise` fails**, do NOT change the data seed to make it pass — that would hide a harness that adopts noise. Stop and report; the adoption rule needs tightening (e.g., require a mean rho gain larger than the seed-to-seed spread).
- [ ] **Step 5: Commit** `feat(prospects-model): grouped-CV harness that adopts signal and rejects noise`.

---

### Task 6: Run the test; record the verdict

**Files:** Create `whiff_test.py`; modify spec + memory with the result

- [ ] **Step 1: Create** `whiff_test.py`:

```python
"""Whiff-family test: does minor-league whiff rate / CSW predict MLB value in
this league's 4x4 beyond K% and BB%?

Usage:  python whiff_test.py     (needs cache/labels.csv -- python build_labels.py)
Writes: cache/whiff_test_report.txt
"""
import os
import statistics

from psmodel import dataset, evaluate, milb
from psmodel import features as F

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "cache", "labels.csv")
REPORT = os.path.join(HERE, "cache", "whiff_test_report.txt")
SEASONS = (2016, 2017, 2018, 2019)       # most complete MLB outcomes by 2026
LEVELS = (12, 11)                        # AA, affiliated AAA
MAX_PA, MAX_IP = 800, 250                # one level-season can't exceed these


def gather(group):
    rows = []
    for s in SEASONS:
        for lvl in LEVELS:
            rows += milb.season_rows(s, lvl, group)
    # Guard: if StatsAPI returned a combined split alongside per-team splits,
    # combining would double-count and volumes would blow past a real season.
    bad = [r for r in rows if r.get("pa", 0) > MAX_PA or r.get("ip", 0) > MAX_IP]
    if bad:
        raise SystemExit(f"{len(bad)} rows exceed one-level volume limits "
                         f"(double-counted splits?) e.g. {bad[0]['name']}")
    return rows


def run(typ, group, base, family, labels, lines):
    thr = dataset.useful_threshold(labels, typ)
    rows = dataset.build(gather(group), typ, labels, thr)
    F.standardize_within(rows, base + family)
    rows = dataset.complete_cases(rows, base + family)
    players = {r["player_id"] for r in rows}
    useful = {r["player_id"] for r in rows if r["useful"]}
    lines.append(f"\n=== {'HITTERS' if typ == 'H' else 'PITCHERS'}: {len(rows)} rows, "
                 f"{len(players)} players, {len(useful)} became starter-quality "
                 f"(peak >= {thr:.2f} SGP) ===")
    res = evaluate.compare(rows, base, family)
    for key, label in (("rho", "rank accuracy (Spearman)"), ("top", "top-50 hit rate")):
        b = [r[key + "_base"] for r in res]
        f = [r[key + "_fam"] for r in res]
        lines.append(f"  {label:26} baseline {statistics.mean(b):.3f} +/- {statistics.pstdev(b):.3f}"
                     f"   with whiff family {statistics.mean(f):.3f} +/- {statistics.pstdev(f):.3f}")
    ok, wins = evaluate.adopt(res)
    lines.append(f"  VERDICT: whiff family {'ADOPTED' if ok else 'NOT adopted'} "
                 f"({wins}/10 shuffles improved rank accuracy without hurting top-50; needs 8)")
    lines.append("  Traits by weight (standardized ridge coefficient; + means more MLB value):")
    for k, c in evaluate.trait_ranking(rows, base + family):
        lines.append(f"    {k:8} {c:+.3f}")


def main():
    labels = dataset.load_labels(LABELS)
    lines = ["Whiff-family test -- AA + affiliated AAA, 2016-2019 seasons; MLB outcomes through 2026"]
    run("H", "hitting", F.BASE_H, F.FAMILY_H, labels, lines)
    run("P", "pitching", F.BASE_P, F.FAMILY_P, labels, lines)
    text = "\n".join(lines)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nreport -> {REPORT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Security audit** (user requirement, before any network run): imports stdlib + numpy/scipy/sklearn only; hosts = `statsapi.mlb.com` only; `git ls-files prospects-model/cache` empty; no credentials.
- [ ] **Step 3: Run** `python whiff_test.py`. Expect two sections with row/player counts in the hundreds-to-low-thousands, a VERDICT per type, and trait rankings. Sanity gates before trusting it:
  - Starter-quality players should be a small minority (single-digit to low-teens %) — if half the sample is "useful", the threshold or the label join is wrong.
  - In the trait ranking, age should be negative for both types (older at a level → less value). If not, stop and investigate before interpreting anything else.
- [ ] **Step 4: Record** the verdict and trait ranking in the spec (new section "Whiff test result") and in memory `project_prospect_model.md`; send the report file to the user.
- [ ] **Step 5: Commit** `feat(prospects-model): whiff-family test driver and result`.

---

## Not in this plan

- Exit velocity / launch angle (the MLB→AAA bridge) — next plan; data is already downloaded (`cache/pbp_live`, 9,750 games).
- High-A / Single-A and 2021+ cohorts, the full walk-forward temporal backtest, model-family comparison beyond ridge — sub-project 3 proper.
- The Prospects page — sub-project 4.
