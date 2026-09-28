# Minor-League Tracking Probe: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find out, with a small sample and not a download, which minor-league levels below AAA carry exit-velocity tracking in their game records, 2021–2026.

**Architecture:** One script, `prospects-model/probe_minors_tracking.py`. It reuses the existing, tested `psmodel/pbp.py` (schedule, game fetch, atomic cached writes) and `psmodel/tracking.py` (event parser). It samples 4 games per season × level × home league and applies a rule fixed in advance.

**Tech Stack:** Python 3 stdlib; existing `psmodel` modules; `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-28-post-build-queue-design.md`, part B.

---

## Ground rules

- **Where to run:** from `prospects-model/`. Tests: `python -m unittest discover -s tests`. Note the count before starting; this plan adds 2 tests.
- **The only network step is Task 2, and the security audit comes first.** Hosts: `statsapi.mlb.com` only. It makes about 18 schedule requests plus about 216 game records at 1 request/second, roughly 4–5 minutes. The records are cached under the gitignored `cache/pbp_live/`, so a relaunch skips what's already on disk.
- **Do NOT use `fetch_pbp.py --limit`.** It rewrites phase manifests. This script never touches manifests.
- **No bulk download.** If the result makes a bigger download look worthwhile, that is a separate plan, written on Opus.
- **Commits:** commit locally. **Never push, fetch or pull.**

---

### Task 1: The probe script (TDD for its two helpers)

**Files:**
- Create: `prospects-model/probe_minors_tracking.py`
- Test: `prospects-model/tests/test_probe.py`

- [ ] **Step 1: Write the failing tests**

Create `prospects-model/tests/test_probe.py`:

```python
import unittest

import probe_minors_tracking as P


def pitch(code, ev=None):
    return {"isPitch": True, "details": {"code": code}, "hitData": {"launchSpeed": ev} if ev else {}}


class TestProbe(unittest.TestCase):
    def test_spread_picks_evenly_through_the_season(self):
        self.assertEqual(P.spread(list(range(10)), 4), [1, 3, 6, 8])
        self.assertEqual(P.spread([1, 2], 4), [1, 2])

    def test_ev_share_counts_balls_in_play_only(self):
        game = {"liveData": {"plays": {"allPlays": [{"matchup": {}, "playEvents": [
            pitch("X", 95.0), pitch("D"), pitch("S"), pitch("E", 101.2), pitch("B")]}]}}}
        n, share = P.ev_share(game)
        self.assertEqual(n, 3)
        self.assertAlmostEqual(share, 2 / 3)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_probe -v`. Expected: ERROR, `ModuleNotFoundError: No module named 'probe_minors_tracking'`.

- [ ] **Step 3: Write the script**

Create `prospects-model/probe_minors_tracking.py`:

```python
"""Is there ball tracking (exit velocity) in the minors below AAA?

A SMALL probe, not a download (the prove-the-need rule): for each season
2021-2026, level (AA, High-A, Single-A) and home league, it fetches 4 complete
game records spread across the season and counts how many balls in play carry
exit velocity. Rule set in advance (spec part B): a league-season HAS TRACKING if
>= 3 of its 4 sampled games have EV on >= 80% of balls in play.

Usage:  python probe_minors_tracking.py
Network: statsapi.mlb.com only (schedule + game feeds), 1 request/second, cached
under cache/ (gitignored); about 216 game records. Never touches fetch_pbp.py's
phase manifests. Writes cache/minors_tracking_probe.json.
"""
import json
import os

from psmodel import pbp, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "minors_tracking_probe.json")
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
LEVELS = {12: "AA", 13: "High-A", 14: "Single-A"}
PER_LEAGUE = 4
IN_PLAY = frozenset({"X", "D", "E"})        # StatsAPI pitch codes for a ball put in play
GAME_EV_SHARE = 0.80
GAMES_NEEDED = 3


def spread(items, n):
    """n items evenly spaced through a list (all of them if there are n or fewer)."""
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step + step / 2)] for i in range(n)]


def ev_share(game):
    """(balls in play, share of them carrying exit velocity)."""
    bip = [e for e in tracking.iter_events(game) if e["code"] in IN_PLAY]
    return len(bip), (sum(1 for e in bip if e["ev"] is not None) / len(bip) if bip else 0.0)


def main():
    out = []
    for season in SEASONS:
        for sid, level in LEVELS.items():
            games = pbp.list_games(season, sid)
            for lg in sorted({g["home_league_id"] for g in games if g["home_league_id"] is not None}):
                picked = spread([g for g in games if g["home_league_id"] == lg], PER_LEAGUE)
                shares = []
                for g in picked:
                    pbp.fetch_game(season, sid, g["game_pk"])
                    shares.append(ev_share(pbp.load_game(season, sid, g["game_pk"]))[1])
                tracked = sum(1 for s in shares if s >= GAME_EV_SHARE) >= GAMES_NEEDED
                row = {"season": season, "level": level, "league_id": lg, "games": len(picked),
                       "ev_shares": [round(s, 2) for s in shares], "has_tracking": tracked}
                out.append(row)
                print(f"{season} {level:8} home league {lg}: EV share by game {row['ev_shares']} -> "
                      f"{'TRACKED' if tracked else 'no'}", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"\n{sum(r['has_tracking'] for r in out)} of {len(out)} league-seasons have tracking -> {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_probe -v`. Expected: 2 tests OK. Then `python -m unittest discover -s tests`. Expected: all pass (the earlier count + 2), 3 skipped.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add probe_minors_tracking.py tests/test_probe.py
git commit -m "feat(probe): small sampled probe for exit-velocity tracking below AAA"
```

### Task 2: Security audit, then run

- [ ] **Step 1: Security audit**

Confirm each of these and state the result to the user before running:
1. **Hosts:** `grep -n "https\?://" probe_minors_tracking.py psmodel/pbp.py psmodel/tracking.py` shows only `statsapi.mlb.com`.
2. **Imports:** the imports are stdlib plus `psmodel` only (`grep -n "^import\|^from" probe_minors_tracking.py`).
3. **Nothing from cache is tracked:** `git ls-files cache` prints nothing.
4. **No credentials:** no tokens, cookies or credentials anywhere in the request path (`psmodel/pbp.py` `_download` sends only a User-Agent).
5. **No stray fetch running:** check `tasklist | grep -i python` (the orphaned-fetch gotcha).

- [ ] **Step 2: Run**

Run: `python probe_minors_tracking.py`. Expected: one line per season × level × home league (about 54 lines), ending in "N of M league-seasons have tracking".

Sanity: the Single-A home league that is the Florida State League should read TRACKED from 2021 on, per `psmodel/pbp.py`'s notes. If it doesn't, report that; don't adjust the thresholds.

- [ ] **Step 3: Confirm nothing leaked into git**

Run: `git status --short; git ls-files cache`. Expected: no `cache/` paths.

- [ ] **Step 4: Hand to Opus**

Tell the user the headline count and ask them to switch to Opus. Opus will:
- map league ids to names;
- record the result in the post-build-queue spec;
- decide per spec part B: either close the question, or write a follow-up design with its outcome-history caveat.
