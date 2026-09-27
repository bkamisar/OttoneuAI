"""Backfill minor-league play-by-play, one checkpointed game at a time.

Usage:
    python fetch_pbp.py                          # first slice: AA + AAA, 2016-2019
    python fetch_pbp.py --seasons 2021 2022 --levels 13 14
    python fetch_pbp.py --limit 5                # smoke test: 5 games per phase
    python fetch_pbp.py --force                  # refetch everything
    python fetch_pbp.py --seasons 2022 --levels 11 --leagues 112   # PCL only

Checkpointing, at two grains:
  * game  -- a game whose file exists is skipped (files are written atomically);
  * phase -- a (season, level) whose _manifest.json records zero failures, for
             the SAME league filter, is skipped outright on relaunch. A phase
             with failures is re-scanned, which only fetches the missing games.
             The current season is never marked complete, so games that finish
             after a run are picked up by the next one.
One bad game never kills the run: failures are logged to failures.json and
retried on the next launch.
"""
import argparse
import datetime
import json
import os
import sys
import time

from psmodel import http, pbp

LEVEL_NAMES = {11: "AAA", 12: "AA", 13: "High-A", 14: "Single-A"}
CURRENT_YEAR = datetime.date.today().year


def season_is_final(season):
    """A season still in progress must stay re-scannable."""
    return season < CURRENT_YEAR


def _league_key(leagues):
    return sorted(leagues) if leagues else None


def manifest_path(season, sport_id):
    return os.path.join(pbp.PBP_DIR, str(season), str(sport_id), "_manifest.json")


def phase_done(season, sport_id, leagues):
    """Done only if a complete, failure-free run covered the SAME leagues."""
    p = manifest_path(season, sport_id)
    if not os.path.exists(p):
        return False
    with open(p, encoding="utf-8") as fh:
        m = json.load(fh)
    return (bool(m.get("complete")) and m.get("failed", 1) == 0
            and m.get("leagues") == _league_key(leagues))


def run_phase(season, sport_id, force, limit, failures, leagues=None):
    games = pbp.list_games(season, sport_id, include_leagues=leagues)
    if limit:
        games = games[:limit]
    todo = sum(1 for g in games if force or not os.path.exists(pbp.game_path(season, sport_id, g["game_pk"])))
    name = f"{season} {LEVEL_NAMES.get(sport_id, sport_id)}" + (f" leagues={sorted(leagues)}" if leagues else "")
    print(f"[{name}] {len(games)} games, {todo} to fetch", flush=True)

    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    started, done_net = time.time(), 0
    for i, g in enumerate(games, 1):
        try:
            outcome = pbp.fetch_game(season, sport_id, g["game_pk"], force=force)
            counts[outcome] += 1
        except Exception as exc:          # noqa: BLE001 - log and keep going
            counts["failed"] += 1
            failures.append({"season": season, "sport_id": sport_id,
                             "game_pk": g["game_pk"], "error": str(exc)[:300]})
            continue
        if outcome == "fetched":
            done_net += 1
        if outcome == "fetched" and done_net % 200 == 0:
            rate = done_net / max(1e-9, time.time() - started)
            left = todo - done_net
            print(f"[{name}] {i}/{len(games)} | {rate:.2f} games/s | "
                  f"~{left / max(rate, 1e-9) / 60:.0f} min left in phase", flush=True)

    manifest = dict(counts, games=len(games), leagues=_league_key(leagues),
                    complete=(not limit) and season_is_final(season),
                    finished_at=datetime.datetime.now().isoformat(timespec="seconds"))
    os.makedirs(os.path.dirname(manifest_path(season, sport_id)), exist_ok=True)
    with open(manifest_path(season, sport_id), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[{name}] done: {counts}", flush=True)
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=[2016, 2017, 2018, 2019])
    ap.add_argument("--levels", type=int, nargs="+", default=[12, 11])   # AA first, then AAA
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="games per phase (smoke test)")
    ap.add_argument("--leagues", type=int, nargs="+", default=None,
                    help="only these home-league ids (e.g. 112 = Pacific Coast League)")
    args = ap.parse_args()

    failures, totals = [], {"fetched": 0, "skipped": 0, "failed": 0}
    t0 = time.time()
    for season in args.seasons:
        if season == 2020:
            print("[2020] no minor-league season (COVID) -- skipping", flush=True)
            continue
        for sport_id in args.levels:
            leagues = set(args.leagues) if args.leagues else None
            if not args.force and not args.limit and phase_done(season, sport_id, leagues):
                print(f"[{season} {LEVEL_NAMES.get(sport_id, sport_id)}] complete per manifest -- skipping", flush=True)
                continue
            c = run_phase(season, sport_id, args.force, args.limit, failures, leagues)
            for k in totals:
                totals[k] += c[k]

    fail_path = os.path.join(pbp.PBP_DIR, "failures.json")
    os.makedirs(pbp.PBP_DIR, exist_ok=True)
    with open(fail_path, "w", encoding="utf-8") as fh:
        json.dump(failures, fh, indent=2)
    print(f"\nALL DONE in {(time.time() - t0) / 60:.1f} min: {totals}"
          f"{' -- ' + str(len(failures)) + ' failures in ' + fail_path + '; rerun to retry them' if failures else ''}",
          flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
