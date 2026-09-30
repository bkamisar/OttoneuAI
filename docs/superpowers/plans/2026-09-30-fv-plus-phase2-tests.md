# FV+ Phase 2: The FV+ Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the pre-registered FV+ tests from spec `docs/superpowers/specs/2026-09-30-fv-plus-design.md` (Phase 2 as changed by **Amendment A**) and write the report and verdict. The tests are:
- four omnibus decision tests (hitters and pitchers x rating and soon), each "FV + all pre-registered 4x4 adjustments" vs FV alone;
- the graduates-restored guard;
- the shuffle control;
- component explanations and weights;
- the provisional Statcast group;
- the exploration map and confirmation queue.

**Architecture:**
- **Board grades:** `consensus.load_board` gains the extra grade, position and org columns.
- **Ground balls:** StatsAPI rows gain ground-out and air-out counts, already in the cached JSON.
- **Standings:** a new `mlbteams` module maps Board orgs to MLB clubs and reads first-party standings. It is the only network step, 9 cached requests.
- **Pulled air:** `spray.pulled_air` measures pulled air balls from the AAA game records on disk.
- **Pure logic:** a new pure module `psmodel/fvplus.py` holds features, models, walk-forward, pooling, Holm, shuffles, partial Spearman and map cells.
- **Runner:** `fvplus_run.py` assembles the data and runs checkpointed phases (one JSON per phase; `--force` redoes them). It writes `cache/fvplus_report.txt` and `cache/fvplus_verdict.json`.

**Tech Stack:** Python 3.14, numpy, scipy, scikit-learn (already used). Runs from `prospects-model/`.

**Executed inline on Opus (the user's choice).**

**Pre-registered, from the spec and Amendment A. Never change after a result:**
- **Strict as-of walk-forward.** A test class v fits on classes c with a known answer at v (rating: c + 4 <= v; soon: c + 2 <= v), minus the test players. A test class is used only if training has >= 300 players and, for soon, >= 30 successes. Expected test classes:
  - H rating and P rating: 2021, 2022;
  - H soon: 2019, 2021, 2022, 2023, 2024;
  - P soon: 2021, 2022, 2023, 2024.

  The runner stops if the rule yields anything else.
- **Models.** Rating uses ridge (`evaluate._model("ridge")`, the project's). Soon uses a standardized logit with CV **scored by log-loss** (`LogisticRegressionCV(Cs=10, scoring="neg_log_loss")`).
  - Why log-loss: default accuracy scoring is flat when positives are 3-8%, which can pick an arbitrary penalty. Log-loss is a proper score.
  - This is a build choice, recorded here before any run.
- **Missing values:**
  - blank hitter tools, FB or CMD: that list's median;
  - no SL and no CB: breaker 20; no CH: 20;
  - any other missing value: the training mean.
- **Reliever flag:** our as-of start share below 0.5. The Board's pitcher role codes (SP/SIRP/MIRP) exist only from the 2021 list on (2017-2020 say RHP/LHP), so they can't be used for training classes.
- **Premium position:** first Board Pos token in {C, SS, CF}. The 2017-18 lists code many outfielders as "OF" (not premium); those lists are training-only.
- **Adoption (all must hold):**
  - Holm-adjusted two-sided p < 0.05 across the 4 models (pooled z = sum(d)/sqrt(sum(se^2)));
  - gain > 0 in a majority of test classes;
  - no class z <= -2;
  - soon: mean top-50 change >= -0.04;
  - real pooled gain above the 95th percentile of 200 within-FV-grade block shuffles;
  - AND the graduates-restored guard also passes: its own Holm across 4, majority, no harm, and top-50, with no shuffle.
- **Components are explanation only.** Each is the pooled gain lost when the group is dropped.
- **Statcast group:** partial Spearman with the target, controlling for `fv_score`, per class and pooled, with Holm over its 6. It is PROVISIONAL and decides nothing now.
  - Classes: soon 2022-2024, rating 2022.
  - Population: graded players whose class-season row is AAA.
  - S-EV "top third / bottom third" are computed among AAA hitters in `aaa_tracking.csv` that season with bbe >= 100.
  - S-PA needs >= 100 batted balls with an angle.
- **Exploration map:**
  - Residual = y minus the mean y of the same class and FV bucket (40/45/50/55/60, clipped).
  - Grade bins: <=40, 45-50, >50. The 2x2s use high >= 55 and low <= 45.
  - Profiles: power arm (FB >= 60 and CMD <= 40), command artist (CMD >= 55 and FB <= 50), breaker-first (breaker >= 60 and FB <= 50).
  - A cell goes to the confirmation queue if its 95% interval excludes 0 and n >= 20.
  - Classes: every class with a known answer (rating <= 2022, soon <= 2024).

---

### Task 1: Board extras

**Files:**
- Modify: `prospects-model/psmodel/consensus.py:65-78` (`load_board`)
- Create: `prospects-model/tests/test_fvplus_data.py`

- [ ] **Step 1: Write the failing test** `tests/test_fvplus_data.py`:

```python
import os
import tempfile
import unittest

from psmodel import consensus as C


HITTERS = ("Name,Org,Pos,Current Level,Age,Top 100,Org Rk,Hit,Game Pwr,Raw Pwr,Spd,FV,PA,OBP,SLG,ISO,BB%,K%,wRC+,playerId\n"
           "A B,StL,SS/2B,AA,21.5,,3,40 / 55,30 / 50,55 / 60,50 / 50,50,,,,,,,,sa1\n")
PITCHERS = ("Name,Org,Pos,Current Level,Age,Top 100,Org Rk,FB,SL,CB,CH,CMD,FV,IP,K%,BB%,GB%,ERA,xFIP,playerId\n"
            "C D,ATH,SIRP,AAA,24.0,,9,60 / 70,,50 / 55,,40 / 45,45+,,,,,,,sa2\n")


def board(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        return C.load_board(path)
    finally:
        os.remove(path)


class TestBoardExtras(unittest.TestCase):
    def test_hitter_extras(self):
        e = board(HITTERS)[0]
        self.assertEqual((e["org"], e["pos"]), ("StL", "SS"))
        self.assertEqual((e["hit_fut"], e["pwr_fut"], e["raw_pwr_fut"], e["spd_fut"]), (55, 50, 60, 50))
        self.assertIsNone(e["fb_fut"])

    def test_pitcher_extras(self):
        e = board(PITCHERS)[0]
        self.assertEqual((e["org"], e["pos"], e["fv"]), ("ATH", "SIRP", 47.5))
        self.assertEqual((e["fb_fut"], e["sl_fut"], e["cb_fut"], e["ch_fut"], e["cmd_fut"]), (70, None, 55, None, 45))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it:** `python -m pytest tests/test_fvplus_data.py -q`. Expected: 2 failures, `KeyError: 'org'`.

- [ ] **Step 3: Implement.** In `consensus.load_board`, replace the `out.append(...)` call with:

```python
            out.append({"fg_id": r["playerId"], "name": r["Name"], "key": norm_name(r["Name"]),
                        "age": _num(r.get("Age")), "fv": fv,
                        "top100": _rank(r.get("Top 100")), "org_rk": _rank(r.get("Org Rk")),
                        "hit_fut": _future(r.get("Hit")), "pwr_fut": _future(r.get("Game Pwr")),
                        "raw_pwr_fut": _future(r.get("Raw Pwr")), "spd_fut": _future(r.get("Spd")),
                        "fb_fut": _future(r.get("FB")), "sl_fut": _future(r.get("SL")),
                        "cb_fut": _future(r.get("CB")), "ch_fut": _future(r.get("CH")),
                        "cmd_fut": _future(r.get("CMD")),
                        "org": (r.get("Org") or "").strip(), "pos": (r.get("Pos") or "").split("/")[0].strip()})
```

Also change the docstring's first line to: `"""Graded players from one Board export: ids, name, age, FV, ranks, future tool/pitch grades, org, first position."""`

- [ ] **Step 4: Run** `python -m pytest tests/test_fvplus_data.py tests/test_consensus.py -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/consensus.py prospects-model/tests/test_fvplus_data.py
git commit -m "feat(fv-plus): Board loader keeps raw power, speed, pitch grades, org and position

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Ground-out and air-out counts

**Files:**
- Modify: `prospects-model/psmodel/statsapi.py` (`normalize_pitcher`)
- Modify: `prospects-model/psmodel/milb.py:12` (`_PIT_SUM`)
- Test: `prospects-model/tests/test_fvplus_data.py`

- [ ] **Step 1: Add the failing test** to `tests/test_fvplus_data.py`. Put `from psmodel import statsapi` at the top, and add this class before `if __name__`:

```python
class TestGroundOuts(unittest.TestCase):
    def test_pitcher_rows_carry_go_ao(self):
        split = {"player": {"id": 7, "fullName": "X"}, "team": {"name": "T"}, "league": {"name": "PCL"},
                 "stat": {"inningsPitched": "10.0", "groundOuts": 12, "airOuts": 8, "homeRuns": 1}}
        r = statsapi.normalize_pitcher(split, 2023, 11)
        self.assertEqual((r["go"], r["ao"]), (12, 8))
```

- [ ] **Step 2: Run:** `python -m pytest tests/test_fvplus_data.py -q`. Expected: 1 failure, `KeyError: 'go'`.

- [ ] **Step 3: Implement.**
  - In `normalize_pitcher`'s `row.update({...})`, add after `"bf": ...`:

    ```python
            "go": int(num(st.get("groundOuts"))),
            "ao": int(num(st.get("airOuts"))),
    ```

  - In `milb.py`, change `_PIT_SUM` to:

    ```python
    _PIT_SUM = ("g", "gs", "ip", "so", "bb", "hr", "np", "strikes", "bf", "go", "ao")
    ```

- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass. If a statsapi test compares a whole pitcher dict, add `"go": 0, "ao": 0` to its expected dict.

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/statsapi.py prospects-model/psmodel/milb.py prospects-model/tests/test_fvplus_data.py
git commit -m "feat(fv-plus): pitcher rows carry ground-out and air-out counts (already in cached StatsAPI data)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Parent clubs and MLB standings

**Files:**
- Create: `prospects-model/psmodel/mlbteams.py`
- Create: `prospects-model/fetch_standings.py`
- Test: `prospects-model/tests/test_fvplus_data.py`

- [ ] **Step 1: Add the failing tests** to `tests/test_fvplus_data.py`. Put `from psmodel import http, mlbteams` at the top, and add:

```python
def standings_payload(rename=None, drop=None):
    teams = [{"team": {"id": tid, "name": f"City {nick}"}, "wins": 81 + i % 5, "losses": 81 - i % 5}
             for i, (tid, nick) in enumerate(sorted(set(mlbteams.TEAMS.values())))
             if tid != drop]
    if rename:
        teams[0]["team"]["name"] = rename
    return {"records": [{"teamRecords": teams[:15]}, {"teamRecords": teams[15:]}]}


class TestStandings(unittest.TestCase):
    def test_parses_thirty_clubs(self):
        pct = mlbteams.parse_standings(standings_payload(), 2023)
        self.assertEqual(len(pct), 30)
        self.assertTrue(all(0 < v < 1 for v in pct.values()))

    def test_wrong_name_or_missing_club_is_an_error(self):
        with self.assertRaises(http.DataError):
            mlbteams.parse_standings(standings_payload(rename="Somebody Else"), 2023)
        with self.assertRaises(http.DataError):
            mlbteams.parse_standings(standings_payload(drop=147), 2023)

    def test_org_aliases(self):
        self.assertEqual(mlbteams.team_of("StL"), mlbteams.team_of("STL"))
        self.assertEqual(mlbteams.team_of("ATH")[0], 133)
        self.assertEqual(mlbteams.team_of("OAK")[0], 133)
```

- [ ] **Step 2: Run:** `python -m pytest tests/test_fvplus_data.py -q`. Expected: import failure (`mlbteams` does not exist).

- [ ] **Step 3: Write `psmodel/mlbteams.py`**

```python
"""MLB parent clubs: FanGraphs Board org codes -> MLB team ids, and each club's
regular-season winning percentage from MLB StatsAPI standings (first-party).

Content-asserted: a season must return exactly the 30 clubs below, and each
club's name must contain the nickname expected for its id.
"""
from . import http

URL = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason"
TEAMS = {
    "ARI": (109, "Diamondbacks"), "ATL": (144, "Braves"), "BAL": (110, "Orioles"), "BOS": (111, "Red Sox"),
    "CHC": (112, "Cubs"), "CHW": (145, "White Sox"), "CIN": (113, "Reds"), "CLE": (114, "Cleveland"),
    "COL": (115, "Rockies"), "DET": (116, "Tigers"), "HOU": (117, "Astros"), "KCR": (118, "Royals"),
    "LAA": (108, "Angels"), "LAD": (119, "Dodgers"), "MIA": (146, "Marlins"), "MIL": (158, "Brewers"),
    "MIN": (142, "Twins"), "NYM": (121, "Mets"), "NYY": (147, "Yankees"), "OAK": (133, "Athletics"),
    "PHI": (143, "Phillies"), "PIT": (134, "Pirates"), "SDP": (135, "Padres"), "SEA": (136, "Mariners"),
    "SFG": (137, "Giants"), "STL": (138, "Cardinals"), "TBR": (139, "Rays"), "TEX": (140, "Rangers"),
    "TOR": (141, "Blue Jays"), "WSN": (120, "Nationals"),
}
ALIASES = {"StL": "STL", "ATH": "OAK"}


def team_of(org):
    """(MLB team id, nickname) for a Board org code. An unknown code raises KeyError."""
    return TEAMS[ALIASES.get(org, org)]


def parse_standings(payload, season):
    """{team id: winning percentage} from a standings payload, content-checked."""
    got = {}
    for rec in payload.get("records") or []:
        for tr in rec.get("teamRecords") or []:
            t = tr.get("team") or {}
            w, l = int(tr.get("wins", 0)), int(tr.get("losses", 0))
            got[t.get("id")] = (t.get("name") or "", w / (w + l) if w + l else None)
    expected = dict(TEAMS.values())
    if set(got) != set(expected):
        raise http.DataError(f"standings {season}: clubs {sorted(set(got) ^ set(expected), key=str)} "
                             "don't match the 30 expected")
    for tid, nick in expected.items():
        if nick not in got[tid][0]:
            raise http.DataError(f"standings {season}: team {tid} is {got[tid][0]!r}, expected '{nick}'")
    return {tid: pct for tid, (_, pct) in got.items()}


def win_pct(season):
    return parse_standings(http.fetch_json(URL.format(season=season)), season)
```

- [ ] **Step 4: Run** `python -m pytest tests/test_fvplus_data.py -q`. Expected: all pass.

- [ ] **Step 5: Write `fetch_standings.py`**

```python
"""FV+ Phase 2: pull MLB regular-season standings (first-party StatsAPI) for the
seasons the FV+ classes need, and check them. Responses are cached under cache/
(gitignored); a rerun reads the cache and makes no requests.

Usage:  python fetch_standings.py
Network: statsapi.mlb.com only, stdlib urllib over HTTPS, no credentials.
"""
from psmodel import mlbteams

SEASONS = [s for s in range(2016, 2026) if s != 2020]
KNOWN_BEST = {2016: "CHC", 2018: "BOS", 2019: "HOU", 2022: "LAD"}   # public record, as a content check


def main():
    code_of = {tid: code for code, (tid, _) in mlbteams.TEAMS.items()}
    seen = {}
    for s in SEASONS:
        pct = mlbteams.win_pct(s)
        best, worst = max(pct, key=pct.get), min(pct, key=pct.get)
        print(f"{s}: 30 clubs; best {code_of[best]} {pct[best]:.3f}, worst {code_of[worst]} {pct[worst]:.3f}")
        if s in KNOWN_BEST and code_of[best] != KNOWN_BEST[s]:
            raise SystemExit(f"{s}: best record should be {KNOWN_BEST[s]}, got {code_of[best]}")
        seen[s] = tuple(sorted(pct.items()))
    if len(set(seen.values())) != len(seen):
        raise SystemExit("two seasons returned identical standings -- the season parameter may be ignored")
    print("standings OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Security audit (before the network step).** Confirm by reading, and state each point in the log:
  - `mlbteams` uses `http.fetch_json`: stdlib `urllib` only;
  - one host (`statsapi.mlb.com`), HTTPS with default certificate verification;
  - no credentials, cookies or personal data;
  - responses land in `prospects-model/cache/` (gitignored);
  - 1-second throttle, 9 requests total.

  Then run: `python fetch_standings.py`
  Expected: 9 season lines and `standings OK`.

- [ ] **Step 7: Commit**

```bash
git add prospects-model/psmodel/mlbteams.py prospects-model/fetch_standings.py prospects-model/tests/test_fvplus_data.py
git commit -m "feat(fv-plus): parent-club win% from first-party MLB standings, content-checked

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Pulled air from the AAA game records

**Files:**
- Modify: `prospects-model/psmodel/spray.py` (append)
- Test: `prospects-model/tests/test_spray.py`

- [ ] **Step 1: Add the failing test** to the end of `tests/test_spray.py`, before any `if __name__` block:

```python
class TestPulledAir(unittest.TestCase):
    def test_share_of_angled_balls_pulled_in_the_air(self):
        from psmodel import spray as S
        ev = lambda x, y, traj, side="R": {"code": "X", "ev": 95.0, "hc_x": x, "hc_y": y, "bat_side": side,
                                           "traj": traj, "batter": 1}
        events = [ev(60, 120, "fly_ball"),        # pulled, air
                  ev(60, 120, "ground_ball"),     # pulled, ground
                  ev(125, 100, "line_drive"),     # straightaway
                  ev(190, 120, "fly_ball", "L"),  # pulled for a lefty, air
                  {"code": "X", "ev": 90.0, "hc_x": None, "hc_y": None, "bat_side": "R", "traj": "fly_ball",
                   "batter": 1}]                  # no angle: not counted
        rate, n = S.pulled_air(events)[1]
        self.assertEqual(n, 4)
        self.assertAlmostEqual(rate, 50.0)
```

If `tests/test_spray.py` does not already `import unittest`, add it.

- [ ] **Step 2: Run:** `python -m pytest tests/test_spray.py -q`. Expected: 1 failure, `AttributeError: ... 'pulled_air'`.

- [ ] **Step 3: Append to `psmodel/spray.py`:**

```python
AIR = frozenset({"line_drive", "fly_ball"})


def pulled_air(events, pull_deg=15.0):
    """{batter: (pulled line drives + fly balls as % of batted balls with an angle,
    batted balls with an angle)}. Pull uses the same geometry as pull_and_fb."""
    acc = {}
    for e in events:
        if e.get("code") not in IN_PLAY or e.get("ev") is None:
            continue
        ang = angle(e)
        if ang is None:
            continue
        a = acc.setdefault(e["batter"], [0, 0])
        a[0] += 1
        a[1] += ang < -pull_deg and e.get("traj") in AIR
    return {b: (100.0 * a[1] / a[0], a[0]) for b, a in acc.items()}
```

- [ ] **Step 4: Run** `python -m pytest tests/test_spray.py -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/spray.py prospects-model/tests/test_spray.py
git commit -m "feat(fv-plus): pulled-air rate from charted coordinates (line drives + fly balls to the pull side)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The FV+ logic module

**Files:**
- Create: `prospects-model/psmodel/fvplus.py`
- Create: `prospects-model/tests/test_fvplus.py`

- [ ] **Step 1: Write the failing tests** `tests/test_fvplus.py`:

```python
import unittest

import numpy as np

from psmodel import fvplus as F


def hitter_entry(**kw):
    e = {"fv": 50.0, "top100": None, "org_rk": 5, "hit_fut": 55.0, "pwr_fut": 50.0, "raw_pwr_fut": 60.0,
         "spd_fut": None, "pos": "CF", "org": "NYY"}
    e.update(kw)
    return e


def pitcher_entry(**kw):
    e = {"fv": 45.0, "top100": None, "org_rk": 10, "fb_fut": 60.0, "sl_fut": None, "cb_fut": 55.0,
         "ch_fut": None, "cmd_fut": 40.0, "pos": "SP", "org": "SEA"}
    e.update(kw)
    return e


ROW = {"f": {"age": -0.5, "bb": 1.2, "is_aaa": 0.0, "is_aa": 1.0, "is_higha": 0.0}, "start_share": 0.2}


class TestKeysAndFeatures(unittest.TestCase):
    def test_keys_unique_and_drop(self):
        k = F.keys("H", "soon")
        self.assertEqual(len(k), len(set(k)))
        self.assertNotIn("sm", F.keys("H", "soon", drop="SM"))
        self.assertIn("raw_gap", F.keys("H", "rating"))
        self.assertNotIn("raw_gap", F.keys("H", "soon"))

    def test_hitter_features(self):
        x = F.features("H", hitter_entry(), ROW, {"hit_fut": 45, "pwr_fut": 45, "raw_pwr_fut": 50, "spd_fut": 40},
                       opp=0.45)
        self.assertEqual(x["spd"], 40)                 # blank -> the list median
        self.assertEqual(x["raw_gap"], 10)             # 60 - 50
        self.assertEqual(x["prem"], 1.0)
        self.assertEqual((x["bb"], x["age_rel"], x["opp"]), (1.2, -0.5, 0.45))

    def test_pitcher_features(self):
        x = F.features("P", pitcher_entry(), ROW, {"fb_fut": 50, "cmd_fut": 45}, opp=0.5, gb=0.3)
        self.assertEqual((x["brk"], x["ch"]), (55, F.NO_PITCH))
        self.assertAlmostEqual(x["fb_x_cmd"], (60 - 50) * (40 - 50) / 10)
        self.assertAlmostEqual(x["fb_x_brk"], (60 - 50) * (55 - 50) / 10)
        self.assertEqual((x["rel"], x["gb"]), (1.0, 0.3))
        x = F.features("P", pitcher_entry(sl_fut=None, cb_fut=None), dict(ROW, start_share=None), {"fb_fut": 50, "cmd_fut": 45},
                       opp=0.5)
        self.assertEqual(x["brk"], F.NO_PITCH)
        self.assertIsNone(x["rel"])


class TestMatrixAndSplit(unittest.TestCase):
    def test_matrix_fills_with_training_mean(self):
        tr = [{"x": {"a": 1.0}}, {"x": {"a": 3.0}}, {"x": {"a": None}}]
        X, fill = F.matrix(tr, ["a"])
        self.assertEqual(list(X[:, 0]), [1.0, 3.0, 2.0])
        Xt, _ = F.matrix([{"x": {"a": None}}], ["a"], fill)
        self.assertEqual(Xt[0, 0], 2.0)

    def test_split_is_as_of_and_isolates_test_players(self):
        p = lambda pid: {"player_id": pid, "x": {}}
        classes = {2016: [p(1), p(2)], 2017: [p(3)], 2019: [p(4)], 2021: [p(2), p(5)]}
        known = lambda c, v: c + 4 <= v
        train, test = F._split(classes, 2021, known, lambda q: 1.0)
        self.assertEqual(sorted(q["player_id"] for q in train), [1, 3])   # 2019 unknown; player 2 is in the test
        self.assertEqual(sorted(q["player_id"] for q in test), [2, 5])

    def test_trainable(self):
        pl = lambda n, s: [{"y": 1.0}] * s + [{"y": 0.0}] * (n - s)
        self.assertTrue(F.trainable(pl(300, 0), "rating"))
        self.assertFalse(F.trainable(pl(299, 0), "rating"))
        self.assertFalse(F.trainable(pl(400, 29), "soon"))
        self.assertTrue(F.trainable(pl(400, 30), "soon"))


class TestDecisionMath(unittest.TestCase):
    def test_holm_adjust(self):
        adj = F.holm_adjust({"a": .01, "b": .04, "c": .03})
        self.assertAlmostEqual(adj["a"], .03)
        self.assertAlmostEqual(adj["c"], .06)
        self.assertAlmostEqual(adj["b"], .06)

    def test_pooled(self):
        d, z, n = F.pooled({1: {"d": .02, "se": .01}, 2: {"d": .01, "se": .01}, 3: None})
        self.assertAlmostEqual(d, .03)
        self.assertAlmostEqual(z, .03 / np.sqrt(2e-4))
        self.assertEqual(n, 2)

    def test_majority(self):
        self.assertEqual([F.majority(n) for n in (2, 4, 5)], [2, 3, 3])

    def test_conditions(self):
        r = lambda d, se, b50, f50: {"d": d, "se": se, "base": {"top50": b50}, "fam": {"top50": f50}}
        c = F.conditions({1: r(.02, .01, .1, .1), 2: r(-.01, .01, .1, .1), 3: r(.03, .01, .1, .1)}, "soon")
        self.assertTrue(c["majority"])
        self.assertFalse(c["harmed"])
        c = F.conditions({1: r(.05, .01, .1, .1), 2: r(-.03, .01, .1, .1)}, "rating")
        self.assertFalse(c["majority"])
        self.assertTrue(c["harmed"])


class TestShuffle(unittest.TestCase):
    def test_block_shuffle_stays_within_fv_grade(self):
        ps = [{"fv_grade": g, "x": {"fv": g, "a": i, "b": 10 * i}} for i, g in enumerate([45, 45, 45, 50, 50])]
        out = F.shuffled({2021: ps}, ["a", "b"], np.random.default_rng(1))[2021]
        for p in out:
            self.assertEqual(p["x"]["b"], 10 * p["x"]["a"])          # the block moves together
        self.assertEqual(sorted(p["x"]["a"] for p in out[:3]), [0, 1, 2])
        self.assertEqual(sorted(p["x"]["a"] for p in out[3:]), [3, 4])
        self.assertEqual([p["x"]["fv"] for p in out], [45, 45, 45, 50, 50])
        self.assertEqual([p["x"]["a"] for p in ps], [0, 1, 2, 3, 4])   # input untouched


class TestStatcastAndMap(unittest.TestCase):
    def test_partial_spearman(self):
        rng = np.random.default_rng(0)
        z = rng.normal(size=200)
        x = rng.normal(size=200)
        self.assertAlmostEqual(F.partial_spearman(x, x, z), 1.0)
        self.assertAlmostEqual(F.partial_spearman(z, x, z), 0.0, places=9)

    def test_fv_bucket_and_bins(self):
        self.assertEqual([F.fv_bucket(g) for g in (37.5, 42.5, 47.5, 55, 70)], [40, 40, 45, 55, 60])
        self.assertEqual([F.gbin(g) for g in (40, 45, 50, 52.5)], ["<=40", "45-50", "45-50", ">50"])

    def test_residuals_within_class_and_bucket(self):
        ps = [{"cls": 2021, "fv_grade": 50, "y": 1.0}, {"cls": 2021, "fv_grade": 50, "y": 0.0},
              {"cls": 2022, "fv_grade": 50, "y": 1.0}]
        self.assertEqual(F.residuals(ps), [0.5, -0.5, 0.0])

    def test_gb_z(self):
        rows = [{"player_id": i, "season": 2023, "sport_id": 11, "league": "PCL", "ip": 50.0, "go": g, "ao": 100 - g}
                for i, g in enumerate((30, 50, 70))]
        z = F.gb_z(rows)
        self.assertAlmostEqual(sum(z.values()), 0.0, places=9)
        self.assertGreater(z[(2, 2023, 11)], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run:** `python -m pytest tests/test_fvplus.py -q`. Expected: collection error (`psmodel.fvplus` missing).

- [ ] **Step 3: Write `psmodel/fvplus.py`**

```python
"""FV+ (spec docs/superpowers/specs/2026-09-30-fv-plus-design.md, Amendment A).

FanGraphs' FV is the base; FV+ adds the pre-registered 4x4 adjustments in ONE
regularized model per player type and output (ridge for rating, logit for soon),
fit strictly as-of and tested walk-forward against FV alone. The groups, grades,
thresholds and rules here are the spec's, fixed before any result.
"""
import warnings

import numpy as np
from scipy.stats import norm, rankdata
from sklearn.linear_model import LogisticRegressionCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import asof, evaluate
from . import consensus as C
from . import features as FT
from . import walkforward as W

PREMIUM = frozenset({"C", "SS", "CF"})
NO_PITCH = 20.0
MIN_TRAIN_PLAYERS = 300
MIN_TRAIN_SUCCESSES = 30
N_SHUFFLE = 200
SHUFFLE_PCT = 95.0
HOLM_ALPHA = 0.05
MIN_IP = 30.0
QUEUE_MIN_N = 20

_RW = ["hit", "gpwr", "spd", "prem", "bb"]
_SH = ["fb", "brk", "ch", "cmd", "fb_x_cmd", "fb_x_brk", "rel"]
_PX = ["is_aaa", "is_aa", "is_higha", "age_rel"]
GROUPS = {
    ("H", "rating"): {"RW": _RW, "UP": ["age_rel", "raw_gap"], "OP": ["opp"], "SM": ["sm"]},
    ("H", "soon"): {"RW": _RW, "OP": ["opp"], "PX": _PX, "SM": ["sm"]},
    ("P", "rating"): {"SH": _SH, "GB": ["gb"], "OP": ["opp"], "SM": ["sm"]},
    ("P", "soon"): {"SH": _SH, "GB": ["gb"], "OP": ["opp"], "PX": _PX, "SM": ["sm"]},
}
# Expected weight signs from the spec's tables ('?' = no call).
EXPECTED = {
    ("H", "rating"): {"hit": "?", "gpwr": "+", "spd": "-", "prem": "?", "bb": "+", "age_rel": "-",
                      "raw_gap": "+", "opp": "-", "sm": "+"},
    ("H", "soon"): {"hit": "?", "gpwr": "+", "spd": "-", "prem": "?", "bb": "+", "opp": "-",
                    "is_aaa": "+", "is_aa": "+", "is_higha": "+", "age_rel": "+", "sm": "+"},
    ("P", "rating"): {"fb": "?", "brk": "+", "ch": "?", "cmd": "?", "fb_x_cmd": "?", "fb_x_brk": "?",
                      "rel": "?", "gb": "+", "opp": "-", "sm": "+"},
    ("P", "soon"): {"fb": "?", "brk": "+", "ch": "?", "cmd": "?", "fb_x_cmd": "?", "fb_x_brk": "?",
                    "rel": "+", "gb": "+", "opp": "-", "is_aaa": "+", "is_aa": "+", "is_higha": "+",
                    "age_rel": "+", "sm": "+"},
}
GRADE_KEYS = {"H": ("hit_fut", "pwr_fut", "raw_pwr_fut", "spd_fut"), "P": ("fb_fut", "cmd_fut")}


def keys(typ, target, drop=None):
    out = []
    for g, ks in GROUPS[(typ, target)].items():
        if g != drop:
            out += [k for k in ks if k not in out]
    return out


def medians(board, typ):
    """The list's median future grade for each tool imputed when blank."""
    out = {}
    for k in GRADE_KEYS[typ]:
        vals = [e[k] for e in board if e.get(k) is not None]
        out[k] = float(np.median(vals)) if vals else 50.0
    return out


def features(typ, e, r, med, opp, gb=None):
    """Adjustments for one graded player. e = Board entry (consensus.load_board),
    r = his model row for the class season, med = medians(that list), opp = the
    parent club's win% that season, gb = ground-ball z (pitchers)."""
    f = r["f"]
    x = {"fv": C.fv_score(e), "age_rel": f.get("age"), "opp": opp,
         "is_aaa": f.get("is_aaa"), "is_aa": f.get("is_aa"), "is_higha": f.get("is_higha")}
    if typ == "H":
        g = {k: med[k] if e.get(k) is None else e[k] for k in GRADE_KEYS["H"]}
        x.update(hit=g["hit_fut"], gpwr=g["pwr_fut"], spd=g["spd_fut"], raw_gap=g["raw_pwr_fut"] - g["pwr_fut"],
                 prem=1.0 if e.get("pos") in PREMIUM else 0.0, bb=f.get("bb"))
    else:
        fb = med["fb_fut"] if e.get("fb_fut") is None else e["fb_fut"]
        cmd = med["cmd_fut"] if e.get("cmd_fut") is None else e["cmd_fut"]
        brk = max([g for g in (e.get("sl_fut"), e.get("cb_fut")) if g is not None], default=NO_PITCH)
        ch = NO_PITCH if e.get("ch_fut") is None else e["ch_fut"]
        ss = r.get("start_share")
        x.update(fb=fb, brk=brk, ch=ch, cmd=cmd, fb_x_cmd=(fb - 50) * (cmd - 50) / 10,
                 fb_x_brk=(fb - 50) * (brk - 50) / 10, rel=None if ss is None else float(ss < 0.5), gb=gb)
    return x


def gb_z(raw_rows):
    """{(player_id, season, sport_id): ground-out share z within level-season-league}, 30+ IP rows."""
    rows = []
    for r in raw_rows:
        if r["ip"] < MIN_IP:
            continue
        outs = (r.get("go") or 0) + (r.get("ao") or 0)
        rows.append({"sport_id": r["sport_id"], "season": r["season"], "league": r.get("league"),
                     "key": (r["player_id"], r["season"], r["sport_id"]),
                     "f": {"gb": r["go"] / outs if outs else None}})
    FT.standardize_within_league(rows, ["gb"])
    return {r["key"]: r["f"]["gb"] for r in rows}


def matrix(players, cols, fill=None):
    X = np.array([[np.nan if p["x"].get(k) is None else float(p["x"][k]) for k in cols] for p in players],
                 dtype=float)
    if fill is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fill = np.nan_to_num(np.nanmean(X, axis=0))
    r, c = np.where(np.isnan(X))
    X[r, c] = fill[c]
    return X, fill


def _model(target):
    if target == "rating":
        return evaluate._model("ridge")
    return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=10, scoring="neg_log_loss", max_iter=2000))


def fit(train, cols, target):
    X, fill = matrix(train, cols)
    return _model(target).fit(X, np.array([p["y"] for p in train], dtype=float)), fill


def predict(model, fill, test, cols, target):
    X, _ = matrix(test, cols, fill)
    return model.predict_proba(X)[:, 1] if target == "soon" else model.predict(X)


def coefs(model):
    return np.ravel(model[-1].coef_)


def _split(classes, v, known, yfun):
    test = [dict(p, y=yfun(p)) for p in classes[v]]
    ids = {p["player_id"] for p in test}
    train = [dict(p, y=yfun(p)) for c, ps in classes.items() if c != v and known(c, v)
             for p in ps if p["player_id"] not in ids]
    return train, test


def split(classes, v, target, ctx):
    """(train, test) at test class v, strictly as-of, test players removed from training."""
    known = asof.rating_known if target == "rating" else asof.soon_known
    return _split(classes, v, known, lambda p: W._y(p["row"], target, ctx))


def trainable(train, target):
    if len(train) < MIN_TRAIN_PLAYERS:
        return False
    return target == "rating" or sum(p["y"] for p in train) >= MIN_TRAIN_SUCCESSES


def walk(classes, test_classes, target, cols, ctxs):
    """FV alone vs FV + cols at each test class: ({v: head_to_head | None}, {v: (test, pred)})."""
    res, preds = {}, {}
    full = ["fv"] + list(cols)
    for v in test_classes:
        train, test = split(classes, v, target, ctxs[v])
        if not trainable(train, target):
            res[v] = None
            continue
        m, fill = fit(train, full, target)
        p = predict(m, fill, test, full, target)
        preds[v] = (test, p)
        res[v] = C.head_to_head(test, C.pct([q["x"]["fv"] for q in test]), p, target, ctxs[v])
    return res, preds


def pooled(res):
    """(summed gain, pooled z, classes used) over {class: head_to_head | None}."""
    got = [r for r in res.values() if r is not None]
    d = float(sum(r["d"] for r in got))
    se = float(np.sqrt(sum(r["se"] ** 2 for r in got)))
    return d, (d / se if se > 0 else 0.0), len(got)


def p_two_sided(z):
    return float(2 * norm.sf(abs(z)))


def holm_adjust(p):
    """Holm step-down adjusted p-values for {name: p}."""
    out, run = {}, 0.0
    order = sorted(p, key=p.get)
    for i, k in enumerate(order):
        run = max(run, min(1.0, (len(order) - i) * p[k]))
        out[k] = run
    return out


def majority(n):
    return n // 2 + 1


def conditions(res, target):
    """Every adoption condition except Holm and the shuffle."""
    got = [r for r in res.values() if r is not None]
    pos = sum(1 for r in got if r["d"] > 0)
    t50 = float(np.mean([r["fam"]["top50"] - r["base"]["top50"] for r in got])) if got else 0.0
    return {"classes": len(got), "positive": pos, "majority": len(got) >= 2 and pos >= majority(len(got)),
            "harmed": any(W.z_score(r["d"], r["se"]) <= W.HARM_Z for r in got), "top50": t50,
            "top50_ok": target == "rating" or t50 >= -W.TOP50_TOLERANCE}


def shuffled(classes, cols, rng):
    """Copies with the cols block permuted jointly among players of the same FV grade, per class."""
    out = {}
    for c, ps in classes.items():
        by = {}
        for i, p in enumerate(ps):
            by.setdefault(p["fv_grade"], []).append(i)
        new = [dict(p, x=dict(p["x"])) for p in ps]
        for idx in by.values():
            for dst, src in zip(idx, rng.permutation(idx)):
                for k in cols:
                    new[dst]["x"][k] = ps[src]["x"][k]
        out[c] = new
    return out


def weights(train, cols, target, n_boot=200, seed=0):
    """{col: (standardized weight, 2.5%, 97.5%)} from a player bootstrap."""
    base = coefs(fit(train, cols, target)[0])
    pids = np.array([p["player_id"] for p in train])
    uniq = np.unique(pids)
    rows_of = {q: np.where(pids == q)[0] for q in uniq}
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        idx = np.concatenate([rows_of[q] for q in rng.choice(uniq, len(uniq))])
        sub = [train[i] for i in idx]
        if target == "soon" and len({p["y"] for p in sub}) < 2:
            continue
        boot.append(coefs(fit(sub, cols, target)[0]))
    lo, hi = np.percentile(np.array(boot), [2.5, 97.5], axis=0)
    return {k: (float(b), float(l), float(h)) for k, b, l, h in zip(cols, base, lo, hi)}


def partial_spearman(x, y, z):
    """Spearman of x and y with z's ranks regressed out of both (ties averaged)."""
    rx, ry, rz = (rankdata(a) for a in (x, y, z))
    A = np.column_stack([np.ones(len(rz)), rz])

    def resid(a):
        return a - A @ np.linalg.lstsq(A, a, rcond=None)[0]

    ex, ey = resid(rx), resid(ry)
    den = np.sqrt((ex @ ex) * (ey @ ey))
    return float(ex @ ey / den) if den > 0 else 0.0


def partial_ci(x, y, z, n_boot=300, seed=0):
    """(partial Spearman, bootstrap SE) over players (one row each)."""
    x, y, z = (np.asarray(a, dtype=float) for a in (x, y, z))
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        if len(set(y[i])) < 2 or len(set(x[i])) < 2:
            continue
        boot.append(partial_spearman(x[i], y[i], z[i]))
    return partial_spearman(x, y, z), float(np.std(boot)) if boot else 0.0


def fv_bucket(fv_grade):
    return int(min(60, max(40, 5 * np.floor(fv_grade / 5))))


def gbin(g):
    return "<=40" if g <= 40 else ("45-50" if g <= 50 else ">50")


def residuals(players):
    """y minus the mean y of the same class and FV bucket."""
    groups = {}
    for p in players:
        groups.setdefault((p["cls"], fv_bucket(p["fv_grade"])), []).append(p["y"])
    means = {g: float(np.mean(v)) for g, v in groups.items()}
    return [p["y"] - means[(p["cls"], fv_bucket(p["fv_grade"]))] for p in players]


def cell(values, n_boot=500, seed=0):
    """(mean, 2.5%, 97.5%, n) of one map cell's residuals; None if empty."""
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return None
    rng = np.random.default_rng(seed)
    boot = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(a.mean()), float(lo), float(hi), len(a)


def queued(c):
    return c is not None and c[3] >= QUEUE_MIN_N and (c[1] > 0 or c[2] < 0)
```

- [ ] **Step 4: Run** `python -m pytest tests/test_fvplus.py -q`. Expected: all pass. Then run the full suite: `python -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add prospects-model/psmodel/fvplus.py prospects-model/tests/test_fvplus.py
git commit -m "feat(fv-plus): FV+ logic -- features, as-of walk-forward, pooling, Holm, block shuffle, partial Spearman, map cells

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The runner

**Files:**
- Create: `prospects-model/fvplus_run.py`

- [ ] **Step 1: Write `fvplus_run.py`**

```python
"""FV+ Phase 2 (spec 2026-09-30-fv-plus-design.md, Amendment A): does FanGraphs'
FV plus pre-registered 4x4 adjustments beat FV alone?

Phases, each checkpointed to cache/fvplus_<phase>.json (skipped on relaunch;
--force redoes all): omnibus, guard, shuffle, components, weights, statcast, map.
Then the report (cache/fvplus_report.txt) and verdict (cache/fvplus_verdict.json).

Usage:  python fvplus_run.py [--force]
Reads cached data, the Board exports (cache/fv/) and the cached MLB standings
(run fetch_standings.py first). No network.
"""
import argparse
import datetime
import json
import os
import warnings

import numpy as np

import consensus_gate as CG
from psmodel import asof, cohorts, context, dataset, milb, mlbteams, pcohorts, spray, statsapi, step1
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import stuff
from psmodel import stuff_layer as SL
from psmodel import tracking
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "fvplus_report.txt")
VERDICT = os.path.join(CACHE, "fvplus_verdict.json")
NOW = cohorts.CURRENT_SEASON
MODELS = [("H", "rating"), ("H", "soon"), ("P", "rating"), ("P", "soon")]
EXPECTED_TESTS = {("H", "rating"): [2021, 2022], ("P", "rating"): [2021, 2022],
                  ("H", "soon"): [2019, 2021, 2022, 2023, 2024], ("P", "soon"): [2021, 2022, 2023, 2024]}
FIRST_TEST = 2018                                   # classes 2016-17 (lists 2017-18) are thin: training only
STATCAST_CLASSES = {"rating": (2022,), "soon": (2022, 2023, 2024)}
SEED = 0
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


def mkey(m):
    return f"{m[0]}_{m[1]}"


class Data:
    """Everything the phases need, built once on first use."""

    def __init__(self):
        self.labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
        self.rows, self.history, self.dec, self.boards = {}, {}, {}, {}
        for typ in ("H", "P"):
            asof.attach_ranks(self.labels, typ)
        for typ, noun in (("H", "hitters"), ("P", "pitchers")):
            mlb = {pid: r for (pid, t), r in self.labels.items() if t == typ}
            if typ == "H":
                self.history[typ] = cohorts.mlb_pa_history()
                self.rows[typ] = cohorts.add_products(cohorts.build_rows(cohorts.load_milb(), self.history[typ], mlb))
            else:
                self.history[typ] = pcohorts.mlb_ip_history()
                raw = pcohorts.load_milb()
                self.gb = F.gb_z(raw)
                self.rows[typ] = pcohorts.add_products(pcohorts.build_rows(raw, self.history[typ], mlb))
            with open(os.path.join(CACHE, CG.TYPES[typ]["decisions"]), encoding="utf-8") as fh:
                self.dec[typ] = json.load(fh)
            self.boards[typ] = {y: C.load_board(C.board_path(FV_DIR, y, noun)) for y in range(2017, NOW + 1)
                                if os.path.exists(C.board_path(FV_DIR, y, noun))}
        self.class_seasons = [c for c in range(2016, NOW) if c in cohorts.MILB_SEASONS and c + 1 in self.boards["H"]]
        self.win = {c: mlbteams.win_pct(c) for c in self.class_seasons}
        self.ctx = {(typ, v): asof.ref_curve(self.labels, v, typ) for typ in ("H", "P")
                    for v in self.class_seasons + [NOW]}
        self.classes, self.classes_r, self.counts = {}, {}, {}
        for typ in ("H", "P"):
            for t in ("rating", "soon"):
                g, r = {}, {}
                for c in self.class_seasons:
                    g[c], r[c], self.counts[(typ, t, c)] = self._class(typ, t, c)
                self.classes[(typ, t)], self.classes_r[(typ, t)] = g, r

    def _sm(self, typ, t, c):
        dec = self.dec[typ][t]
        got = W.predictions(self.rows[typ], dec["keys"], t, dec["kind"], {c: self.ctx[(typ, c)]}, (c,),
                            unseal=c in W.SEALED)
        if c not in got:
            return {}
        test, pred = CG.one_per_player(*got[c])
        return {r["player_id"]: float(p) for r, p in zip(test, pred)}

    def _class(self, typ, t, c):
        """(graded players, restored graduates, counts) for class c: rows of season c, one per player."""
        best = {}
        for r in self.rows[typ]:
            if r["season"] == c and (r["player_id"] not in best or r["sport_id"] < best[r["player_id"]]["sport_id"]):
                best[r["player_id"]] = r
        test = list(best.values())
        boards = self.boards[typ]
        nxt = C.match(CG.people(test), boards[c + 1])
        prev = C.match(CG.people(test), boards[c]) if c in boards else None
        skip = nxt["age_rejected"] | {a["player_id"] for a in nxt["ambiguous"]}
        med_n = F.medians(boards[c + 1], typ)
        med_p = F.medians(boards[c], typ) if c in boards else None
        sm = self._sm(typ, t, c)
        graded, restored, missing = [], [], {}
        for r in test:
            pid = r["player_id"]
            if pid in nxt["matched"]:
                e, med, out = nxt["matched"][pid], med_n, graded
            elif pid in skip:
                continue
            elif prev and pid in prev["matched"] and self.history[typ].get(pid, {}).get(c + 1, 0) >= CG.TYPES[typ]["graduate"]:
                e, med, out = prev["matched"][pid], med_p, restored
            else:
                continue
            for k in F.GRADE_KEYS[typ]:
                missing[k] = missing.get(k, 0) + (e.get(k) is None)
            gb = self.gb.get((pid, c, r["sport_id"])) if typ == "P" else None
            x = F.features(typ, e, r, med, self.win[c].get(mlbteams.team_of(e["org"])[0]), gb)
            out.append({"player_id": pid, "name": r["name"], "typ": typ, "cls": c, "fv_grade": e["fv"],
                        "x": x, "row": r, "sm_raw": sm.get(pid)})
        guard = [dict(p, x=dict(p["x"])) for p in graded + restored]    # copies: sm percentile differs
        for group in (graded, guard):
            scored = [p for p in group if p["sm_raw"] is not None]
            pct = C.pct([p["sm_raw"] for p in scored]) if scored else []
            for p, q in zip(scored, pct):
                p["x"]["sm"] = float(q)
        counts = {"graded": len(graded), "restored": len(restored), "missing_grades": missing}
        return graded, guard, counts

    def ctxs(self, typ):
        return {v: self.ctx[(typ, v)] for v in self.class_seasons}


def test_classes(d, m):
    """Test classes by the pre-registered rule; stops if they differ from Amendment A's list."""
    typ, t = m
    known = asof.rating_known if t == "rating" else asof.soon_known
    out = []
    for v in d.class_seasons:
        if v < FIRST_TEST or not known(v, NOW):
            continue
        train, _ = F.split(d.classes[m], v, t, d.ctx[(typ, v)])
        if F.trainable(train, t):
            out.append(v)
    if out != EXPECTED_TESTS[m]:
        raise SystemExit(f"{m}: the rule gives test classes {out}, Amendment A says {EXPECTED_TESTS[m]} -- stop")
    return out


def summary(res):
    if res is None:
        return None
    return {"fv": res["base"], "fvplus": res["fam"], "d": res["d"], "se": res["se"], "z": W.z_score(res["d"], res["se"])}


def phase_omnibus(d, classes_attr="classes"):
    out = {}
    for m in MODELS:
        typ, t = m
        res, _ = F.walk(getattr(d, classes_attr)[m], test_classes(d, m), t, F.keys(typ, t), d.ctxs(typ))
        dsum, z, n = F.pooled(res)
        out[mkey(m)] = {"classes": {str(v): summary(r) for v, r in res.items()}, "d": dsum, "z": z, "n": n,
                        "p": F.p_two_sided(z), "conditions": F.conditions(res, t)}
    return out


def phase_shuffle(d):
    out = {}
    for m in MODELS:
        typ, t = m
        cols, tests, rng = F.keys(typ, t), test_classes(d, m), np.random.default_rng(SEED)
        null = []
        for i in range(F.N_SHUFFLE):
            res, _ = F.walk(F.shuffled(d.classes[m], cols, rng), tests, t, cols, d.ctxs(typ))
            null.append(F.pooled(res)[0])
            if (i + 1) % 50 == 0:
                print(f"  shuffle {mkey(m)} {i + 1}/{F.N_SHUFFLE}", flush=True)
        out[mkey(m)] = null
    return out


def phase_components(d):
    out = {}
    for m in MODELS:
        typ, t = m
        tests = test_classes(d, m)
        _, full = F.walk(d.classes[m], tests, t, F.keys(typ, t), d.ctxs(typ))
        out[mkey(m)] = {}
        for g in F.GROUPS[m]:
            _, dropped = F.walk(d.classes[m], tests, t, F.keys(typ, t, drop=g), d.ctxs(typ))
            res = {v: C.head_to_head(full[v][0], dropped[v][1], full[v][1], t, d.ctx[(typ, v)])
                   for v in full if v in dropped}
            dsum, z, n = F.pooled(res)
            out[mkey(m)][g] = {"d": dsum, "z": z, "n": n}
    return out


def phase_weights(d):
    out = {}
    for m in MODELS:
        typ, t = m
        known = asof.rating_known if t == "rating" else asof.soon_known
        ctx = d.ctx[(typ, NOW)]
        train = [dict(p, y=W._y(p["row"], t, ctx)) for c, ps in d.classes[m].items() if known(c, NOW) for p in ps]
        out[mkey(m)] = F.weights(train, ["fv"] + F.keys(typ, t), t)
    return out


def _stuff_scores():
    sc = json.load(open(os.path.join(CACHE, "stuff_choice.json"), encoding="utf-8"))
    s_keys, s_kind = sc["score_keys"], sc["kind"]
    sv_mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    sv_aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB) for s in range(2015, stuff.LAST_OUTCOME_SEASON + 1)}
    mlb_stats = {(r["player_id"], s): r for s, rs in by_season.items() for r in rs}
    values = stuff.season_values(by_season, den)
    aaa_stats = {(r["player_id"], s): r for s in (2022, 2023, 2024) for r in milb.season_rows(s, statsapi.AAA, "pitching")}
    out = {}
    for c in (2022, 2023, 2024):
        model = SL.stuff_model(c, sv_mlb, values, mlb_stats, s_keys, s_kind)
        off = SL.offsets(c, sv_aaa, sv_mlb, [k for k in s_keys if k != "age"])
        out.update(SL.aaa_scores(sv_aaa, aaa_stats, model, off, s_keys, {c}))
    return out


def phase_statcast(d):
    """Per-player measures and the provisional partial-Spearman tests (no fitting)."""
    aaa = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    measures = {"pull_air": {}, "ev_low_air": {}, "ev": {}, "stuff": {}}
    for c in (2022, 2023, 2024):
        for pid, (rate, n) in spray.pulled_air(tracking.season_events(c, statsapi.AAA)).items():
            if n >= 100:
                measures["pull_air"][f"{pid}|{c}"] = rate
        pool = [(pid, r) for (pid, s), r in aaa.items() if s == c and (r.get("bbe") or 0) >= 100
                and r.get("avg_best_speed") is not None and r.get("linedrives_percent") is not None
                and r.get("flyballs_percent") is not None]
        ev = np.array([r["avg_best_speed"] for _, r in pool])
        air = np.array([r["linedrives_percent"] + r["flyballs_percent"] for _, r in pool])
        ev_hi, air_lo = np.percentile(ev, 200 / 3), np.percentile(air, 100 / 3)
        for (pid, r), e, a in zip(pool, ev, air):
            measures["ev_low_air"][f"{pid}|{c}"] = float(e >= ev_hi and a <= air_lo)
            measures["ev"][f"{pid}|{c}"] = float(e)
    measures["stuff"] = {f"{pid}|{s}": float(v) for (pid, s), v in _stuff_scores().items()}
    tests = {}
    for name, typ, meas in (("S-PA", "H", "pull_air"), ("S-EV", "H", "ev_low_air"), ("S-ST", "P", "stuff")):
        for t in ("rating", "soon"):
            per = {}
            for c in STATCAST_CLASSES[t]:
                ctx = d.ctx[(typ, c)]
                ps = [p for p in d.classes[(typ, t)][c]
                      if p["row"]["sport_id"] == statsapi.AAA and f"{p['player_id']}|{c}" in measures[meas]]
                if len(ps) < C.MIN_H2H:
                    per[str(c)] = None
                    continue
                y = [W._y(p["row"], t, ctx) for p in ps]
                if t == "soon" and len(set(y)) < 2:
                    per[str(c)] = None
                    continue
                x = [measures[meas][f"{p['player_id']}|{c}"] for p in ps]
                rho, se = F.partial_ci(x, y, [p["x"]["fv"] for p in ps])
                per[str(c)] = {"rho": rho, "se": se, "n": len(ps)}
            got = [v for v in per.values() if v is not None]
            s = float(sum(v["rho"] for v in got))
            se = float(np.sqrt(sum(v["se"] ** 2 for v in got)))
            z = s / se if se > 0 else 0.0
            tests[f"{name}_{t}"] = {"classes": per, "z": z, "p": F.p_two_sided(z), "n_classes": len(got)}
    return {"measures": measures, "tests": tests}


def phase_map(d, statcast):
    meas = statcast["measures"]
    out = {}
    for m in MODELS:
        typ, t = m
        known = asof.rating_known if t == "rating" else asof.soon_known
        ps = [dict(p, y=W._y(p["row"], t, d.ctx[(typ, c)])) for c, group in d.classes[m].items() if known(c, NOW)
              for p in group]
        res = F.residuals(ps)
        cells = {}

        def add(name, test):
            cells[name] = F.cell([r for p, r in zip(ps, res) if test(p)])

        if typ == "H":
            for k, get in (("hit", lambda x: x["hit"]), ("game_pwr", lambda x: x["gpwr"]),
                           ("raw_pwr", lambda x: x["raw_gap"] + x["gpwr"]), ("spd", lambda x: x["spd"])):
                for b in ("<=40", "45-50", ">50"):
                    add(f"{k} {b}", lambda p, get=get, b=b: F.gbin(get(p["x"])) == b)
            add("premium position", lambda p: p["x"]["prem"] == 1.0)
            add("other position", lambda p: p["x"]["prem"] == 0.0)
            for pa_hi in (True, False):
                for ev_hi in (True, False):
                    def test(p, pa_hi=pa_hi, ev_hi=ev_hi):
                        k = f"{p['player_id']}|{p['cls']}"
                        if k not in meas["pull_air"] or k not in meas["ev"]:
                            return False
                        pa_med = np.median([v for kk, v in meas["pull_air"].items() if kk.endswith(f"|{p['cls']}")])
                        ev_med = np.median([v for kk, v in meas["ev"].items() if kk.endswith(f"|{p['cls']}")])
                        return (meas["pull_air"][k] >= pa_med) == pa_hi and (meas["ev"][k] >= ev_med) == ev_hi
                    add(f"pulled air {'high' if pa_hi else 'low'} x EV {'high' if ev_hi else 'low'}", test)
        else:
            for k in ("fb", "brk", "ch", "cmd"):
                for b in ("<=40", "45-50", ">50"):
                    add(f"{k} {b}", lambda p, k=k, b=b: F.gbin(p["x"][k]) == b)
            names = ("fb", "brk", "ch", "cmd")
            for i, a in enumerate(names):
                for b_ in names[i + 1:]:
                    for ha in (True, False):
                        for hb in (True, False):
                            add(f"{a} {'high' if ha else 'low'} x {b_} {'high' if hb else 'low'}",
                                lambda p, a=a, b_=b_, ha=ha, hb=hb:
                                (p["x"][a] >= 55 if ha else p["x"][a] <= 45) and (p["x"][b_] >= 55 if hb else p["x"][b_] <= 45))
            add("profile: power arm", lambda p: p["x"]["fb"] >= 60 and p["x"]["cmd"] <= 40)
            add("profile: command artist", lambda p: p["x"]["cmd"] >= 55 and p["x"]["fb"] <= 50)
            add("profile: breaker-first", lambda p: p["x"]["brk"] >= 60 and p["x"]["fb"] <= 50)
            for st_hi in (True, False):
                for sec_hi in (True, False):
                    def test(p, st_hi=st_hi, sec_hi=sec_hi):
                        k = f"{p['player_id']}|{p['cls']}"
                        if k not in meas["stuff"]:
                            return False
                        st_med = np.median([v for kk, v in meas["stuff"].items() if kk.endswith(f"|{p['cls']}")])
                        sec = (p["x"]["cmd"] + max(p["x"]["brk"], p["x"]["ch"])) / 2
                        return (meas["stuff"][k] >= st_med) == st_hi and (sec >= 50) == sec_hi
                    add(f"stuff {'high' if st_hi else 'low'} x cmd+secondary {'high' if sec_hi else 'low'}", test)
        out[mkey(m)] = cells
    return out


def checkpoint(name, force, fn):
    path = os.path.join(CACHE, f"fvplus_{name}.json")
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


def fmt_res(r):
    if r is None:
        return "n/a"
    return (f"FV {r['fv']['rank']:.3f} t50 {r['fv']['top50']:.2f} | FV+ {r['fvplus']['rank']:.3f} "
            f"t50 {r['fvplus']['top50']:.2f} | gain {r['d']:+.4f} (z {r['z']:+.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every phase")
    force = ap.parse_args().force
    cache = {}

    def data():
        if "d" not in cache:
            print("building data ...", flush=True)
            cache["d"] = Data()
            with open(os.path.join(CACHE, "fvplus_counts.json"), "w", encoding="utf-8") as fh:
                json.dump({f"{k[0]}_{k[1]}_{k[2]}": v for k, v in cache["d"].counts.items()}, fh)
        return cache["d"]

    omni = checkpoint("omnibus", force, lambda: phase_omnibus(data()))
    guard = checkpoint("guard", force, lambda: phase_omnibus(data(), "classes_r"))
    null = checkpoint("shuffle", force, lambda: phase_shuffle(data()))
    comps = checkpoint("components", force, lambda: phase_components(data()))
    wts = checkpoint("weights", force, lambda: phase_weights(data()))
    stat = checkpoint("statcast", force, lambda: phase_statcast(data()))
    fmap = checkpoint("map", force, lambda: phase_map(data(), stat))
    with open(os.path.join(CACHE, "fvplus_counts.json"), encoding="utf-8") as fh:
        counts = json.load(fh)

    holm = F.holm_adjust({k: v["p"] for k, v in omni.items()})
    holm_g = F.holm_adjust({k: v["p"] for k, v in guard.items()})
    L = ["FV+ PHASE 2 -- does FV plus the pre-registered 4x4 adjustments beat FV alone?",
         "Spec 2026-09-30-fv-plus-design.md, Amendment A. Strict as-of walk-forward; gain = FV+ minus FV "
         "(Spearman for rating, AUC for soon) on the same graded players.", ""]
    L.append("0. Classes (graded / graduates restored; blank grades imputed):")
    for k, v in sorted(counts.items()):
        L.append(f"  {k}: graded {v['graded']}, restored {v['restored']}, blank grades {v['missing_grades']}")
    L.append("")
    verdict = {"generated": datetime.date.today().isoformat(), "models": {}}
    L.append("1. DECISION TESTS (one Holm family of 4)")
    for m in MODELS:
        k = mkey(m)
        o, g, c = omni[k], guard[k], omni[k]["conditions"]
        real, p95 = o["d"], float(np.percentile(null[k], F.SHUFFLE_PCT))
        gc = g["conditions"]
        main_ok = holm[k] < F.HOLM_ALPHA and c["majority"] and not c["harmed"] and c["top50_ok"] and real > p95
        guard_ok = holm_g[k] < F.HOLM_ALPHA and gc["majority"] and not gc["harmed"] and gc["top50_ok"]
        adopted = main_ok and guard_ok
        L.append(f"  {k}: adjustments {F.keys(*m)}")
        for v, r in o["classes"].items():
            L.append(f"    class {v} (list {int(v) + 1}): {fmt_res(r)}")
        L += [f"    pooled gain {o['d']:+.4f}, z {o['z']:+.2f}, p {o['p']:.4f}, Holm-adjusted p {holm[k]:.4f}",
              f"    majority {c['positive']}/{c['classes']} ({'ok' if c['majority'] else 'NO'}), "
              f"harm {'YES' if c['harmed'] else 'none'}, mean top-50 change {c['top50']:+.3f} "
              f"({'ok' if c['top50_ok'] else 'NO'}), shuffle 95th pct {p95:+.4f} vs real {real:+.4f} "
              f"({'ok' if real > p95 else 'NO'})",
              f"    guard (graduates restored): pooled gain {g['d']:+.4f}, z {g['z']:+.2f}, Holm p {holm_g[k]:.4f}, "
              f"majority {gc['positive']}/{gc['classes']}, harm {'YES' if gc['harmed'] else 'none'} "
              f"-> {'passes' if guard_ok else 'fails'}",
              f"    VERDICT {k}: {'ADOPT FV+' if adopted else 'FV stands'}", ""]
        verdict["models"][k] = {"adopted": adopted, "main_ok": main_ok, "guard_ok": guard_ok, "d": o["d"],
                                "z": o["z"], "holm_p": holm[k], "shuffle_p95": p95}
    L.append("2. COMPONENTS (explanation, not decision): pooled gain lost when the group is dropped")
    for m in MODELS:
        L.append(f"  {mkey(m)}: " + "; ".join(f"{g} {v['d']:+.4f} (z {v['z']:+.1f})" for g, v in comps[mkey(m)].items()))
    L += ["", "3. WEIGHTS (production fit on every answered class; standardized; 95% player bootstrap)"]
    for m in MODELS:
        L.append(f"  {mkey(m)}:")
        for col, (w, lo, hi) in wts[mkey(m)].items():
            exp = F.EXPECTED[m].get(col, "base")
            sig = "+" if lo > 0 else "-" if hi < 0 else "0"
            flag = "   SURPRISE (opposite to expected)" if exp in "+-" and sig in "+-" and sig != exp else ""
            L.append(f"    {col:9} {w:+.3f} [{lo:+.3f}, {hi:+.3f}]  expected {exp}{flag}")
    L += ["", "4. STATCAST GROUP -- PROVISIONAL (partial Spearman with the target, FV held fixed; decided after 2028)"]
    sh = F.holm_adjust({k: v["p"] for k, v in stat["tests"].items()})
    for k, v in stat["tests"].items():
        per = "; ".join(f"{c}: n/a" if r is None else f"{c}: {r['rho']:+.3f} (se {r['se']:.3f}, n {r['n']})"
                        for c, r in v["classes"].items())
        L.append(f"  {k}: {per} -> pooled z {v['z']:+.2f}, Holm p {sh[k]:.3f}")
    L += ["", "5. EXPLORATION MAP (descriptive; residual = outcome minus class-and-FV-bucket mean)"]
    queue = []
    for m in MODELS:
        L.append(f"  {mkey(m)}:")
        for name, cl in fmap[mkey(m)].items():
            if cl is None:
                L.append(f"    {name}: empty")
                continue
            q = F.queued(cl)
            L.append(f"    {name}: {cl[0]:+.3f} [{cl[1]:+.3f}, {cl[2]:+.3f}] n={cl[3]}" + ("   -> QUEUE" if q else ""))
            if q:
                queue.append(f"{mkey(m)}: {name} ({cl[0]:+.3f}, n={cl[3]})")
    L += ["", "6. CONFIRMATION QUEUE (pre-register for the 2025+ classes; nothing adopted now):"] + \
         [f"  - {q}" for q in queue or ["(empty)"]]
    verdict["queue"] = queue
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Import smoke test:** `python -c "import fvplus_run"`. Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add prospects-model/fvplus_run.py
git commit -m "feat(fv-plus): checkpointed FV+ runner -- omnibus, guard, shuffle, components, weights, Statcast group, map

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Run, review, record

- [ ] **Step 1:** Run `tasklist | grep -i python`. Expected: nothing unaccounted for.
- [ ] **Step 2: Run in the background:** `python fvplus_run.py`. It stops if the test classes differ from Amendment A's list; if so, bring that to the user. A crash is fixed and relaunched; completed phases are skipped.
- [ ] **Step 3: Opus review.**
  - Check the plumbing before reading any verdict:
    - class counts vs Amendment A;
    - blank-grade counts;
    - each class's FV rank accuracy against `consensus_*_report.txt`'s FV line for the same class. They must match exactly: same players, same FV order.
  - Then read the verdicts, components, weights (flagging surprises), the Statcast group, and the map and queue.
- [ ] **Step 4: Record.**
  - Write a "Phase 2 result" section in the spec.
  - Update the memory file.
  - Commit the spec.
  - Tell the user plainly what was adopted, what wasn't, and what that means for the page. The page change (FV+ columns and the pitcher tiebreaker lens) is a separate, next plan.
