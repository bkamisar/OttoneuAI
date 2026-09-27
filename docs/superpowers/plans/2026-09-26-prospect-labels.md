# Prospect Model, Sub-Project 1: Label Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every MLB player-season 2015–2026 as its value in this league's 4×4 scoring, and prove the Python math matches the JS engine exactly.

**Architecture:** A `prospects-model/` Python package. MLB StatsAPI supplies stats through a disk-cached, content-asserted fetch layer. Denominators and replacement levels are derived from a synthetic 12-team league built from one reference season and then held fixed, so labels are comparable across years. A parity harness feeds identical inputs to the Python SGP math and to `shared.js`'s `calcPlayerSGP` and requires agreement to 1e-9.

**Tech Stack:** Python 3.14.3 with **already-installed** packages only (numpy 2.4.3, pandas 3.0.1, scikit-learn 1.8.0, scipy 1.17.1, requests 2.33.1). Tests use stdlib `unittest` — no new dependency. Node is used only by the parity harness to run `shared.js`.

Spec: `docs/superpowers/specs/2026-09-26-prospect-model-design.md`

---

## Context the implementer needs

**League constants** (verified from `shared.js`):
`NUM_TEAMS = 12`, `HITTER_SLOTS` has **12** entries (C, 1B, 2B, SS, 3B, MI, OF1–OF5, UTIL),
`IP_MAX = 1500` per team, `PA_PER_SLOT = 650`, `SALARY_POOL = 4800`.
There is **no** `PITCHER_SLOTS` — pitchers are constrained by an innings budget,
so pitcher replacement is defined by cumulative innings (12 × 1500 = 18,000
league-wide), not by a slot count.

**The SGP formula to reproduce** (`shared.js` `calcPlayerSGP`), hitters:
```
paRatio = pa / repl.pa
sgp  = (HR  - repl.hr  * paRatio) / D_HR
     + (R   - repl.r   * paRatio) / D_R
     + (OBP - repl.obp) * pa / avgPA / D_OBP
     + (SLG - repl.slg) * pa / avgPA / D_SLG
```
pitchers:
```
ipScale = max(1, ip / repl.ip)          # never scales DOWN (load-bearing)
sgp  = (SO   - repl.so * ipScale) / D_SO
     + (repl.era  - ERA)  * ip / avgIP / D_ERA
     + (repl.whip - WHIP) * ip / avgIP / D_WHIP
     + (repl.hr9  - HR9)  * ip / avgIP / D_HR9
```

**Known simplification (document, don't hide):** labels use `calcPlayerSGP` with
the general replacement baseline, **not** `hitterSGP` with positional offsets.
Positional offsets need full-league position data per season and redistribute
value among hitters rather than changing the total. Recorded as a limitation.

**Why denominators are NOT harvested from the live tool** (measured 2026-09-26):
in late September the rest-of-season projections are nearly exhausted, so team
pitching totals compute to zero, `calcSGPDenoms` falls back to `1.0` for ERA /
WHIP / HR9 / SO, and hitter replacement collapses to **2.2 PA**. Any constant
taken from today's tool state would be garbage. Python derives its own from
actual full-season stats instead.

**StatsAPI quirks:**
- `inningsPitched` is baseball notation: `"62.2"` means 62⅔. Must convert
  (mirror `parseIPInnings` in `shared.js`).
- Rate stats arrive as strings, sometimes leading-dot (`".369"`). `float()`
  handles these; empty strings and `"-.--"` do not.
- Paginate with `limit`/`offset`; a page shorter than `limit` is the last.
- `playerPool=all` is required or you get only qualified players.

**Security posture** (from the spec): no new installs; pin observed versions for
reproducibility; raw pulls land in `cache/` and are gitignored; sanitize leading
`= + - @` in any CSV written for spreadsheets.

## Running the tests

```bash
cd prospects-model && python -m unittest discover -s tests -v
```
Network-touching tests are skipped unless `PROSPECTS_LIVE=1` is set, so the
default suite is offline and fast.

## File map

| File | Responsibility |
|---|---|
| `prospects-model/requirements.txt` | Pinned versions (documentation; nothing to install) |
| `prospects-model/.gitignore` | Excludes `cache/` |
| `prospects-model/psmodel/http.py` | Cached, throttled, asserted JSON/CSV fetch |
| `prospects-model/psmodel/statsapi.py` | Season-stat pulls, normalization, IP parsing |
| `prospects-model/psmodel/context.py` | Synthetic-league denominators + replacement levels |
| `prospects-model/psmodel/labels.py` | SGP math, per-season labels |
| `prospects-model/psmodel/targets.py` | Debut, window, peak, completeness, time-to-contribution |
| `prospects-model/parity/js_side.js` | Runs `shared.js` `calcPlayerSGP` on injected inputs |
| `prospects-model/parity/compare.py` | Asserts Python ≡ JS within 1e-9 |
| `prospects-model/tests/` | `unittest` suites |

---

### Task 1: Scaffold

**Files:**
- Create: `prospects-model/.gitignore`, `requirements.txt`, `psmodel/__init__.py`, `tests/__init__.py`, `README.md`

- [ ] **Step 1: Create the scaffold**

`prospects-model/.gitignore`:
```
cache/
__pycache__/
*.pyc
```

`prospects-model/requirements.txt`:
```
# Versions observed already installed on 2026-09-26. Pinned for reproducibility,
# NOT to be installed -- a silent upgrade could change model output.
numpy==2.4.3
pandas==3.0.1
scikit-learn==1.8.0
scipy==1.17.1
requests==2.33.1
# tests use stdlib unittest; no test dependency
```

`prospects-model/psmodel/__init__.py` and `prospects-model/tests/__init__.py`: empty files.

`prospects-model/README.md`:
```markdown
# Prospect Value Model

Predicts which minor-league traits produce value in this league's 4x4 scoring.
Design: `../docs/superpowers/specs/2026-09-26-prospect-model-design.md`

## Layout
- `psmodel/` — pipeline modules
- `parity/`  — proves the Python SGP math matches shared.js
- `tests/`   — `python -m unittest discover -s tests -v`
- `cache/`   — raw API pulls (gitignored; never committed)

## Sources
- **MLB StatsAPI** — canonical for all counting and rate stats.
- **Baseball Savant** — expected and tracking metrics ONLY. Never blended with
  StatsAPI for the same quantity (Soto 2026: 477 PA / .278 in StatsAPI vs
  472 / .276 in Savant, because Savant counts tracked PAs).
```

- [ ] **Step 2: Verify the layout**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: `Ran 0 tests` and `OK` — the package imports cleanly.

- [ ] **Step 3: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): scaffold the label pipeline

Python package for the prospect value model. Pins the already-installed
package versions for reproducibility rather than installing anything, so
a silent upgrade cannot change model output. Raw API pulls are cached to
a gitignored directory; only derived artifacts are ever committed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Cached, asserted fetch layer

**Files:**
- Create: `prospects-model/psmodel/http.py`, `prospects-model/tests/test_http.py`

- [ ] **Step 1: Write the failing test**

`prospects-model/tests/test_http.py`:
```python
import json, os, tempfile, unittest
from psmodel import http


class TestCacheKey(unittest.TestCase):
    def test_distinct_urls_get_distinct_paths(self):
        a = http.cache_path("https://x/y?a=1", ".json")
        b = http.cache_path("https://x/y?a=2", ".json")
        self.assertNotEqual(a, b)

    def test_same_url_is_stable(self):
        a = http.cache_path("https://x/y?a=1", ".json")
        b = http.cache_path("https://x/y?a=1", ".json")
        self.assertEqual(a, b)


class TestAssertions(unittest.TestCase):
    """The rule earned the hard way: assert on CONTENT, not HTTP status.
    Four endpoints in this project returned 200 with wrong or empty data."""

    def test_require_rows_rejects_empty(self):
        with self.assertRaises(http.DataError):
            http.require_rows([], "empty-case")

    def test_require_keys_rejects_missing(self):
        with self.assertRaises(http.DataError):
            http.require_keys([{"a": 1}], ["a", "b"], "missing-case")

    def test_require_keys_accepts_present(self):
        http.require_keys([{"a": 1, "b": 2}], ["a", "b"], "ok-case")


class TestCacheRoundTrip(unittest.TestCase):
    def test_write_then_read(self):
        with tempfile.TemporaryDirectory() as d:
            old = http.CACHE_DIR
            try:
                http.CACHE_DIR = d
                p = http.cache_path("https://example/test", ".json")
                http.cache_write(p, json.dumps({"hello": "world"}))
                self.assertEqual(json.loads(http.cache_read(p))["hello"], "world")
                self.assertIsNone(http.cache_read(os.path.join(d, "nope.json")))
            finally:
                http.CACHE_DIR = old


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: `ModuleNotFoundError: No module named 'psmodel.http'`

- [ ] **Step 3: Implement**

`prospects-model/psmodel/http.py`:
```python
"""Cached, throttled, content-asserted HTTP for first-party MLB sources.

Read-only, unauthenticated GETs to MLB-operated hosts. No credentials, no
cookies, no personal data in query strings.

The content assertions are the point of this module. Four endpoints in this
project returned HTTP 200 with data that was wrong or empty:
  - FanGraphs ZiPS `season=` silently ignored (identical rows for 2027/2028)
  - Savant `minors=true` a no-op (byte-identical output)
  - Savant `hfLevel=AAA` on the MLB path: 200, zero rows
  - `statcast-search-minors/csv`: 200, 4,215 rows, every team an MLB club
So: never trust a status code. Assert on what came back.
"""
import hashlib
import json
import os
import time
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
USER_AGENT = "Mozilla/5.0 (OttoneuAI prospect model; personal research)"
MIN_INTERVAL_S = 1.0          # be a good citizen; never hammer
_last_request_at = [0.0]


class DataError(Exception):
    """Returned payload failed a content assertion."""


def cache_path(url: str, suffix: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return os.path.join(CACHE_DIR, digest + suffix)


def cache_read(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return None


def cache_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _throttle() -> None:
    wait = MIN_INTERVAL_S - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.time()


def fetch_text(url: str, suffix: str = ".txt", attempts: int = 3) -> str:
    """GET with disk cache. Cached responses never re-hit the network."""
    path = cache_path(url, suffix)
    cached = cache_read(path)
    if cached is not None:
        return cached
    last = None
    for i in range(attempts):
        try:
            _throttle()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8-sig", errors="replace")
            cache_write(path, text)
            return text
        except Exception as exc:       # noqa: BLE001 - retry any transport error
            last = exc
            time.sleep(1.5 * (i + 1))
    raise DataError(f"fetch failed after {attempts} attempts: {url} ({last})")


def fetch_json(url: str):
    return json.loads(fetch_text(url, ".json"))


def require_rows(rows, label: str):
    """A payload that parsed but holds nothing is a failure, not an empty result."""
    if not rows:
        raise DataError(f"{label}: zero rows returned (HTTP status is not evidence)")
    return rows


def require_keys(rows, keys, label: str):
    missing = [k for k in keys if k not in rows[0]]
    if missing:
        raise DataError(f"{label}: payload missing expected keys {missing}")
    return rows


def require_value(actual, expected, label: str):
    """Guards silently-ignored parameters: assert the response reflects the request."""
    if str(actual) != str(expected):
        raise DataError(f"{label}: expected {expected!r} in payload, got {actual!r} "
                        "- parameter may be silently ignored")
    return actual
```

- [ ] **Step 4: Run the tests**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: 6 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): cached fetch layer with content assertions

Disk-cached, throttled, read-only GETs to MLB's own APIs. The assertions
are the real content: four endpoints in this project returned HTTP 200
with wrong or empty data (ZiPS season= ignored, Savant minors=true a
no-op, hfLevel=AAA giving zero rows, statcast-search-minors returning
MLB clubs). require_rows/require_keys/require_value make 'it returned
200' insufficient.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: StatsAPI season stats

**Files:**
- Create: `prospects-model/psmodel/statsapi.py`, `prospects-model/tests/test_statsapi.py`

- [ ] **Step 1: Write the failing test**

`prospects-model/tests/test_statsapi.py`:
```python
import os, unittest
from psmodel import statsapi


class TestInnings(unittest.TestCase):
    """Baseball notation: 62.2 means 62 and 2/3 innings, not 62.2."""

    def test_thirds(self):
        self.assertAlmostEqual(statsapi.parse_innings("62.2"), 62 + 2 / 3, places=9)
        self.assertAlmostEqual(statsapi.parse_innings("10.1"), 10 + 1 / 3, places=9)
        self.assertAlmostEqual(statsapi.parse_innings("7.0"), 7.0, places=9)

    def test_junk_is_zero(self):
        self.assertEqual(statsapi.parse_innings(""), 0.0)
        self.assertEqual(statsapi.parse_innings(None), 0.0)
        self.assertEqual(statsapi.parse_innings("-.--"), 0.0)


class TestNum(unittest.TestCase):
    def test_leading_dot(self):
        self.assertAlmostEqual(statsapi.num(".369"), 0.369, places=9)

    def test_junk(self):
        self.assertEqual(statsapi.num(""), 0.0)
        self.assertEqual(statsapi.num("-.--"), 0.0)
        self.assertEqual(statsapi.num(None), 0.0)


class TestNormalize(unittest.TestCase):
    def test_hitter_row(self):
        split = {
            "player": {"id": 665742, "fullName": "Juan Soto"},
            "team": {"name": "New York Mets"},
            "league": {"name": "NL"},
            "stat": {"age": 27, "plateAppearances": 477, "atBats": 395, "hits": 110,
                     "homeRuns": 27, "runs": 63, "baseOnBalls": 78, "strikeOuts": 65,
                     "obp": ".397", "slg": ".522"},
        }
        r = statsapi.normalize_hitter(split, 2026, 1)
        self.assertEqual(r["player_id"], 665742)
        self.assertEqual(r["pa"], 477)
        self.assertEqual(r["hr"], 27)
        self.assertAlmostEqual(r["obp"], 0.397, places=9)
        self.assertEqual(r["season"], 2026)
        self.assertEqual(r["sport_id"], 1)

    def test_pitcher_row_converts_innings(self):
        split = {
            "player": {"id": 663878, "fullName": "Nate Pearson"},
            "team": {"name": "New Hampshire Fisher Cats"},
            "league": {"name": "EAS"},
            "stat": {"age": 22, "inningsPitched": "62.2", "strikeOuts": 69,
                     "baseOnBalls": 21, "homeRuns": 4, "era": "2.59", "whip": "0.99",
                     "gamesStarted": 16, "gamesPlayed": 16},
        }
        r = statsapi.normalize_pitcher(split, 2019, 12)
        self.assertAlmostEqual(r["ip"], 62 + 2 / 3, places=9)
        self.assertEqual(r["so"], 69)
        self.assertAlmostEqual(r["era"], 2.59, places=9)
        # HR/9 is derived, not served
        self.assertAlmostEqual(r["hr9"], 4 * 9 / (62 + 2 / 3), places=6)

    def test_zero_innings_gives_zero_hr9(self):
        split = {"player": {"id": 1, "fullName": "x"}, "stat": {"inningsPitched": "0.0", "homeRuns": 0}}
        self.assertEqual(statsapi.normalize_pitcher(split, 2020, 1)["hr9"], 0.0)


@unittest.skipUnless(os.environ.get("PROSPECTS_LIVE") == "1", "set PROSPECTS_LIVE=1 for network tests")
class TestLive(unittest.TestCase):
    def test_known_line_matches_spot_check(self):
        """Soto 2026: 477 PA, 27 HR, .397 OBP -- user-verified 2026-09-26."""
        rows = statsapi.season_stats(2026, "hitting", 1)
        soto = [r for r in rows if r["player_id"] == 665742]
        self.assertEqual(len(soto), 1, "exactly one row per player-season-sport")
        self.assertEqual(soto[0]["pa"], 477)
        self.assertEqual(soto[0]["hr"], 27)

    def test_multi_level_season_is_two_rows(self):
        """Witt Jr. 2021: 279 PA at AA and 285 at AAA. Both must survive."""
        aa = [r for r in statsapi.season_stats(2021, "hitting", 12) if r["player_id"] == 677951]
        aaa = [r for r in statsapi.season_stats(2021, "hitting", 11) if r["player_id"] == 677951]
        self.assertEqual(aa[0]["pa"], 279)
        self.assertEqual(aaa[0]["pa"], 285)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: `ModuleNotFoundError: No module named 'psmodel.statsapi'`

- [ ] **Step 3: Implement**

`prospects-model/psmodel/statsapi.py`:
```python
"""MLB StatsAPI season stats — the canonical source for counting and rate stats.

sportId: 1 = MLB, 11 = AAA, 12 = AA, 13 = High-A, 14 = Single-A.
The player id is the SAME across levels, so MiLB->MLB is an exact join. This
matters: a name-substring search for "Witt" during design matched Jantzen
Witte, a 31-year-old in Tacoma, not Bobby Witt Jr.
"""
from . import http

BASE = "https://statsapi.mlb.com/api/v1/stats"
PAGE = 1000

MLB, AAA, AA, HIGH_A, SINGLE_A = 1, 11, 12, 13, 14
MILB_SPORT_IDS = (AAA, AA, HIGH_A, SINGLE_A)


def num(v) -> float:
    """StatsAPI rate stats arrive as strings, sometimes leading-dot ('.369')."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_innings(v) -> float:
    """'62.2' is 62 and 2/3 innings. Mirrors parseIPInnings in shared.js."""
    f = num(v)
    whole = int(f)
    outs = round((f - whole) * 10)
    return whole + outs / 3.0


def _common(split, season, sport_id):
    player = split.get("player", {}) or {}
    return {
        "player_id": player.get("id"),
        "name": player.get("fullName"),
        "season": season,
        "sport_id": sport_id,
        "team": (split.get("team") or {}).get("name"),
        "league": (split.get("league") or {}).get("name"),
        "age": split.get("stat", {}).get("age"),
    }


def normalize_hitter(split, season, sport_id):
    st = split.get("stat", {}) or {}
    row = _common(split, season, sport_id)
    row.update({
        "g": int(num(st.get("gamesPlayed"))),
        "pa": int(num(st.get("plateAppearances"))),
        "ab": int(num(st.get("atBats"))),
        "h": int(num(st.get("hits"))),
        "hr": int(num(st.get("homeRuns"))),
        "r": int(num(st.get("runs"))),
        "bb": int(num(st.get("baseOnBalls"))),
        "so": int(num(st.get("strikeOuts"))),
        "sb": int(num(st.get("stolenBases"))),
        "obp": num(st.get("obp")),
        "slg": num(st.get("slg")),
    })
    return row


def normalize_pitcher(split, season, sport_id):
    st = split.get("stat", {}) or {}
    ip = parse_innings(st.get("inningsPitched"))
    hr = int(num(st.get("homeRuns")))
    row = _common(split, season, sport_id)
    row.update({
        "g": int(num(st.get("gamesPlayed"))),
        "gs": int(num(st.get("gamesStarted"))),
        "ip": ip,
        "so": int(num(st.get("strikeOuts"))),
        "bb": int(num(st.get("baseOnBalls"))),
        "hr": hr,
        "era": num(st.get("era")),
        "whip": num(st.get("whip")),
        # HR/9 is a scored category but not served; derive it.
        "hr9": (hr * 9.0 / ip) if ip > 0 else 0.0,
    })
    return row


def season_stats(season: int, group: str, sport_id: int):
    """All player-seasons for one season/group/level. group is 'hitting'|'pitching'."""
    normalize = normalize_hitter if group == "hitting" else normalize_pitcher
    out, offset = [], 0
    while True:
        url = (f"{BASE}?stats=season&season={season}&group={group}"
               f"&sportId={sport_id}&limit={PAGE}&offset={offset}&playerPool=all")
        payload = http.fetch_json(url)
        stats = payload.get("stats") or []
        if not stats:
            break
        splits = stats[0].get("splits") or []
        if offset == 0:
            http.require_rows(splits, f"statsapi {season}/{group}/sport{sport_id}")
            http.require_keys(splits, ["player", "stat"],
                              f"statsapi {season}/{group}/sport{sport_id}")
        for s in splits:
            row = normalize(s, season, sport_id)
            if row["player_id"] is not None:
                out.append(row)
        if len(splits) < PAGE:
            break
        offset += PAGE
    return out
```

- [ ] **Step 4: Run the tests (offline, then live)**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: 13 tests, `OK` (live tests skipped).

Run: `cd prospects-model && PROSPECTS_LIVE=1 python -m unittest tests.test_statsapi -v`
Expected: 9 tests, `OK`. Soto 2026 = 477 PA / 27 HR, Witt Jr. 2021 = 279 PA at AA and 285 at AAA.

- [ ] **Step 5: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): StatsAPI season stats with exact-ID joins

Normalizes hitter and pitcher season lines for MLB and every minor-league
level. Two details that would silently corrupt labels: innings arrive in
baseball notation (62.2 is 62 and 2/3), and HR/9 is a scored category
StatsAPI does not serve, so it is derived from HR and IP.

Live tests assert the user-verified spot checks: Soto 2026 at 477 PA /
27 HR, and Witt Jr. 2021 as TWO rows (279 PA at AA, 285 at AAA) because
multi-level seasons must never be deduplicated.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Synthetic-league denominators and replacement levels

> **DEVIATION (built 2026-09-26): denominators come from the REAL league spread in
> `standings.csv`, not a synthetic league. The code below for `assign_teams` /
> `build_denominators` is superseded — see `prospects-model/psmodel/context.py`
> (`denominators_from_standings`, `load_league_denominators`).**
> Executing this task, the test for the snaked-team version failed with
> `HR: degenerate denominator 0.0`, which exposed the flaw: snaking builds
> artificially balanced teams. Measured against the real spread, snaking
> under-estimated it by roughly half and random assignment by 7-36%; a real
> league is more spread out than any mechanical draw. The spec had asked for
> "this league's current values" all along. Replacement-level and `league_averages`
> below are built as written.

**Files:**
- Create: `prospects-model/psmodel/context.py`, `prospects-model/tests/test_context.py`

- [ ] **Step 1: Write the failing test**

`prospects-model/tests/test_context.py`:
```python
import unittest
from psmodel import context


def hitters(n, base_hr=20):
    """n synthetic hitters, DESCENDING quality (player 1 is best)."""
    return [{"player_id": i, "pa": 600, "ab": 540, "hr": base_hr + (n - i) // 3,
             "r": 70 + (n - i) // 3, "obp": 0.400 - i * 0.0003,
             "slg": 0.560 - i * 0.0005} for i in range(1, n + 1)]


def pitchers(n):
    return [{"player_id": i, "ip": 180.0, "so": 220 - i // 2, "bb": 50, "hr": 18,
             "era": 3.0 + i * 0.008, "whip": 1.05 + i * 0.0015,
             "hr9": 0.9 + i * 0.0015} for i in range(1, n + 1)]


class TestDenominators(unittest.TestCase):
    def test_all_categories_positive_and_finite(self):
        d = context.build_denominators(hitters(300), pitchers(250))
        for cat in ("HR", "R", "OBP", "SLG", "SO", "ERA", "WHIP", "HR9"):
            self.assertIn(cat, d)
            self.assertGreater(d[cat], 0.0, f"{cat} denominator must be > 0")
            self.assertTrue(d[cat] == d[cat], f"{cat} denominator is NaN")

    def test_never_falls_back_to_one(self):
        """The live JS tool returned 1.0 for every pitching denominator in
        September because RoS projections were exhausted. A denominator of
        exactly 1.0 for a rate category means the computation collapsed."""
        d = context.build_denominators(hitters(300), pitchers(250))
        for cat in ("ERA", "WHIP", "HR9"):
            self.assertNotEqual(d[cat], 1.0, f"{cat} looks like the collapse fallback")


class TestReplacement(unittest.TestCase):
    def test_hitter_replacement_is_a_real_regular(self):
        """Must look like an actual player -- not the 2.2 PA the live tool
        produced from exhausted September projections."""
        repl = context.hitter_replacement(hitters(400))
        self.assertGreater(repl["pa"], 100)
        self.assertGreater(repl["obp"], 0.200)
        self.assertLess(repl["obp"], 0.400)

    def test_replacement_sits_past_everyone_rostered(self):
        """Mirrors computeFABaselines' future branch: skip ROSTERED_H, then take
        the next FA_COHORT_H. Skipping only the 144 starting slots would set
        replacement far too high."""
        pool = hitters(400)
        repl = context.hitter_replacement(pool)
        ranked = sorted(pool, key=lambda r: r["pa"] * (r["obp"] + r["slg"]), reverse=True)
        expected = ranked[context.ROSTERED_H:context.ROSTERED_H + context.FA_COHORT_H]
        self.assertAlmostEqual(repl["obp"],
                               sum(r["obp"] for r in expected) / len(expected), places=9)
        # and it is worse than the starters
        starters = ranked[:context.STARTING_HITTERS]
        self.assertLess(repl["obp"] + repl["slg"],
                        sum(r["obp"] + r["slg"] for r in starters) / len(starters))

    def test_volume_floor_excludes_tiny_samples(self):
        """FA_MIN_PA keeps a 12-PA hot streak out of the replacement cohort."""
        pool = hitters(400)
        pool.append({"player_id": 9999, "pa": 12, "ab": 10, "hr": 4, "r": 6,
                     "obp": 0.900, "slg": 1.800})
        repl = context.hitter_replacement(pool)
        self.assertLess(repl["obp"], 0.500)

    def test_pitcher_replacement_uses_rostered_count_and_floor(self):
        repl = context.pitcher_replacement(pitchers(300))
        self.assertGreaterEqual(repl["ip"], context.FA_MIN_IP)
        self.assertGreater(repl["era"], 0.0)

    def test_too_small_a_pool_raises(self):
        with self.assertRaises(ValueError):
            context.hitter_replacement(hitters(10))


class TestLeagueAverages(unittest.TestCase):
    def test_avg_pa_is_per_team_starters_not_league_wide(self):
        """144 starters at 600 PA is 86,400 league PA; per team that is 7,200.
        League-wide/12 over a 300-player pool would give 15,000 -- roughly
        double -- and would halve the weight of OBP and SLG."""
        avg_pa, avg_ip = context.league_averages(hitters(300), pitchers(250))
        self.assertAlmostEqual(avg_pa, 144 * 600 / 12, places=6)
        self.assertAlmostEqual(avg_ip, 1500.0, places=6)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Expected: `ModuleNotFoundError: No module named 'psmodel.context'`

- [ ] **Step 3: Implement**

`prospects-model/psmodel/context.py`:
```python
"""Synthetic-league denominators and replacement levels.

Why these are computed here rather than read from the JS tool: measured
2026-09-26, the live tool's rest-of-season projections were nearly exhausted,
so every pitching denominator fell back to 1.0 and hitter replacement collapsed
to 2.2 PA. Constants taken from that state would be meaningless.

Denominators are built ONCE from a reference season and then held FIXED across
all label years; replacement level is recomputed PER SEASON. Fixed denominators
plus per-season replacement is what makes 2019 and 2024 comparable -- era
inflation is absorbed into replacement instead of making old seasons look better.
"""
import statistics

NUM_TEAMS = 12
HITTER_SLOTS = 12            # C,1B,2B,SS,3B,MI,OF1-5,UTIL (shared.js HITTER_SLOTS)
STARTING_HITTERS = NUM_TEAMS * HITTER_SLOTS          # 144 — used for synthetic teams
TEAM_IP_BUDGET = 1500                                # shared.js IP_MAX
LEAGUE_IP_BUDGET = NUM_TEAMS * TEAM_IP_BUDGET        # 18000

# Replacement level mirrors the FUTURE-YEAR branch of computeFABaselines in
# shared.js, which is the case that matches ours: it abandons "who is actually a
# free agent" (undefined for a historical season) and instead skips the top N
# the league rosters, taking the cohort at the boundary of what remains. Its
# comment: "the roster boundary dissolves each October ... the league re-rosters
# the best available."
#
# Constants are shared.js's, not invented here:
FA_COHORT_H = 8              # hitters averaged into the baseline
FA_COHORT_P = 10             # pitchers averaged into the baseline
FA_MIN_PA = 100              # role floor: excludes stashed prospects / injured
FA_MIN_IP = 30               # excludes elite rates on no playing time
# Rostered counts measured from this league's roster.csv on 2026-09-26 (526
# players across 12 teams). Skipping only the 144 STARTING slots would set
# replacement far too high -- teams roster ~25 hitters each, and the genuinely
# free alternative sits past all of them.
ROSTERED_H = 295
ROSTERED_P = 231


def _hitter_rank(row):
    """Crude quality proxy for ordering only: volume x rate."""
    return row["pa"] * (row["obp"] + row["slg"])


def _pitcher_rank(row):
    era = row["era"] if row["era"] > 0 else 99.0
    return row["ip"] * (1.0 / era + row["so"] / 1000.0)


def build_denominators(hitter_rows, pitcher_rows):
    """Split the pool into NUM_TEAMS synthetic teams and take the stdev of each
    category's team total -- the same quantity calcSGPDenoms measures."""
    hs = sorted(hitter_rows, key=_hitter_rank, reverse=True)[:STARTING_HITTERS]
    ps = sorted(pitcher_rows, key=_pitcher_rank, reverse=True)
    if len(hs) < NUM_TEAMS * 2 or len(ps) < NUM_TEAMS * 2:
        raise ValueError("pool too small to build synthetic teams")

    # Snake the ranked players across teams so every team is comparable.
    teams = [{"h": [], "p": []} for _ in range(NUM_TEAMS)]
    for i, row in enumerate(hs):
        leg = i // NUM_TEAMS
        idx = i % NUM_TEAMS
        teams[idx if leg % 2 == 0 else NUM_TEAMS - 1 - idx]["h"].append(row)
    per_team_ip = LEAGUE_IP_BUDGET / NUM_TEAMS
    t = 0
    for row in ps:
        if sum(x["ip"] for x in teams[t]["p"]) >= per_team_ip:
            t += 1
            if t >= NUM_TEAMS:
                break
        teams[t]["p"].append(row)

    totals = {c: [] for c in ("HR", "R", "OBP", "SLG", "SO", "ERA", "WHIP", "HR9")}
    for team in teams:
        h, p = team["h"], team["p"]
        if not h or not p:
            continue
        pa = sum(x["pa"] for x in h) or 1
        ab = sum(x["ab"] for x in h) or 1
        ip = sum(x["ip"] for x in p) or 1
        totals["HR"].append(sum(x["hr"] for x in h))
        totals["R"].append(sum(x["r"] for x in h))
        totals["OBP"].append(sum(x["obp"] * x["pa"] for x in h) / pa)
        totals["SLG"].append(sum(x["slg"] * x["ab"] for x in h) / ab)
        totals["SO"].append(sum(x["so"] for x in p))
        totals["ERA"].append(sum(x["era"] * x["ip"] for x in p) / ip)
        totals["WHIP"].append(sum(x["whip"] * x["ip"] for x in p) / ip)
        totals["HR9"].append(sum(x["hr9"] * x["ip"] for x in p) / ip)

    out = {}
    for cat, vals in totals.items():
        if len(vals) < 2:
            raise ValueError(f"{cat}: fewer than 2 synthetic teams produced totals")
        sd = statistics.pstdev(vals)
        if not sd or sd != sd:
            raise ValueError(f"{cat}: degenerate denominator {sd!r}")
        out[cat] = sd
    return out


def hitter_replacement(hitter_rows):
    """Average of the cohort just past what the league rosters.

    Mirrors computeFABaselines' future-year branch: apply the volume floor, rank,
    skip ROSTERED_H, average the next FA_COHORT_H.
    """
    pool = [r for r in hitter_rows if (r.get("pa") or 0) >= FA_MIN_PA]
    ranked = sorted(pool, key=_hitter_rank, reverse=True)
    need = ROSTERED_H + FA_COHORT_H
    if len(ranked) < need:
        raise ValueError(f"need >= {need} hitters over {FA_MIN_PA} PA, got {len(ranked)}")
    cohort = ranked[ROSTERED_H:need]
    n = len(cohort)
    return {k: sum(r[k] for r in cohort) / n for k in ("pa", "ab", "hr", "r", "obp", "slg")}


def league_averages(hitter_rows, pitcher_rows):
    """avgPA / avgIP as calcPlayerSGP means them: per-TEAM totals for the
    players who actually start, NOT league-wide totals.

    Getting this wrong silently rescales every rate category. League-wide MLB PA
    divided by 12 is roughly double a 12-team fantasy team's starter PA, which
    would halve the weight of OBP and SLG against HR and R.
    """
    ranked = sorted(hitter_rows, key=_hitter_rank, reverse=True)[:STARTING_HITTERS]
    avg_pa = sum(r["pa"] for r in ranked) / NUM_TEAMS
    return avg_pa, float(TEAM_IP_BUDGET)


def pitcher_replacement(pitcher_rows):
    """Same construction as hitters, with the pitcher floor, count and cohort."""
    pool = [r for r in pitcher_rows if (r.get("ip") or 0.0) >= FA_MIN_IP]
    ranked = sorted(pool, key=_pitcher_rank, reverse=True)
    need = ROSTERED_P + FA_COHORT_P
    if len(ranked) < need:
        raise ValueError(f"need >= {need} pitchers over {FA_MIN_IP} IP, got {len(ranked)}")
    cohort = ranked[ROSTERED_P:need]
    n = len(cohort)
    return {k: sum(r[k] for r in cohort) / n for k in ("ip", "so", "era", "whip", "hr9")}
```

- [ ] **Step 4: Run the tests**

Expected: 21 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): synthetic-league denominators and replacement

Denominators come from splitting a reference season into 12 synthetic
teams and taking the stdev of each category total -- the same quantity
calcSGPDenoms measures -- then stay fixed across all label years, while
replacement is recomputed per season. That combination is what makes
2019 and 2024 comparable: era inflation lands in replacement instead of
making old seasons look better.

Computed here rather than read from the JS tool because, measured in
late September, the tool's exhausted RoS projections collapsed every
pitching denominator to the 1.0 fallback and hitter replacement to 2.2
PA. A test now asserts a rate denominator is never exactly 1.0.

Pitcher replacement uses the innings budget (12 x 1500) because the
league has no pitcher slot count.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Label math and the parity gate

**Files:**
- Create: `prospects-model/psmodel/labels.py`, `prospects-model/parity/js_side.js`, `prospects-model/parity/compare.py`, `prospects-model/tests/test_labels.py`

- [ ] **Step 1: Write the failing test**

`prospects-model/tests/test_labels.py`:
```python
import unittest
from psmodel import labels

DEN = {"HR": 4.0, "R": 12.5, "OBP": 0.00765, "SLG": 0.01165,
       "SO": 40.0, "ERA": 0.22, "WHIP": 0.03, "HR9": 0.10}
REPL_H = {"pa": 400, "ab": 360, "hr": 10, "r": 45, "obp": 0.305, "slg": 0.390}
REPL_P = {"ip": 120.0, "so": 110, "era": 4.20, "whip": 1.33, "hr9": 1.25}


class TestHitterSGP(unittest.TestCase):
    def test_replacement_level_player_scores_about_zero(self):
        row = {"pa": 400, "ab": 360, "hr": 10, "r": 45, "obp": 0.305, "slg": 0.390}
        self.assertAlmostEqual(labels.hitter_sgp(row, REPL_H, DEN, 600), 0.0, places=9)

    def test_better_player_scores_higher(self):
        weak = {"pa": 600, "ab": 540, "hr": 15, "r": 60, "obp": 0.310, "slg": 0.400}
        strong = {"pa": 600, "ab": 540, "hr": 40, "r": 100, "obp": 0.390, "slg": 0.560}
        self.assertGreater(labels.hitter_sgp(strong, REPL_H, DEN, 600),
                           labels.hitter_sgp(weak, REPL_H, DEN, 600))

    def test_counting_stats_prorate_replacement_to_playing_time(self):
        """Half a season of replacement-rate production is still ~0, not a
        penalty -- the 'Will Smith fix' in shared.js."""
        half = {"pa": 200, "ab": 180, "hr": 5, "r": 22.5, "obp": 0.305, "slg": 0.390}
        self.assertAlmostEqual(labels.hitter_sgp(half, REPL_H, DEN, 600), 0.0, places=6)


class TestPitcherSGP(unittest.TestCase):
    def test_replacement_level_pitcher_scores_about_zero(self):
        row = {"ip": 120.0, "so": 110, "era": 4.20, "whip": 1.33, "hr9": 1.25}
        self.assertAlmostEqual(labels.pitcher_sgp(row, REPL_P, DEN, 1400), 0.0, places=9)

    def test_ip_scale_never_scales_down(self):
        """max(1, ip/repl.ip) is load-bearing: a short reliever faces the FULL
        replacement strikeout total, so identical rates over fewer innings must
        score LOWER, not the same. Pro-rating down once inflated relievers to
        ~47% of all pitching value (shared.js invariant #3)."""
        rate = {"era": 2.50, "whip": 1.00, "hr9": 0.80}
        short = dict(rate, ip=30.0, so=40)      # 12.0 K/9
        full = dict(rate, ip=120.0, so=160)     # 12.0 K/9, same rates
        self.assertLess(labels.pitcher_sgp(short, REPL_P, DEN, 1400),
                        labels.pitcher_sgp(full, REPL_P, DEN, 1400))

    def test_lower_era_is_better(self):
        good = {"ip": 180.0, "so": 200, "era": 2.80, "whip": 1.05, "hr9": 0.90}
        bad = {"ip": 180.0, "so": 200, "era": 4.80, "whip": 1.05, "hr9": 0.90}
        self.assertGreater(labels.pitcher_sgp(good, REPL_P, DEN, 1400),
                           labels.pitcher_sgp(bad, REPL_P, DEN, 1400))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Expected: `ModuleNotFoundError: No module named 'psmodel.labels'`

- [ ] **Step 3: Implement**

`prospects-model/psmodel/labels.py`:
```python
"""4x4 SGP above replacement -- a mirror of calcPlayerSGP in shared.js.

Any change here must keep parity/compare.py passing. The JS engine is the
reference implementation; this is a port, not a redesign.

Known simplification: uses the general replacement baseline, not hitterSGP's
positional offsets. Those need full-league position data per season and
redistribute value among hitters rather than changing the total.
"""


def hitter_sgp(row, repl, den, avg_pa):
    pa = row["pa"] or 0
    pa_ratio = (pa / repl["pa"]) if repl.get("pa") else 1.0
    sgp = (row["hr"] - repl["hr"] * pa_ratio) / den["HR"]
    sgp += (row["r"] - repl["r"] * pa_ratio) / den["R"]
    sgp += (row["obp"] - repl["obp"]) * pa / (avg_pa or 1) / den["OBP"]
    sgp += (row["slg"] - repl["slg"]) * pa / (avg_pa or 1) / den["SLG"]
    return sgp


def pitcher_sgp(row, repl, den, avg_ip):
    ip = row["ip"] or 0.0
    # max(1, ...) never scales DOWN: a low-inning reliever faces the full
    # replacement K total and stays docked for volume (shared.js invariant #3).
    ip_scale = max(1.0, ip / repl["ip"]) if repl.get("ip") else 1.0
    sgp = (row["so"] - repl["so"] * ip_scale) / den["SO"]
    sgp += (repl["era"] - row["era"]) * ip / (avg_ip or 1) / den["ERA"]
    sgp += (repl["whip"] - row["whip"]) * ip / (avg_ip or 1) / den["WHIP"]
    sgp += (repl["hr9"] - row["hr9"]) * ip / (avg_ip or 1) / den["HR9"]
    return sgp
```

- [ ] **Step 4: Run the tests**

Expected: 27 tests, `OK`.

- [ ] **Step 5: Write the parity harness**

`prospects-model/parity/js_side.js`:
```javascript
// Runs shared.js calcPlayerSGP on injected inputs and prints JSON.
// Inputs are injected so the comparison isolates the FORMULA: the JS tool's
// own denominators and replacement levels depend on its seasonal state (in
// late September they collapse to 1.0 and 2.2 PA), which would make an
// end-to-end comparison fail for reasons unrelated to the math.
const fs = require('fs'), vm = require('vm'), path = require('path');
const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  window: { location: { hostname: '', pathname: '' } },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'shared.js'), 'utf8'), sandbox);

const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = cases.map(c =>
  sandbox.calcPlayerSGP({ type: c.type }, c.stats, c.repl, c.den, c.avgPA, c.avgIP));
process.stdout.write(JSON.stringify(out));
```

`prospects-model/parity/compare.py`:
```python
"""Parity gate: the Python SGP math must equal shared.js to 1e-9.

If this fails, the labels are wrong and every downstream finding inherits the
error. Run it after ANY change to psmodel/labels.py.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from psmodel import labels                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEN = {"HR": 4.01009, "R": 12.45428, "OBP": 0.00765, "SLG": 0.01165,
       "SO": 41.3, "ERA": 0.2184, "WHIP": 0.0312, "HR9": 0.0975}
REPL_H = {"pa": 431.0, "ab": 389.0, "hr": 11.4, "r": 48.6, "obp": 0.3102, "slg": 0.3944}
REPL_P = {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711}
AVG_PA, AVG_IP = 6100.0, 1440.0

HITTERS = [
    {"pa": 477, "ab": 395, "hr": 27, "r": 63, "obp": 0.397, "slg": 0.522},   # Soto 2026
    {"pa": 600, "ab": 540, "hr": 40, "r": 100, "obp": 0.390, "slg": 0.560},
    {"pa": 431, "ab": 389, "hr": 11.4, "r": 48.6, "obp": 0.3102, "slg": 0.3944},  # == repl
    {"pa": 80, "ab": 72, "hr": 1, "r": 6, "obp": 0.260, "slg": 0.300},        # cameo
    {"pa": 0, "ab": 0, "hr": 0, "r": 0, "obp": 0.0, "slg": 0.0},              # empty
]
PITCHERS = [
    {"ip": 62 + 2 / 3, "so": 69, "era": 2.59, "whip": 0.99, "hr9": 0.574},   # Pearson 2019 AA
    {"ip": 200.0, "so": 240, "era": 2.80, "whip": 1.02, "hr9": 0.85},
    {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711},  # == repl
    {"ip": 30.0, "so": 45, "era": 1.90, "whip": 0.85, "hr9": 0.60},           # reliever
    {"ip": 0.0, "so": 0, "era": 0.0, "whip": 0.0, "hr9": 0.0},                # empty
]


def main() -> int:
    cases, expected = [], []
    for row in HITTERS:
        cases.append({"type": "H", "stats": row, "repl": REPL_H, "den": DEN,
                      "avgPA": AVG_PA, "avgIP": AVG_IP})
        expected.append(labels.hitter_sgp(row, REPL_H, DEN, AVG_PA))
    for row in PITCHERS:
        cases.append({"type": "P", "stats": row, "repl": REPL_P, "den": DEN,
                      "avgPA": AVG_PA, "avgIP": AVG_IP})
        expected.append(labels.pitcher_sgp(row, REPL_P, DEN, AVG_IP))

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cases, fh)
        case_file = fh.name
    try:
        proc = subprocess.run(["node", os.path.join(HERE, "js_side.js"), case_file],
                              capture_output=True, text=True, check=True)
    finally:
        os.unlink(case_file)
    got = json.loads(proc.stdout)

    worst, failures = 0.0, 0
    for i, (py, js) in enumerate(zip(expected, got)):
        diff = abs(py - js)
        worst = max(worst, diff)
        if diff > 1e-9:
            failures += 1
            print(f"  MISMATCH case {i}: python={py!r} js={js!r} diff={diff:g}")
    print(f"parity: {len(cases)} cases, max abs diff {worst:.3e}, {failures} failures")
    if failures:
        print("FAIL - labels do not match shared.js; do not build on these labels")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the parity gate**

Run: `cd prospects-model && python parity/compare.py`
Expected: `parity: 10 cases, max abs diff <= 1e-09, 0 failures` then `PASS`.

If it fails, **stop** — fix `labels.py` to match the JS, not the reverse.

- [ ] **Step 7: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): SGP label math with a parity gate vs shared.js

Ports calcPlayerSGP to Python and proves it agrees with the JS engine to
1e-9 across 10 cases including replacement-level players, a cameo, a
short reliever and empty lines. shared.js is the reference; this is a
port, not a redesign.

The harness injects denominators and replacement levels into BOTH sides
so it isolates the formula. An end-to-end comparison would fail for
unrelated reasons: the live tool's September state collapses its own
pitching denominators to 1.0 and hitter replacement to 2.2 PA.

Tests pin the two subtleties that make the math non-obvious: counting
stats pro-rate replacement to playing time (so a half-season at
replacement rate scores ~0, not a penalty), and the pitcher ipScale
max(1, ...) never scales down, keeping short relievers docked on volume.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Target construction

**Files:**
- Create: `prospects-model/psmodel/targets.py`, `prospects-model/tests/test_targets.py`

- [ ] **Step 1: Write the failing test**

`prospects-model/tests/test_targets.py`:
```python
import unittest
from psmodel import targets

CURRENT = 2026


def season(year, value, pa=500, ip=0.0):
    return {"season": year, "value": value, "pa": pa, "ip": ip}


class TestWindow(unittest.TestCase):
    def test_peak_is_max_within_four_seasons_of_debut(self):
        rows = [season(2019, 5.0), season(2020, 12.0), season(2021, 30.0),
                season(2022, 18.0), season(2023, 99.0)]   # year 5 must be ignored
        t = targets.build_target(rows, current_season=CURRENT)
        self.assertEqual(t["debut_season"], 2019)
        self.assertAlmostEqual(t["peak_value"], 30.0)
        self.assertEqual(t["peak_season"], 2021)

    def test_cameo_cannot_be_the_peak(self):
        rows = [season(2022, 40.0, pa=40), season(2023, 9.0, pa=500)]
        t = targets.build_target(rows, current_season=CURRENT)
        self.assertAlmostEqual(t["peak_value"], 9.0)
        self.assertEqual(t["peak_season"], 2023)

    def test_no_eligible_season_is_zero_not_none(self):
        t = targets.build_target([season(2024, 3.0, pa=30)], current_season=CURRENT)
        self.assertEqual(t["peak_value"], 0.0)


class TestCompleteness(unittest.TestCase):
    def test_complete_window_weighs_one(self):
        rows = [season(2019, 10.0)]
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 1.0)

    def test_partial_window_is_downweighted(self):
        rows = [season(2025, 10.0)]        # 2025,2026 observed of 2025-2028
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 0.5)

    def test_weight_floors_at_quarter(self):
        rows = [season(2026, 10.0)]
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 0.25)


class TestTimeToContribution(unittest.TestCase):
    def test_seasons_from_snapshot_to_first_eligible_season(self):
        rows = [season(2022, 2.0, pa=60), season(2023, 14.0, pa=520)]
        t = targets.build_target(rows, CURRENT, snapshot_season=2021)
        self.assertEqual(t["years_to_contribute"], 2)   # 2021 -> 2023

    def test_none_when_never_contributed(self):
        t = targets.build_target([season(2024, 1.0, pa=20)], CURRENT, snapshot_season=2023)
        self.assertIsNone(t["years_to_contribute"])


class TestNonArrival(unittest.TestCase):
    """'Hasn't yet' must never be confused with 'never will'."""

    def test_long_gone_prospect_is_a_labeled_zero(self):
        t = targets.build_target([], CURRENT, snapshot_season=2018)
        self.assertTrue(t["labeled"])
        self.assertEqual(t["peak_value"], 0.0)

    def test_recent_prospect_without_a_debut_is_unlabeled(self):
        t = targets.build_target([], CURRENT, snapshot_season=2024)
        self.assertFalse(t["labeled"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Expected: `ModuleNotFoundError: No module named 'psmodel.targets'`

- [ ] **Step 3: Implement**

`prospects-model/psmodel/targets.py`:
```python
"""Turns a player's MLB season labels into a training target.

Peak value over the first 4 seasons from debut. The window is short on purpose:
the planning horizon is not 5-10 years, so producing well AND soon is the goal,
and a short window also leaves more cohorts with complete outcomes.
"""
WINDOW = 4
MIN_PA = 100          # peak-eligibility floor; low volume already self-penalizes
MIN_IP = 25
NON_ARRIVAL_YEARS = 5  # seasons after the snapshot before a no-show counts as a zero
MIN_WEIGHT = 0.25


def _eligible(row):
    return (row.get("pa") or 0) >= MIN_PA or (row.get("ip") or 0.0) >= MIN_IP


def build_target(mlb_seasons, current_season, snapshot_season=None):
    """mlb_seasons: [{season, value, pa, ip}] for ONE player (may be empty)."""
    rows = sorted(mlb_seasons, key=lambda r: r["season"])
    if not rows:
        elapsed = (current_season - snapshot_season) if snapshot_season is not None else 0
        labeled = snapshot_season is not None and elapsed >= NON_ARRIVAL_YEARS
        return {"debut_season": None, "peak_value": 0.0, "peak_season": None,
                "completeness": 1.0 if labeled else 0.0,
                "years_to_contribute": None, "labeled": labeled}

    debut = rows[0]["season"]
    window = [r for r in rows if debut <= r["season"] <= debut + WINDOW - 1]
    eligible = [r for r in window if _eligible(r)]

    peak = max(eligible, key=lambda r: r["value"]) if eligible else None
    observed = min(WINDOW, max(0, current_season - debut + 1))
    first = next((r for r in rows if _eligible(r)), None)

    return {
        "debut_season": debut,
        "peak_value": peak["value"] if peak else 0.0,
        "peak_season": peak["season"] if peak else None,
        "completeness": max(MIN_WEIGHT, observed / WINDOW),
        "years_to_contribute": (first["season"] - snapshot_season)
                               if (first and snapshot_season is not None) else None,
        "labeled": True,
    }
```

- [ ] **Step 4: Run the tests**

Expected: 37 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add prospects-model
git commit -m "feat(prospects-model): target construction with honest non-arrival rule

Peak value over the first four seasons from debut, with a playing-time
floor so a cameo can never be the peak, and NFLU-style completeness
weighting for partial windows.

The subtle part is the non-arrival rule: a minor leaguer who has not
debuted is UNKNOWN, not a zero. Only after five seasons with no debut
does he become a labeled zero. Conflating 'hasn't yet' with 'never
will' would poison exactly the recent cohorts that matter most.

Also emits years_to_contribute as a second output, so a distant high
ceiling and an imminent solid regular do not collapse into one score.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Build the real labels; document

**Files:**
- Create: `prospects-model/build_labels.py`
- Modify: `MODEL.md` (fix the stale §1 data-feeds table)

- [ ] **Step 1: Write the driver**

`prospects-model/build_labels.py`:
```python
"""Builds MLB player-season labels for 2015-2026 and writes cache/labels.csv.

Usage:  python build_labels.py [--reference-season 2024]

Denominators come from ONE reference season and are then fixed; replacement is
per season. Prints a summary so the numbers can be eyeballed before use.
"""
import argparse
import csv
import os

from psmodel import context, labels, statsapi

FIRST, LAST = 2015, 2026
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "labels.csv")


def sanitize(v):
    """CSV injection guard for spreadsheet users."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not s.lstrip("-").replace(".", "", 1).isdigit() else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference-season", type=int, default=2024)
    args = ap.parse_args()

    ref_h = statsapi.season_stats(args.reference_season, "hitting", statsapi.MLB)
    ref_p = statsapi.season_stats(args.reference_season, "pitching", statsapi.MLB)
    den = context.build_denominators(ref_h, ref_p)
    print(f"denominators from {args.reference_season}:")
    for cat in ("HR", "R", "OBP", "SLG", "SO", "ERA", "WHIP", "HR9"):
        print(f"  {cat:5} {den[cat]:.5f}")

    rows = []
    for season in range(FIRST, LAST + 1):
        hs = statsapi.season_stats(season, "hitting", statsapi.MLB)
        ps = statsapi.season_stats(season, "pitching", statsapi.MLB)
        repl_h = context.hitter_replacement(hs)
        repl_p = context.pitcher_replacement(ps)
        avg_pa, avg_ip = context.league_averages(hs, ps)
        for r in hs:
            rows.append({"player_id": r["player_id"], "name": r["name"], "season": season,
                         "type": "H", "pa": r["pa"], "ip": 0.0,
                         "value": labels.hitter_sgp(r, repl_h, den, avg_pa)})
        for r in ps:
            rows.append({"player_id": r["player_id"], "name": r["name"], "season": season,
                         "type": "P", "pa": 0, "ip": r["ip"],
                         "value": labels.pitcher_sgp(r, repl_p, den, avg_ip)})
        top = sorted((r for r in rows if r["season"] == season),
                     key=lambda r: r["value"], reverse=True)[:3]
        print(f"{season}: {len(hs)} hitters, {len(ps)} pitchers | replH pa={repl_h['pa']:.0f} "
              f"obp={repl_h['obp']:.3f} | top: " +
              ", ".join(f"{t['name']} {t['value']:.1f}" for t in top))

    # Never overwrite a good artifact with a partial one. Borrowed from
    # autoLoadFromRepo in shared.js, which learned this the hard way: a blank
    # upstream export parsed to zero rows, silently replaced good cached data,
    # and every hitter in the tool showed "No proj" with no error anywhere.
    expected_seasons = LAST - FIRST + 1
    seasons_seen = len({r["season"] for r in rows})
    if seasons_seen < expected_seasons:
        raise SystemExit(f"REFUSING TO WRITE: only {seasons_seen}/{expected_seasons} "
                         f"seasons produced rows. Existing {OUT} left untouched.")
    if len(rows) < expected_seasons * 500:
        raise SystemExit(f"REFUSING TO WRITE: {len(rows)} rows is implausibly few for "
                         f"{expected_seasons} seasons. Existing {OUT} left untouched.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["player_id", "name", "season", "type", "pa", "ip", "value"])
        w.writeheader()
        for r in rows:
            w.writerow({k: sanitize(v) for k, v in r.items()})
    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd prospects-model && python build_labels.py`

Expected: 12 seasons summarized; ~1,400–1,600 rows per season. **Sanity gates
to eyeball before trusting the output:**
- No pitching denominator is exactly `1.0` (that's the collapse fallback).
- Hitter replacement shows **PA in the hundreds**, not single digits.
- The top-3 names per season are recognizable stars, not bench players.

- [ ] **Step 3: Re-run the parity gate**

Run: `cd prospects-model && python parity/compare.py`
Expected: `PASS`.

- [ ] **Step 4: Fix the stale MODEL.md §1 table**

In `MODEL.md` §1, replace the two stale rows:

```
| `proj_*_y1/y2.csv` | manual upload (full-season projections) | occasional |
| `data/prospects.csv` | manual (FanGraphs The Board export) | occasional |
```

with:

```
| `proj_*_y1/y2.csv` | Apps Script → FanGraphs ZiPS `zipsp1`/`zipsp2` (full-season) | weekly (trigger) |
| `data/prospects.csv` | Apps Script → FanGraphs Board `prospects-list-combined` | weekly (trigger) |
| `data/prospects_stats_hitting.csv` / `_pitching.csv` | Apps Script → same Board call (`dataStats`) | weekly (trigger) |
```

- [ ] **Step 5: Run the full suite**

Run: `cd prospects-model && python -m unittest discover -s tests -v`
Expected: 37 tests, `OK`.

- [ ] **Step 6: Commit**

```bash
git add prospects-model MODEL.md
git commit -m "feat(prospects-model): build MLB season labels 2015-2026

Driver that pulls every MLB player-season, derives fixed denominators
from a reference season, recomputes replacement per season, and writes
cache/labels.csv (gitignored -- derived artifacts only).

Prints sanity gates that catch the failure mode found during design: a
pitching denominator of exactly 1.0 or a single-digit replacement PA
means the computation collapsed rather than produced a label.

Also fixes MODEL.md section 1, which still described the Y1/Y2
projections and prospect files as manual uploads after they were
automated in September 2026.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Not in this plan (next sub-projects)

- **Features** from MiLB seasons, normalized within level-season, handling the
  2020 gap and multi-level seasons.
- **Probe StatsAPI play-by-play for MiLB `hitData`** — decides whether exit
  velocity and launch angle are available for prospects as clean JSON rather
  than scraped HTML. Bat speed and squared-up appear MLB-only.
- **Model and backtest** with the 2-of-3 adoption rule and phantom-feature guard.
- **Savant bridge** calibrated on MLB 2015+ (and 2023+ for bat tracking).
- **Tool surface** in `prospects.html` with the edge column.
