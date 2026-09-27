# Hitter Tracking Metrics + Savant Parity Implementation Plan (3b, plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute hitter tracking metrics (exit velocity, launch angle, barrels, chase, contact, spray, batted-ball mix) from our game records, PROVE they reproduce Baseball Savant's published 2024 numbers, then build the AAA metric table (2022 PCL, 2023–2026) and the MLB history table (Savant, 2015–2026) that plan B's bridge needs.

**Architecture:** `tracking.py` turns a game record into pitch-level events. `metrics.py` aggregates events into per-batter season metrics named exactly like Savant's leaderboard columns, with every uncertain definition exposed as a variant parameter. `parity_tracking.py` runs all variants on the 2024 MLB season and keeps the one that matches Savant; it is a hard gate. `savant.py` pulls MLB leaderboards with content guards. `build_tracking.py` refuses to run until parity has passed.

**Tech Stack:** Python 3.14 stdlib + already-installed numpy. Tests: stdlib `unittest`. Hosts: `statsapi.mlb.com` (game records, already downloaded) and `baseballsavant.mlb.com` (leaderboards). Nothing new installed.

Spec: `docs/superpowers/specs/2026-09-26-prospect-model-design.md` → "3b design, hitters first".

---

## Context the implementer needs

- Run from `prospects-model/`. Tests: `python -m unittest discover -s tests` (101 pass, 3 live-only skipped, before this plan).
- **Game records** are gzipped `feed/live` JSON under `cache/pbp_live/{season}/{sport_id}/{game_pk}.json.gz`. `psmodel.pbp.load_game(season, sport_id, pk)` returns the dict; plays are at `["liveData"]["plays"]["allPlays"]`. Available: AAA (`11`) 2023–2026 all games, 2022 PCL only; MLB (`1`) 2024 (downloading at plan time — `cache/pbp_live/mlb2024_log.txt`).
- **Verified encoding (MLB and AAA 2024):**
  - Each pitch event has `isPitch: true`; non-pitch events (pickoffs, subs) have `isPitch` false — skip them.
  - `details.code`: `B` ball, `*B` ball in dirt, `C` called strike, `S` swinging strike, `W` swinging strike (blocked), `F` foul, `T` foul tip, `L` foul bunt, `X`/`D`/`E` in play (out / no out / runs), `H` hit by pitch. Others that can appear: `M` missed bunt, `O` foul tip bunt, `Q` swinging pitchout, `R` foul pitchout, `P` pitchout, `I` intentional ball, `V*` automatic ball/strike.
  - `hitData.launchSpeed` appears ONLY on in-play pitches (`X`/`D`/`E`), never on fouls.
  - `hitData.trajectory` ∈ `ground_ball`, `line_drive`, `fly_ball`, `popup`, and bunt forms like `bunt_grounder`.
  - `hitData.coordinates.coordX/coordY` = Savant's `hc_x/hc_y`. `pitchData.zone` is 1–9 (in zone) or 11–14 (out) on every pitch. Handedness: `matchup.batSide.code` (`R`/`L`) per plate appearance.
- **Uncertain definitions (settled empirically by parity, not by guessing):** whether a foul tip counts as a whiff; whether bunts count as swings / batted balls; the pull threshold; the barrel window (Savant's exact window is unpublished — we use a linear widening from 26–30° at 98 mph to 8–50° at 116 mph).
- **Units:** percentages are 0–100 (Savant's convention), velocities in mph, angles in degrees.
- **Security posture (user requirement):** re-run the audit before any network step: stdlib + already-installed packages only; hosts limited to `statsapi.mlb.com` and `baseballsavant.mlb.com`; `git ls-files prospects-model/cache` empty; no credentials.
- Commits local only; end messages with `Co-Authored-By: <current model> <noreply@anthropic.com>`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `psmodel/tracking.py` | Create | Game record → pitch-level events; list/iterate a level-season's games |
| `psmodel/metrics.py` | Create | Events → per-batter Savant-named metrics; barrel + spray helpers; variants |
| `psmodel/savant.py` | Create | Savant custom + exit-velocity leaderboards with content guards |
| `parity_tracking.py` | Create | Parity gate on 2024 MLB; writes `cache/tracking_definitions.json` + report |
| `build_tracking.py` | Create | AAA metric table + MLB history table (only after parity passes) |
| `tests/test_tracking.py`, `test_metrics.py`, `test_savant.py` | Create | Unit tests |

---

### Task 1: Game records → pitch events

**Files:** Create `psmodel/tracking.py`, `tests/test_tracking.py`

- [ ] **Step 1: Failing tests** — `tests/test_tracking.py`:

```python
import gzip, json, os, tempfile, unittest
from psmodel import pbp, tracking


def pitch(code, zone, **hit):
    e = {"isPitch": True, "details": {"code": code}, "pitchData": {"zone": zone}}
    if hit:
        e["hitData"] = {"launchSpeed": hit["ev"], "launchAngle": hit["la"], "totalDistance": hit.get("dist"),
                        "trajectory": hit["traj"], "coordinates": {"coordX": hit["x"], "coordY": hit["y"]}}
    return e


GAME = {"liveData": {"plays": {"allPlays": [
    {"matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}, "batSide": {"code": "R"}, "pitchHand": {"code": "L"}},
     "playEvents": [pitch("C", 5), pitch("S", 12),
                    pitch("X", 5, ev=101.2, la=27.0, dist=410.0, traj="fly_ball", x=60.0, y=100.0)]},
    {"matchup": {"batter": {"id": 3}, "pitcher": {"id": 2}, "batSide": {"code": "L"}, "pitchHand": {"code": "L"}},
     "playEvents": [{"isPitch": False, "details": {"code": "PK"}}, pitch("B", 13), pitch("F", 4)]},
]}}}


class TestIterEvents(unittest.TestCase):
    def test_one_event_per_pitch_non_pitches_skipped(self):
        ev = list(tracking.iter_events(GAME))
        self.assertEqual(len(ev), 5)
        self.assertEqual([e["code"] for e in ev], ["C", "S", "X", "B", "F"])

    def test_fields(self):
        ev = list(tracking.iter_events(GAME))
        bip = ev[2]
        self.assertEqual((bip["batter"], bip["pitcher"], bip["bat_side"], bip["pitch_hand"]), (1, 2, "R", "L"))
        self.assertEqual((bip["ev"], bip["la"], bip["dist"], bip["traj"]), (101.2, 27.0, 410.0, "fly_ball"))
        self.assertEqual((bip["hc_x"], bip["hc_y"], bip["zone"]), (60.0, 100.0, 5))
        self.assertIsNone(ev[0]["ev"])
        self.assertEqual(ev[3]["bat_side"], "L")


class TestSeasonGames(unittest.TestCase):
    def test_lists_game_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            old = pbp.PBP_DIR
            try:
                pbp.PBP_DIR = d
                folder = os.path.join(d, "2024", "11")
                os.makedirs(folder)
                for name in ("9.json.gz", "10.json.gz"):
                    with gzip.open(os.path.join(folder, name), "wt", encoding="utf-8") as fh:
                        json.dump(GAME, fh)
                with open(os.path.join(folder, "_manifest.json"), "w") as fh:
                    fh.write("{}")
                self.assertEqual(tracking.season_games(2024, 11), [9, 10])
                self.assertEqual(len(list(tracking.season_events(2024, 11))), 10)
            finally:
                pbp.PBP_DIR = old


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_tracking` → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/tracking.py`:

```python
"""Pitch-level events from complete game records (cache/pbp_live).

One parser for MLB and AAA, so a metric computed from these events means the
same thing at both levels -- which parity_tracking.py then proves against
Baseball Savant's published numbers.
"""
import glob
import os

from . import pbp


def iter_events(game):
    """One dict per PITCH: ids, handedness, result code, zone, and batted-ball
    fields when the pitch was put in play (None otherwise)."""
    plays = (((game or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    for play in plays:
        m = play.get("matchup") or {}
        batter = (m.get("batter") or {}).get("id")
        pitcher = (m.get("pitcher") or {}).get("id")
        side = (m.get("batSide") or {}).get("code")
        hand = (m.get("pitchHand") or {}).get("code")
        for e in play.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            det = e.get("details") or {}
            pd = e.get("pitchData") or {}
            hd = e.get("hitData") or {}
            co = hd.get("coordinates") or {}
            yield {"batter": batter, "pitcher": pitcher, "bat_side": side, "pitch_hand": hand,
                   "code": det.get("code"), "zone": pd.get("zone"),
                   "ev": hd.get("launchSpeed"), "la": hd.get("launchAngle"),
                   "dist": hd.get("totalDistance"), "traj": hd.get("trajectory"),
                   "hc_x": co.get("coordX"), "hc_y": co.get("coordY")}


def season_games(season, sport_id):
    """Sorted game_pks with a downloaded record for one level-season."""
    folder = os.path.join(pbp.PBP_DIR, str(int(season)), str(int(sport_id)))
    pks = []
    for f in glob.glob(os.path.join(folder, "*.json.gz")):
        stem = os.path.basename(f).split(".")[0]
        if stem.isdigit():
            pks.append(int(stem))
    return sorted(pks)


def season_events(season, sport_id):
    for pk in season_games(season, sport_id):
        yield from iter_events(pbp.load_game(season, sport_id, pk))
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): game records to pitch-level events`.

---

### Task 2: Metrics with definition variants

**Files:** Create `psmodel/metrics.py`, `tests/test_metrics.py`

- [ ] **Step 1: Failing tests** — `tests/test_metrics.py`:

```python
import unittest
from psmodel import metrics as M


def ev(code, zone, side="R", **hit):
    e = {"batter": 1, "pitcher": 2, "bat_side": side, "pitch_hand": "R", "code": code, "zone": zone,
         "ev": None, "la": None, "dist": None, "traj": None, "hc_x": None, "hc_y": None}
    e.update(hit)
    return e


EVENTS = [
    ev("C", 5),                                                       # called strike, zone, no swing
    ev("S", 12),                                                      # whiff out of zone
    ev("F", 4),                                                       # foul in zone
    ev("T", 6),                                                       # foul tip in zone
    ev("X", 5, ev=100.0, la=28.0, dist=400.0, traj="fly_ball", hc_x=60.0, hc_y=100.0),     # pulled (RHB)
    ev("B", 13),                                                      # ball out of zone
    ev("D", 7, ev=90.0, la=10.0, dist=250.0, traj="line_drive", hc_x=125.42, hc_y=100.0),  # straightaway
    ev("L", 8),                                                       # foul bunt in zone
]


class TestBarrel(unittest.TestCase):
    def test_window(self):
        self.assertTrue(M.is_barrel(98.0, 28.0))
        self.assertFalse(M.is_barrel(98.0, 25.0))
        self.assertFalse(M.is_barrel(97.9, 28.0))
        self.assertTrue(M.is_barrel(116.0, 8.0))
        self.assertFalse(M.is_barrel(116.0, 51.0))
        self.assertTrue(M.is_barrel(120.0, 50.0), "window stops widening at 116 mph")
        self.assertFalse(M.is_barrel(None, 28.0))


class TestSpray(unittest.TestCase):
    def test_pull_depends_on_handedness(self):
        self.assertEqual(M.direction(ev("X", 5, "R", hc_x=60.0, hc_y=100.0), 15.0), "pull")
        self.assertEqual(M.direction(ev("X", 5, "L", hc_x=60.0, hc_y=100.0), 15.0), "oppo")
        self.assertEqual(M.direction(ev("X", 5, "R", hc_x=125.42, hc_y=100.0), 15.0), "straight")
        self.assertIsNone(M.direction(ev("X", 5, "R"), 15.0))


class TestDefault(unittest.TestCase):
    def setUp(self):
        self.m = M.hitter_metrics(EVENTS)[1]

    def test_discipline(self):
        m = self.m
        self.assertEqual((m["pitches"], m["swings"]), (8, 6))
        self.assertAlmostEqual(m["whiff_percent"], 100 / 6)
        self.assertAlmostEqual(m["swing_percent"], 75.0)
        self.assertAlmostEqual(m["oz_swing_percent"], 50.0)
        self.assertAlmostEqual(m["oz_contact_percent"], 0.0)
        self.assertAlmostEqual(m["z_swing_percent"], 500 / 6)
        self.assertAlmostEqual(m["iz_contact_percent"], 100.0)

    def test_batted_balls(self):
        m = self.m
        self.assertEqual(m["bbe"], 2)
        self.assertAlmostEqual(m["exit_velocity_avg"], 95.0)
        self.assertAlmostEqual(m["max_hit_speed"], 100.0)
        self.assertAlmostEqual(m["avg_best_speed"], 100.0)
        self.assertAlmostEqual(m["hard_hit_percent"], 50.0)
        self.assertAlmostEqual(m["barrel_batted_rate"], 50.0)
        self.assertAlmostEqual(m["sweet_spot_percent"], 100.0)
        self.assertAlmostEqual(m["launch_angle_avg"], 19.0)
        self.assertAlmostEqual(m["avg_distance"], 325.0)
        self.assertAlmostEqual(m["flyballs_percent"], 50.0)
        self.assertAlmostEqual(m["linedrives_percent"], 50.0)
        self.assertAlmostEqual(m["pull_percent"], 50.0)
        self.assertAlmostEqual(m["straightaway_percent"], 50.0)
        self.assertAlmostEqual(m["opposite_percent"], 0.0)


class TestVariants(unittest.TestCase):
    def test_foul_tip_as_whiff(self):
        m = M.hitter_metrics(EVENTS, {"foul_tip_is_whiff": True})[1]
        self.assertAlmostEqual(m["whiff_percent"], 200 / 6)
        self.assertAlmostEqual(m["iz_contact_percent"], 80.0)

    def test_bunts_excluded(self):
        m = M.hitter_metrics(EVENTS, {"count_bunts": False})[1]
        self.assertEqual(m["swings"], 5)
        self.assertAlmostEqual(m["whiff_percent"], 20.0)
        self.assertAlmostEqual(m["z_swing_percent"], 400 / 6)

    def test_bunt_batted_balls_follow_the_variant(self):
        bunt = ev("X", 5, ev=40.0, la=-20.0, dist=20.0, traj="bunt_grounder", hc_x=150.0, hc_y=170.0)
        self.assertEqual(M.hitter_metrics([bunt])[1]["groundballs_percent"], 100.0)
        self.assertEqual(M.hitter_metrics([bunt], {"count_bunts": False})[1]["bbe"], 0)

    def test_zero_denominators_are_none(self):
        m = M.hitter_metrics([ev("B", 13)])[1]
        self.assertIsNone(m["whiff_percent"])
        self.assertIsNone(m["exit_velocity_avg"])
        self.assertIsNone(m["oz_contact_percent"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/metrics.py`:

```python
"""Hitter tracking metrics, named and defined to match Baseball Savant's
leaderboard columns, so MLB history (from Savant) and AAA (computed here from
game records) mean the same thing.

Every definition that is not certain is a variant parameter; parity_tracking.py
runs them all on the 2024 MLB season and keeps whichever reproduces Savant.
"""
import math

WHIFF_CODES = {"S", "W", "M", "Q"}                         # swinging strike (+blocked), missed bunt, swinging pitchout
CONTACT_CODES = {"F", "T", "L", "O", "R", "X", "D", "E"}   # fouls, foul tip, foul bunt/tip bunt, foul pitchout, in play
IN_PLAY = {"X", "D", "E"}
BUNT_CODES = {"L", "M", "O"}
BUNT_TRAJ = {"bunt_grounder": "ground_ball", "bunt_popup": "popup", "bunt_line_drive": "line_drive"}

DEFAULT = {"foul_tip_is_whiff": False, "count_bunts": True, "pull_deg": 15.0}

BATTED_BALL_METRICS = [
    "exit_velocity_avg", "max_hit_speed", "avg_best_speed", "hard_hit_percent", "barrel_batted_rate",
    "sweet_spot_percent", "launch_angle_avg", "avg_distance",
    "groundballs_percent", "linedrives_percent", "flyballs_percent", "popups_percent",
    "pull_percent", "straightaway_percent", "opposite_percent",
]
DISCIPLINE_METRICS = [
    "whiff_percent", "swing_percent", "oz_swing_percent", "z_swing_percent",
    "oz_contact_percent", "iz_contact_percent",
]
HITTER_METRICS = BATTED_BALL_METRICS + DISCIPLINE_METRICS


def is_barrel(ev, la):
    """Statcast barrel: EV >= 98 mph with a launch-angle window that widens with
    EV -- 26-30 deg at 98 mph out to 8-50 deg at 116 mph and above. Savant's exact
    window is unpublished; parity_tracking.py measures how close this gets."""
    if ev is None or la is None or ev < 98.0:
        return False
    x = min(ev, 116.0) - 98.0
    return (26.0 - x) <= la <= (30.0 + x * (20.0 / 18.0))


def direction(e, pull_deg):
    """'pull' | 'straight' | 'oppo' from Savant-style spray angle, mirrored for
    left-handed batters; None when coordinates or handedness are missing."""
    x, y, side = e.get("hc_x"), e.get("hc_y"), e.get("bat_side")
    if x is None or y is None or side not in ("R", "L") or y >= 198.27:
        return None
    angle = math.degrees(math.atan((x - 125.42) / (198.27 - y)))
    if side == "L":
        angle = -angle
    if angle < -pull_deg:
        return "pull"
    if angle > pull_deg:
        return "oppo"
    return "straight"


def _pct(n, d):
    return 100.0 * n / d if d else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def hitter_metrics(events, variant=None):
    """{batter_id: {metric: value, 'bbe', 'swings', 'pitches'}} for the events given
    (normally one level-season)."""
    v = dict(DEFAULT, **(variant or {}))
    acc = {}
    for e in events:
        b = e.get("batter")
        if b is None:
            continue
        a = acc.setdefault(b, {"pitches": 0, "swings": 0, "whiffs": 0, "iz": 0, "oz": 0,
                               "iz_sw": 0, "oz_sw": 0, "iz_con": 0, "oz_con": 0, "bbe": []})
        code = e.get("code")
        a["pitches"] += 1
        whiff = code in WHIFF_CODES or (v["foul_tip_is_whiff"] and code == "T")
        contact = code in CONTACT_CODES and not whiff
        if code in BUNT_CODES and not v["count_bunts"]:
            whiff = contact = False
        swing = whiff or contact
        z = e.get("zone")
        a["swings"] += swing
        a["whiffs"] += whiff
        if z is not None and 1 <= z <= 9:
            a["iz"] += 1; a["iz_sw"] += swing; a["iz_con"] += contact
        elif z is not None and z >= 11:
            a["oz"] += 1; a["oz_sw"] += swing; a["oz_con"] += contact
        if code in IN_PLAY and e.get("ev") is not None:
            if e.get("traj") in BUNT_TRAJ and not v["count_bunts"]:
                continue
            a["bbe"].append(e)

    out = {}
    for b, a in acc.items():
        bb = a["bbe"]
        n = len(bb)
        evs = sorted((x["ev"] for x in bb), reverse=True)
        las = [x["la"] for x in bb if x.get("la") is not None]
        traj = [BUNT_TRAJ.get(x.get("traj"), x.get("traj")) for x in bb]
        spray = [d for d in (direction(x, v["pull_deg"]) for x in bb) if d]
        out[b] = {
            "exit_velocity_avg": _mean(evs),
            "max_hit_speed": evs[0] if evs else None,
            "avg_best_speed": _mean(evs[:math.ceil(n / 2)]) if n else None,
            "hard_hit_percent": _pct(sum(1 for s in evs if s >= 95.0), n),
            "barrel_batted_rate": _pct(sum(1 for x in bb if is_barrel(x["ev"], x.get("la"))), n),
            "sweet_spot_percent": _pct(sum(1 for la in las if 8.0 <= la <= 32.0), len(las)),
            "launch_angle_avg": _mean(las),
            "avg_distance": _mean([x["dist"] for x in bb if x.get("dist") is not None]),
            "groundballs_percent": _pct(traj.count("ground_ball"), n),
            "linedrives_percent": _pct(traj.count("line_drive"), n),
            "flyballs_percent": _pct(traj.count("fly_ball"), n),
            "popups_percent": _pct(traj.count("popup"), n),
            "pull_percent": _pct(spray.count("pull"), len(spray)),
            "straightaway_percent": _pct(spray.count("straight"), len(spray)),
            "opposite_percent": _pct(spray.count("oppo"), len(spray)),
            "whiff_percent": _pct(a["whiffs"], a["swings"]),
            "swing_percent": _pct(a["swings"], a["pitches"]),
            "oz_swing_percent": _pct(a["oz_sw"], a["oz"]),
            "z_swing_percent": _pct(a["iz_sw"], a["iz"]),
            "oz_contact_percent": _pct(a["oz_con"], a["oz_sw"]),
            "iz_contact_percent": _pct(a["iz_con"], a["iz_sw"]),
            "bbe": n, "swings": a["swings"], "pitches": a["pitches"],
        }
    return out
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): Savant-named hitter tracking metrics with definition variants`.

---

### Task 3: Savant leaderboards with content guards

**Files:** Create `psmodel/savant.py`, `tests/test_savant.py`

- [ ] **Step 1: Failing tests** — `tests/test_savant.py`:

```python
import unittest
from psmodel import http, savant


def custom_csv(year, rows):
    head = '"last_name, first_name",player_id,year,' + ",".join(savant.CUSTOM_FIELDS)
    lines = [head]
    for pid, vals in rows:
        lines.append(f'"X, Y",{pid},{year},' + ",".join(vals.get(f, "") for f in savant.CUSTOM_FIELDS))
    return "\n".join(lines) + "\n"


def ev_csv(rows):
    head = "last_name,first_name,player_id,attempts,max_hit_speed,avg_distance"
    return "\n".join([head] + [f"X,Y,{pid},{a},{m},{d}" for pid, a, m, d in rows]) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._orig = http.fetch_text
        self.pages = {}
        http.fetch_text = lambda url, suffix=".txt": self.pages["custom" if "custom" in url else "ev"](url)

    def tearDown(self):
        http.fetch_text = self._orig


class TestSeason(Base):
    def test_parses_and_merges(self):
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {"exit_velocity_avg": "91.2", "whiff_percent": ""})])
        self.pages["ev"] = lambda url: ev_csv([(10, 300, 115.1, 180.5)])
        got = savant.hitter_season(2024)
        self.assertAlmostEqual(got[10]["exit_velocity_avg"], 91.2)
        self.assertIsNone(got[10]["whiff_percent"])
        self.assertAlmostEqual(got[10]["max_hit_speed"], 115.1)
        self.assertAlmostEqual(got[10]["avg_distance"], 180.5)

    def test_wrong_year_in_payload_is_an_error(self):
        """Savant has silently ignored parameters before; the payload must
        reflect the request."""
        self.pages["custom"] = lambda url: custom_csv(2023, [(10, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 1, 100, 100)])
        with self.assertRaises(http.DataError):
            savant.hitter_season(2024)


class TestHistory(Base):
    def test_identical_seasons_are_an_error(self):
        """The exit-velocity board has no year column, so an ignored year
        parameter would return the same file every season. Catch that."""
        self.pages["custom"] = lambda url: custom_csv(int(url.split("year=")[1][:4]), [(10, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 1, 100, 100)])
        with self.assertRaises(http.DataError):
            savant.hitter_history(2023, 2024)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `psmodel/savant.py`:

```python
"""Baseball Savant season leaderboards (MLB) for the bridge's MLB history.

Content guards, because Savant has silently ignored parameters before
(minors=true; and StatsAPI's metricAverages ignored sportId): the custom board's
'year' column must equal the request, and no two seasons may come back
byte-identical (the exit-velocity board has no year column to check).
"""
import csv
import hashlib
import io

from . import http
from .metrics import HITTER_METRICS

EV_FIELDS = ("max_hit_speed", "avg_distance")
CUSTOM_FIELDS = [m for m in HITTER_METRICS if m not in EV_FIELDS] + ["pa"]
CUSTOM_URL = ("https://baseballsavant.mlb.com/leaderboard/custom?year={year}&type=batter&min=1"
              "&selections={sel}&csv=true")
EV_URL = ("https://baseballsavant.mlb.com/leaderboard/statcast?type=batter&year={year}"
          "&position=&team=&min=1&csv=true")


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def hitter_season(year, _seen=None):
    """{player_id: {field: value}} for one MLB season (CUSTOM_FIELDS + EV_FIELDS)."""
    ctext = http.fetch_text(CUSTOM_URL.format(year=year, sel=",".join(CUSTOM_FIELDS)), ".csv")
    etext = http.fetch_text(EV_URL.format(year=year), ".csv")
    if _seen is not None:
        for tag, text in (("custom", ctext), ("exit-velocity", etext)):
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if (tag, digest) in _seen:
                raise http.DataError(f"Savant {tag} leaderboard for {year} is identical to "
                                     f"{_seen[(tag, digest)]} -- year parameter ignored?")
            _seen[(tag, digest)] = year
    crows, erows = _rows(ctext), _rows(etext)
    http.require_rows(crows, f"savant custom {year}")
    http.require_rows(erows, f"savant exit-velocity {year}")
    out = {}
    for r in crows:
        http.require_value(r.get("year"), year, f"savant custom {year}")
        out[int(r["player_id"])] = {f: _num(r.get(f)) for f in CUSTOM_FIELDS}
    for r in erows:
        d = out.setdefault(int(r["player_id"]), {f: None for f in CUSTOM_FIELDS})
        d.update({f: _num(r.get(f)) for f in EV_FIELDS})
    for d in out.values():
        for f in EV_FIELDS:
            d.setdefault(f, None)
    return out


def hitter_history(first, last):
    seen = {}
    return {y: hitter_season(y, seen) for y in range(first, last + 1)}
```

- [ ] **Step 4: Run** full suite → pass.
- [ ] **Step 5: Commit** `feat(prospects-model): Savant leaderboards with year and duplicate-content guards`.

---

### Task 4: The parity gate (runs on the downloaded 2024 MLB season)

**Files:** Create `parity_tracking.py`

- [ ] **Step 1: Confirm the download finished:** `cache/pbp_live/2024/1/_manifest.json` exists with `"failed": 0`, and `python -c "from psmodel import tracking; print(len(tracking.season_games(2024,1)))"` prints 2430. If not, rerun `python fetch_pbp.py --seasons 2024 --levels 1` (it resumes).
- [ ] **Step 2: Security audit** (hosts must be only `statsapi.mlb.com` and `baseballsavant.mlb.com`; cache untracked; no credentials).
- [ ] **Step 3: Create** `parity_tracking.py`:

```python
"""Parity gate: our tracking-metric code, run on the 2024 MLB game records, must
reproduce Baseball Savant's published 2024 leaderboard numbers before any AAA
metric is trusted -- the same idea as parity/compare.py for the SGP labels.

Uncertain definitions are run as variants; the best-matching one is written to
cache/tracking_definitions.json, which build_tracking.py requires.

Usage:  python parity_tracking.py
"""
import json
import os

import numpy as np

from psmodel import metrics, savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "cache", "tracking_parity_report.txt")
DEFS = os.path.join(HERE, "cache", "tracking_definitions.json")
SEASON = 2024
MIN_BBE, MIN_SWINGS = 100, 300
GATE_R, GATE_R_BARREL = 0.98, 0.95          # barrel window is unpublished, so a looser bar
VARIANTS = [{"foul_tip_is_whiff": ft, "count_bunts": cb, "pull_deg": pd}
            for ft in (False, True) for cb in (True, False) for pd in (15.0, 22.5)]


def score(ours, theirs):
    per = {}
    for m in metrics.HITTER_METRICS:
        need, floor = ("bbe", MIN_BBE) if m in metrics.BATTED_BALL_METRICS else ("swings", MIN_SWINGS)
        pairs = [(o[m], theirs[p][m]) for p, o in ours.items()
                 if p in theirs and o[need] >= floor
                 and o[m] is not None and theirs[p].get(m) is not None]
        if len(pairs) < 30:
            per[m] = {"n": len(pairs), "r": None, "mad": None, "sd": None}
            continue
        a, b = np.array(pairs, dtype=float).T
        per[m] = {"n": len(pairs), "r": float(np.corrcoef(a, b)[0, 1]),
                  "mad": float(np.mean(np.abs(a - b))), "sd": float(np.std(b)),
                  "bias": float(np.mean(a - b))}
    return per


def loss(per):
    return sum(p["mad"] / p["sd"] for p in per.values() if p["mad"] is not None and p["sd"])


def main():
    games = tracking.season_games(SEASON, 1)
    if len(games) < 2400:
        raise SystemExit(f"only {len(games)} 2024 MLB games on disk -- finish the download first")
    events = list(tracking.season_events(SEASON, 1))
    theirs = savant.hitter_season(SEASON)
    results = sorted(((loss(per), v, per) for v in VARIANTS
                      for per in [score(metrics.hitter_metrics(events, v), theirs)]),
                     key=lambda t: t[0])
    best_loss, best, per = results[0]
    fails = [m for m, p in per.items()
             if p["r"] is None or p["r"] < (GATE_R_BARREL if m == "barrel_batted_rate" else GATE_R)]

    lines = [f"Tracking parity -- our code on {len(games)} 2024 MLB games vs Savant's 2024 leaderboards",
             f"Variants tried: {len(VARIANTS)}; ranked by total normalized error (lower is better):"]
    for l_, v, _ in results:
        lines.append(f"  {l_:7.3f}  {v}")
    lines.append(f"\nChosen: {best}\n")
    lines.append(f"  {'metric':22} {'n':>5} {'r':>7} {'mean|diff|':>11} {'bias':>7}  gate")
    for m in metrics.HITTER_METRICS:
        p = per[m]
        bar = GATE_R_BARREL if m == "barrel_batted_rate" else GATE_R
        ok = p["r"] is not None and p["r"] >= bar
        r_txt = f"{p['r']:.4f}" if p["r"] is not None else "   n/a"
        extra = f"{p['mad']:11.3f} {p['bias']:+7.3f}" if p["mad"] is not None else f"{'':11} {'':7}"
        lines.append(f"  {m:22} {p['n']:5d} {r_txt:>7} {extra}  {'PASS' if ok else 'FAIL (needs ' + str(bar) + ')'}")
    lines.append("\nVERDICT: " + ("PASS -- AAA metrics can be trusted on Savant's definitions" if not fails
                                  else f"FAIL on {fails} -- do not build AAA metrics until resolved"))
    text = "\n".join(lines)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(DEFS, "w", encoding="utf-8") as fh:
        json.dump({"season": SEASON, "variant": best, "passed": not fails, "failed": fails,
                   "per_metric": per}, fh, indent=2)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run** `python parity_tracking.py`.
  - **PASS:** continue to Task 5.
  - **FAIL:** do NOT loosen the gate. Report the failing metrics with their r / bias to the user. Likely causes to investigate in order: a code set (e.g. automatic strikes `VS`, pitchouts), the pull threshold (inspect Savant's definition), the barrel window (a metric that fails only on barrel can be dropped — EV and LA carry the same information). Fix, re-run, and only then proceed.
- [ ] **Step 5: Commit** `feat(prospects-model): tracking parity gate vs Savant` (the driver; the report and definitions JSON live in gitignored `cache/`). Record the verdict and chosen variant in the spec.

---

### Task 5: AAA metric table + MLB history table

**Files:** Create `build_tracking.py`

- [ ] **Step 1: Security audit** (same checks; this step contacts `baseballsavant.mlb.com` for 12 seasons).
- [ ] **Step 2: Create** `build_tracking.py`:

```python
"""After the parity gate passes: AAA hitter tracking metrics (2022 PCL-only,
2023-2026) computed with the parity-chosen definitions, and the MLB history
from Savant (2015-2026). Writes cache/aaa_tracking.csv and cache/mlb_tracking.csv
(gitignored -- derived artifacts only).

Usage:  python build_tracking.py
"""
import csv
import json
import os
import statistics

from psmodel import metrics, savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
DEFS = os.path.join(HERE, "cache", "tracking_definitions.json")
AAA_OUT = os.path.join(HERE, "cache", "aaa_tracking.csv")
MLB_OUT = os.path.join(HERE, "cache", "mlb_tracking.csv")
AAA_SEASONS = (2022, 2023, 2024, 2025, 2026)     # 2022 was tracked only in the PCL
MLB_FIRST, MLB_LAST = 2015, 2026
COLS = ["player_id", "season", "level", "bbe", "swings", "pitches", "pa"] + metrics.HITTER_METRICS


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
        raise SystemExit(f"tracking parity has not passed ({defs.get('failed')}) -- "
                         "run parity_tracking.py and resolve failures first")
    variant = defs["variant"]

    aaa = []
    for season in AAA_SEASONS:
        by = metrics.hitter_metrics(tracking.season_events(season, 11), variant)
        for pid, m in by.items():
            aaa.append(dict(m, player_id=pid, season=season, level="AAA"))
        q = [m["exit_velocity_avg"] for m in by.values() if m["bbe"] >= 100]
        print(f"AAA {season}: {len(by)} hitters, {len(q)} with 100+ batted balls, "
              f"median avg EV {statistics.median(q):.1f}" if q else f"AAA {season}: {len(by)} hitters")

    mlb = []
    for year, by in savant.hitter_history(MLB_FIRST, MLB_LAST).items():
        for pid, m in by.items():
            mlb.append(dict(m, player_id=pid, season=year, level="MLB"))
        q = [m["exit_velocity_avg"] for m in by.values()
             if m.get("exit_velocity_avg") is not None and (m.get("pa") or 0) >= 300]
        print(f"MLB {year}: {len(by)} hitters, median avg EV (300+ PA) "
              f"{statistics.median(q):.1f}" if q else f"MLB {year}: {len(by)} hitters")

    write(AAA_OUT, aaa)
    write(MLB_OUT, mlb)
    print(f"wrote {len(aaa)} AAA rows -> {AAA_OUT}\nwrote {len(mlb)} MLB rows -> {MLB_OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run** `python build_tracking.py`. Sanity gates before trusting it:
  - AAA 2023–2026 each have ~350+ hitters with 100+ batted balls; 2022 about half that (PCL only).
  - Median avg EV is in the high-80s mph at both levels (AAA slightly below or near MLB). A median far outside 84–92 means a parsing or unit error — stop.
  - Every MLB season 2015–2026 is present (the duplicate-content guard would have stopped a silently repeated season).
- [ ] **Step 4: Commit** `feat(prospects-model): AAA tracking table and Savant MLB history`. Record row counts and the sanity numbers in the spec and memory; tell the user plan B (the bridge model) is next and needs Opus for design.

---

## Not in this plan (plan B)

- The bridge model: MLB metrics in season t → value in t+1 (given playing time), ridge vs gbm, **grouped importance** (contact / power / discipline / batted-ball mix / age), and the interaction report.
- AAA → MLB translation from players with both levels in the same season (2023–26).
- Validation on the 2022–23 AAA cohorts against their MLB outcomes.
- Pitchers (after hitters are proven).
