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
