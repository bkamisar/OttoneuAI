# Pitchers Plan P-B: Pitch-Tracking Parity and Tables — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that our game-record parser reproduces Baseball Savant's published pitcher stuff numbers. Then build the AAA (ours) and MLB (Savant) pitch-tracking tables the stuff score will use.

**Architecture:** This mirrors the hitter plan 3b-A:
- `tracking.iter_pitches` reads per-pitch tracking fields.
- `psmodel/pitch_metrics.py` computes Savant-named metrics on each pitcher's primary fastball.
- `savant.pitcher_season` reads Savant's pitcher leaderboard with the same primary-fastball rule.
- `parity_pitch.py` gates on the 2024 MLB season.
- `build_pitch_tracking.py` writes the tables.

**Spec:** `docs/superpowers/specs/2026-09-28-pitchers-design.md`, "Stuff layer design".

---

## Ground rules

- **Where to run:** from `prospects-model/`. Tests: `python -m unittest discover -s tests`. Before this plan: **212 pass, 3 skipped**.
- **Network:** Savant's pitcher leaderboard only (`baseballsavant.mlb.com`), one cached CSV per season 2015–2026, in Tasks 4–5. **Run the security audit (Task 4 Step 1) before the first network call.** The game records are already on disk.
- **`cache/` is never committed.**
- **Commits:** commit locally after each task. **Never push, fetch or pull.**
- **Parity failure is a stop.** If the gate fails, don't build the tables, and don't loosen the gate. Hand to Opus.

---

### Task 0: Preflight

- [ ] Run `python -m unittest discover -s tests`. Expected: 212 pass, 3 skipped.
- [ ] Run `ls cache/pbp_live/2024/1 | wc -l` (about 2,430) and `ls cache/tracking_definitions.json`.

### Task 1: Per-pitch tracking fields (`tracking.iter_pitches`)

**Files:** Modify `psmodel/tracking.py`; Test `tests/test_tracking.py`.

- [ ] **Step 1: Failing test.** Add above `if __name__ == "__main__":` in `tests/test_tracking.py`:

```python
class TestIterPitches(unittest.TestCase):
    def test_pitch_tracking_fields(self):
        game = {"liveData": {"plays": {"allPlays": [{"matchup": {"pitcher": {"id": 7}}, "playEvents": [
            {"isPitch": True, "details": {"code": "S", "type": {"code": "FF"}},
             "pitchData": {"startSpeed": 96.1,
                           "breaks": {"spinRate": 2400, "breakVerticalInduced": 17.0, "breakHorizontal": -6.5},
                           "coordinates": {"pfxX": -5.9, "pfxZ": 11.2}}},
            {"isPitch": False, "details": {"code": "X"}}]}]}}}
        self.assertEqual(list(tracking.iter_pitches(game)), [
            {"pitcher": 7, "type": "FF", "code": "S", "speed": 96.1, "spin": 2400, "ivb": 17.0, "hb": -6.5,
             "pfx_x": -5.9, "pfx_z": 11.2}])
```

- [ ] **Step 2:** Run `python -m unittest tests.test_tracking -v`. Expected: ERROR, `AttributeError: ... no attribute 'iter_pitches'`.

- [ ] **Step 3: Implement.** Append to `psmodel/tracking.py`:

```python
def iter_pitches(game):
    """One dict per PITCH with the fields a pitcher's stuff is measured by: pitch
    type, result code, release speed, spin, induced vertical and horizontal break
    (breaks, inches) and the pfx movement coordinates (a parity variant)."""
    plays = (((game or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    for play in plays:
        pitcher = ((play.get("matchup") or {}).get("pitcher") or {}).get("id")
        for e in play.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            det = e.get("details") or {}
            pd = e.get("pitchData") or {}
            br = pd.get("breaks") or {}
            co = pd.get("coordinates") or {}
            yield {"pitcher": pitcher, "type": (det.get("type") or {}).get("code"), "code": det.get("code"),
                   "speed": pd.get("startSpeed"), "spin": br.get("spinRate"),
                   "ivb": br.get("breakVerticalInduced"), "hb": br.get("breakHorizontal"),
                   "pfx_x": co.get("pfxX"), "pfx_z": co.get("pfxZ")}


def season_pitches(season, sport_id):
    for pk in season_games(season, sport_id):
        yield from iter_pitches(pbp.load_game(season, sport_id, pk))
```

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **213 pass**, 3 skipped.
- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/tracking.py tests/test_tracking.py
git commit -m "feat(pitchers): per-pitch tracking fields from game records (type, speed, spin, movement)"
```

### Task 2: Pitch metrics (`psmodel/pitch_metrics.py`)

**Files:** Create `psmodel/pitch_metrics.py`; Test `tests/test_pitch_metrics.py`.

- [ ] **Step 1: Failing tests.** Create `tests/test_pitch_metrics.py`:

```python
import unittest

from psmodel import pitch_metrics as PM


def pitch(pid, typ, code="B", speed=95.0, spin=2300.0, ivb=16.0, hb=-8.0, pfx_x=-0.7, pfx_z=1.3):
    return {"pitcher": pid, "type": typ, "code": code, "speed": speed, "spin": spin, "ivb": ivb, "hb": hb,
            "pfx_x": pfx_x, "pfx_z": pfx_z}


class TestPitcherMetrics(unittest.TestCase):
    def test_primary_fastball_is_the_most_thrown_and_hb_is_a_magnitude(self):
        ps = ([pitch(1, "SI", speed=94.0, hb=-15.0) for _ in range(60)]
              + [pitch(1, "FF", speed=96.0, hb=-5.0) for _ in range(20)]
              + [pitch(1, "SL", speed=85.0, spin=2500.0) for _ in range(40)])
        m = PM.pitcher_metrics(ps)[1]
        self.assertEqual((m["fb_speed"], m["fb_hb"], m["fb_n"]), (94.0, 15.0, 60))
        self.assertEqual((m["breaking_speed"], m["breaking_spin"], m["breaking_n"]), (85.0, 2500.0, 40))
        self.assertEqual(m["pitches"], 120)

    def test_too_few_pitches_of_a_kind_leave_metrics_empty(self):
        m = PM.pitcher_metrics([pitch(2, "FF") for _ in range(49)] + [pitch(2, "CU") for _ in range(29)])[2]
        self.assertIsNone(m["fb_speed"])
        self.assertIsNone(m["fb_hb"])
        self.assertIsNone(m["breaking_spin"])

    def test_whiffs_and_variants(self):
        ps = ([pitch(3, "FF", code="S") for _ in range(10)] + [pitch(3, "FF", code="F") for _ in range(20)]
              + [pitch(3, "FF", code="T") for _ in range(10)] + [pitch(3, "FF", code="B") for _ in range(20)]
              + [pitch(3, "SV") for _ in range(30)])
        m = PM.pitcher_metrics(ps)[3]
        self.assertAlmostEqual(m["whiff_percent"], 50.0)            # default: foul tips are whiffs, 20/40
        v = {"breaking": PM.BREAKING_NARROW, "movement": "pfx", "foul_tip_is_whiff": False}
        n = PM.pitcher_metrics(ps, v)[3]
        self.assertAlmostEqual(n["whiff_percent"], 25.0)            # 10/40
        self.assertIsNone(n["breaking_speed"])                      # SV isn't in the narrow set
        self.assertAlmostEqual(n["fb_ivb"], 1.3)                    # pfx movement fields


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** Run `python -m unittest tests.test_pitch_metrics -v`. Expected: ERROR (`cannot import name 'pitch_metrics'`).

- [ ] **Step 3: Implement.** Create `psmodel/pitch_metrics.py`:

```python
"""Pitcher stuff metrics, named and defined to match Baseball Savant's pitcher
leaderboard, so MLB history (from Savant) and AAA (computed here from game
records) mean the same thing.

Built on each pitcher's PRIMARY fastball -- the most-thrown of four-seam (FF),
sinker (SI) and cutter (FC) -- so sinkerballers are measured on the pitch they
live on. Horizontal break is a magnitude: its sign flips with handedness.
Uncertain definitions are variant parameters; parity_pitch.py runs them on the
2024 MLB season and keeps whichever reproduces Savant.
"""
from .metrics import BUNT_CODES, CONTACT_CODES, WHIFF_CODES

FASTBALLS = ("FF", "SI", "FC")
FB_METRICS = ["fb_speed", "fb_spin", "fb_ivb", "fb_hb"]
BREAKING_METRICS = ["breaking_speed", "breaking_spin"]
PITCH_METRICS = FB_METRICS + BREAKING_METRICS + ["whiff_percent"]
BREAKING_WIDE = ("SL", "ST", "SV", "CU", "KC", "CS")
BREAKING_NARROW = ("SL", "ST", "CU", "KC")
# The whiff definition is the hitter parity's chosen variant (cache/tracking_definitions.json).
DEFAULT = {"breaking": BREAKING_WIDE, "movement": "breaks", "foul_tip_is_whiff": True, "count_bunts": True}
MIN_FB = 50          # primary fastballs thrown before the fastball metrics count
MIN_BREAKING = 30    # breaking balls thrown before the breaking metrics count


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pitcher_metrics(pitches, variant=None):
    """{pitcher_id: {metric: value, 'pitches', 'swings', 'fb_n', 'breaking_n'}} for
    the pitches given (normally one level-season)."""
    v = dict(DEFAULT, **(variant or {}))
    hx, vz = ("hb", "ivb") if v["movement"] == "breaks" else ("pfx_x", "pfx_z")
    acc = {}
    for p in pitches:
        pid = p.get("pitcher")
        if pid is None:
            continue
        a = acc.setdefault(pid, {"pitches": 0, "swings": 0, "whiffs": 0, "by": {}})
        a["pitches"] += 1
        code = p.get("code")
        whiff = code in WHIFF_CODES or (v["foul_tip_is_whiff"] and code == "T")
        contact = code in CONTACT_CODES and not whiff
        if code in BUNT_CODES and not v["count_bunts"]:
            whiff = contact = False
        a["swings"] += whiff or contact
        a["whiffs"] += whiff
        a["by"].setdefault(p.get("type"), []).append(p)

    out = {}
    for pid, a in acc.items():
        fb = a["by"].get(max(FASTBALLS, key=lambda t: len(a["by"].get(t, ()))), [])
        fb = fb if len(fb) >= MIN_FB else []
        brk = [p for t in v["breaking"] for p in a["by"].get(t, ())]
        brk = brk if len(brk) >= MIN_BREAKING else []
        hb = _mean([p.get(hx) for p in fb])
        out[pid] = {
            "fb_speed": _mean([p.get("speed") for p in fb]),
            "fb_spin": _mean([p.get("spin") for p in fb]),
            "fb_ivb": _mean([p.get(vz) for p in fb]),
            "fb_hb": abs(hb) if hb is not None else None,
            "breaking_speed": _mean([p.get("speed") for p in brk]),
            "breaking_spin": _mean([p.get("spin") for p in brk]),
            "whiff_percent": 100.0 * a["whiffs"] / a["swings"] if a["swings"] else None,
            "pitches": a["pitches"], "swings": a["swings"], "fb_n": len(fb), "breaking_n": len(brk),
        }
    return out
```

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **216 pass**, 3 skipped.
- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/pitch_metrics.py tests/test_pitch_metrics.py
git commit -m "feat(pitchers): Savant-named stuff metrics on the primary fastball, with parity variants"
```

### Task 3: Savant pitcher leaderboard (`savant.pitcher_season`)

**Files:** Modify `psmodel/savant.py`; Test `tests/test_savant.py`.

- [ ] **Step 1: Failing tests.** Add above `if __name__ == "__main__":` in `tests/test_savant.py`. `Base` routes any URL containing "custom" to `self.pages["custom"]`.

```python
def pitcher_csv(year, rows):
    head = '"last_name, first_name",player_id,year,' + ",".join(savant.PITCHER_FIELDS)
    lines = [head] + [f'"X, Y",{pid},{year},' + ",".join(vals.get(f, "") for f in savant.PITCHER_FIELDS)
                      for pid, vals in rows]
    return "\n".join(lines) + "\n"


class TestPitcherSeason(Base):
    def test_primary_fastball_and_magnitude(self):
        self.pages["custom"] = lambda url: pitcher_csv(2024, [
            (5, {"n_ff_formatted": "20.0", "n_si_formatted": "45.0", "si_avg_speed": "94.5", "si_avg_spin": "2150",
                 "si_avg_break_x": "-14.2", "si_avg_break_z_induced": "7.1", "ff_avg_speed": "96.0",
                 "breaking_avg_speed": "84.0", "breaking_avg_spin": "2450", "whiff_percent": "27.5",
                 "p_formatted_ip": "62.2", "pitch_count": "1010"}),
            (6, {"whiff_percent": "20.0"})])
        out = savant.pitcher_season(2024)
        self.assertEqual((out[5]["fb_speed"], out[5]["fb_hb"], out[5]["fb_ivb"], out[5]["pitches"]),
                         (94.5, 14.2, 7.1, 1010.0))
        self.assertAlmostEqual(out[5]["ip"], 62 + 2 / 3)
        self.assertIsNone(out[6]["fb_speed"])
        self.assertIsNone(out[6]["ip"])
        self.assertEqual(out[6]["whiff_percent"], 20.0)

    def test_year_guard(self):
        self.pages["custom"] = lambda url: pitcher_csv(2023, [(5, {"whiff_percent": "20.0"})])
        with self.assertRaises(http.DataError):
            savant.pitcher_season(2024)
```

- [ ] **Step 2:** Run `python -m unittest tests.test_savant -v`. Expected: ERROR (`no attribute 'PITCHER_FIELDS'`).

- [ ] **Step 3: Implement.**
  - In `psmodel/savant.py`, change `from . import http` to `from . import http, statsapi`.
  - Append:

```python
FB_TYPES = ("ff", "si", "fc")
PITCHER_FIELDS = ([f"n_{t}_formatted" for t in FB_TYPES]
                  + [f"{t}_avg_{m}" for t in FB_TYPES for m in ("speed", "spin", "break_x", "break_z_induced")]
                  + ["breaking_avg_speed", "breaking_avg_spin", "whiff_percent", "p_formatted_ip", "pitch_count"])
PITCHER_URL = ("https://baseballsavant.mlb.com/leaderboard/custom?year={year}&type=pitcher&min=1"
               "&selections={sel}&csv=true")


def pitcher_row(r):
    """One Savant pitcher row -> pitch_metrics' fields, on the most-thrown fastball
    (same rule as pitch_metrics); horizontal break as a magnitude."""
    shares = {t: _num(r.get(f"n_{t}_formatted")) or 0.0 for t in FB_TYPES}
    t = max(FB_TYPES, key=lambda k: shares[k])
    has_fb = shares[t] > 0
    hb = _num(r.get(f"{t}_avg_break_x")) if has_fb else None
    return {
        "fb_speed": _num(r.get(f"{t}_avg_speed")) if has_fb else None,
        "fb_spin": _num(r.get(f"{t}_avg_spin")) if has_fb else None,
        "fb_ivb": _num(r.get(f"{t}_avg_break_z_induced")) if has_fb else None,
        "fb_hb": abs(hb) if hb is not None else None,
        "breaking_speed": _num(r.get("breaking_avg_speed")),
        "breaking_spin": _num(r.get("breaking_avg_spin")),
        "whiff_percent": _num(r.get("whiff_percent")),
        "pitches": _num(r.get("pitch_count")),
        "ip": statsapi.parse_innings(r["p_formatted_ip"]) if r.get("p_formatted_ip") else None,
    }


def pitcher_season(year, _seen=None):
    """{player_id: pitcher_row(...)} for one MLB season, with the year guard."""
    text = http.fetch_text(PITCHER_URL.format(year=year, sel=",".join(PITCHER_FIELDS)), ".csv")
    if _seen is not None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in _seen:
            raise http.DataError(f"Savant pitcher leaderboard for {year} is identical to "
                                 f"{_seen[digest]} -- year parameter ignored?")
        _seen[digest] = year
    rows = _rows(text)
    http.require_rows(rows, f"savant pitcher {year}")
    http.require_keys(rows, ["player_id", "year"] + PITCHER_FIELDS, f"savant pitcher {year}")
    out = {}
    for r in rows:
        http.require_value(r.get("year"), year, f"savant pitcher {year}")
        out[int(r["player_id"])] = pitcher_row(r)
    return out


def pitcher_history(first, last):
    seen = {}
    return {y: pitcher_season(y, seen) for y in range(first, last + 1)}
```

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **218 pass**, 3 skipped.
- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/savant.py tests/test_savant.py
git commit -m "feat(pitchers): Savant pitcher leaderboard on the primary fastball, with year guard"
```

### Task 4: The parity gate (`parity_pitch.py`)

**Files:** Create `parity_pitch.py`.

- [ ] **Step 1: Security audit, before the first network call.** Confirm each point and state it to the user:
  1. `grep -n "https\?://" psmodel/savant.py psmodel/http.py psmodel/pbp.py` shows only `baseballsavant.mlb.com` and `statsapi.mlb.com`.
  2. The imports are stdlib, numpy and `psmodel` only.
  3. `git ls-files cache` prints nothing.
  4. No credentials: `psmodel/http.py` sends only a User-Agent.
  5. `tasklist | grep -i python` shows no stray fetch.

- [ ] **Step 2: Create `parity_pitch.py`:**

```python
"""Parity gate for pitch tracking: our pitch-metric code, run on the 2024 MLB game
records, must reproduce Baseball Savant's published 2024 pitcher numbers before any
AAA pitch metric is trusted (the hitters' parity_tracking.py, for pitchers).

Gate per metric: r >= 0.98 AND |mean bias| <= 0.1 SD. Units matter here
(movement in inches), not just correlation. Uncertain definitions run as
variants; the best is written to cache/pitch_definitions.json, which
build_pitch_tracking.py requires.

Usage:  python parity_pitch.py
Network: one Savant CSV (2024 pitchers), cached. Run the security audit first.
"""
import json
import os

import numpy as np

from psmodel import pitch_metrics as PM
from psmodel import savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "cache", "pitch_parity_report.txt")
DEFS = os.path.join(HERE, "cache", "pitch_definitions.json")
SEASON = 2024
MIN_FB, MIN_BREAKING, MIN_SWINGS = 100, 50, 200
GATE_R, GATE_BIAS_SD = 0.98, 0.10
VARIANTS = [{"breaking": b, "movement": mv}
            for b in (PM.BREAKING_WIDE, PM.BREAKING_NARROW) for mv in ("breaks", "pfx")]


def _floor(m):
    if m in PM.FB_METRICS:
        return "fb_n", MIN_FB
    if m in PM.BREAKING_METRICS:
        return "breaking_n", MIN_BREAKING
    return "swings", MIN_SWINGS


def score(ours, theirs):
    per = {}
    for m in PM.PITCH_METRICS:
        need, floor = _floor(m)
        pairs = [(o[m], theirs[p][m]) for p, o in ours.items()
                 if p in theirs and o[need] >= floor and o[m] is not None and theirs[p].get(m) is not None]
        if len(pairs) < 30:
            per[m] = {"n": len(pairs), "r": None, "mad": None, "sd": None, "bias": None}
            continue
        a, b = np.array(pairs, dtype=float).T
        per[m] = {"n": len(pairs), "r": float(np.corrcoef(a, b)[0, 1]), "mad": float(np.mean(np.abs(a - b))),
                  "sd": float(np.std(b)), "bias": float(np.mean(a - b))}
    return per


def loss(per):
    return sum(p["mad"] / p["sd"] for p in per.values() if p["mad"] is not None and p["sd"])


def passes(p):
    return p["r"] is not None and p["r"] >= GATE_R and abs(p["bias"]) <= GATE_BIAS_SD * p["sd"]


def main():
    games = tracking.season_games(SEASON, 1)
    if len(games) < 2400:
        raise SystemExit(f"only {len(games)} 2024 MLB games on disk")
    pitches = list(tracking.season_pitches(SEASON, 1))
    theirs = savant.pitcher_season(SEASON)
    results = sorted(((loss(per), v, per) for v in VARIANTS
                      for per in [score(PM.pitcher_metrics(pitches, v), theirs)]), key=lambda t: t[0])
    best_loss, best, per = results[0]
    fails = [m for m, p in per.items() if not passes(p)]

    L = [f"Pitch-tracking parity -- our code on {len(games)} 2024 MLB games ({len(pitches)} pitches) "
         f"vs Savant's 2024 pitcher leaderboard",
         f"Variants tried: {len(VARIANTS)}; ranked by total normalized error (lower is better):"]
    L += [f"  {l_:7.3f}  breaking={list(v['breaking'])} movement={v['movement']}" for l_, v, _ in results]
    L += [f"\nChosen: breaking={list(best['breaking'])} movement={best['movement']}\n",
          f"  {'metric':16} {'n':>5} {'r':>7} {'mean|diff|':>11} {'bias':>8} {'sd':>8}  gate"]
    for m in PM.PITCH_METRICS:
        p = per[m]
        if p["r"] is None:
            L.append(f"  {m:16} {p['n']:5d}     n/a  FAIL (too few pairs)")
            continue
        L.append(f"  {m:16} {p['n']:5d} {p['r']:7.4f} {p['mad']:11.3f} {p['bias']:+8.3f} {p['sd']:8.3f}  "
                 + ("PASS" if passes(p) else f"FAIL (needs r >= {GATE_R}, |bias| <= {GATE_BIAS_SD} sd)"))
    L.append("\nVERDICT: " + ("PASS -- AAA pitch metrics can be trusted on Savant's definitions" if not fails
                              else f"FAIL on {fails} -- do not build the pitch tables until resolved"))
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(DEFS, "w", encoding="utf-8") as fh:
        json.dump({"season": SEASON, "variant": dict(best, breaking=list(best["breaking"])),
                   "passed": not fails, "failed": fails, "per_metric": per}, fh, indent=2)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3:** Run `python -c "import parity_pitch"`, then commit:
```bash
git ls-files cache
git add parity_pitch.py
git commit -m "feat(pitchers): pitch-tracking parity gate vs Savant 2024 (r and bias per metric)"
```

- [ ] **Step 4: Run.** Run `python parity_pitch.py`. It reads about 2,430 games, so it takes a few minutes.
  - **Expected:** a variant table, a per-metric table and a VERDICT line.
  - **If the VERDICT is FAIL: stop.** Report the table and hand to Opus. Don't change the gate, the metrics or the variants.

### Task 5: The tables (`build_pitch_tracking.py`), only after a PASS

**Files:** Create `build_pitch_tracking.py`.

- [ ] **Step 1: Create the file:**

```python
"""After the pitch parity gate passes: AAA pitcher stuff metrics (2022 PCL-only,
2023-2026) from game records with the parity-chosen definitions, and the MLB
history from Savant (2015-2026). Writes cache/aaa_pitch_tracking.csv and
cache/mlb_pitch_tracking.csv (gitignored -- derived artifacts only).

Usage:  python build_pitch_tracking.py
Network: Savant pitcher leaderboards 2015-2026, one cached CSV per season.
"""
import csv
import json
import os
import statistics

from psmodel import pitch_metrics as PM
from psmodel import savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
DEFS = os.path.join(HERE, "cache", "pitch_definitions.json")
AAA_OUT = os.path.join(HERE, "cache", "aaa_pitch_tracking.csv")
MLB_OUT = os.path.join(HERE, "cache", "mlb_pitch_tracking.csv")
AAA_SEASONS = (2022, 2023, 2024, 2025, 2026)     # 2022 was tracked only in the PCL
MLB_FIRST, MLB_LAST = 2015, 2026
COLS = ["player_id", "season", "level", "pitches", "ip"] + PM.PITCH_METRICS


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})


def main():
    with open(DEFS, encoding="utf-8") as fh:
        defs = json.load(fh)
    if not defs.get("passed"):
        raise SystemExit(f"pitch parity has not passed ({defs.get('failed')}) -- run parity_pitch.py first")
    variant = defs["variant"]

    aaa = []
    for season in AAA_SEASONS:
        by = PM.pitcher_metrics(tracking.season_pitches(season, 11), variant)
        aaa += [dict(m, player_id=pid, season=season, level="AAA") for pid, m in by.items()]
        q = [m["fb_speed"] for m in by.values() if m["fb_n"] >= 100]
        print(f"AAA {season}: {len(by)} pitchers, {len(q)} with 100+ primary fastballs"
              + (f", median fastball {statistics.median(q):.1f} mph" if q else ""), flush=True)

    mlb = []
    for year, by in savant.pitcher_history(MLB_FIRST, MLB_LAST).items():
        mlb += [dict(m, player_id=pid, season=year, level="MLB") for pid, m in by.items()]
        q = [m["fb_speed"] for m in by.values() if m["fb_speed"] is not None and (m.get("pitches") or 0) >= 500]
        print(f"MLB {year}: {len(by)} pitchers" + (f", median fastball (500+ pitches) {statistics.median(q):.1f} mph"
                                                   if q else ""), flush=True)

    write(AAA_OUT, aaa)
    write(MLB_OUT, mlb)
    print(f"wrote {len(aaa)} AAA rows -> {AAA_OUT}\nwrote {len(mlb)} MLB rows -> {MLB_OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run `python -c "import build_pitch_tracking"`, then commit:
```bash
git ls-files cache
git add build_pitch_tracking.py
git commit -m "feat(pitchers): build AAA (game records) and MLB (Savant 2015-2026) pitch-tracking tables"
```

- [ ] **Step 3: Run** `python build_pitch_tracking.py`.
  Sanity checks (report, don't patch):
  - AAA: about 400–700 pitchers per season (2022 fewer, PCL only).
  - MLB: 700–900 pitchers per season.
  - The median primary fastball is roughly 92–95 mph at both levels, and MLB's median drifts up over the years.

- [ ] **Step 4:** Run `git status --short; git ls-files cache`. Expected: no `cache/` paths.

### Task 6: Hand to Opus

Tell the user the parity verdict and the table counts, and ask them to switch to Opus. Opus records a "P-B result" in the pitcher spec and clears P-C (`plans/2026-09-28-pitchers-stuff-score.md`).
