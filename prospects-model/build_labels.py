"""Builds MLB player-season labels for 2013-2026 and writes cache/labels.csv.

Usage:  python build_labels.py [--standings ../data/standings.csv] [--games N]

Denominators are the league's real cross-team spread from standings.csv, held
FIXED across every year; replacement level is recomputed PER SEASON. Prints
sanity gates so the numbers can be eyeballed before use.

Two-way players (Ohtani) appear as one hitter row and one pitcher row per
season. They are kept separate here; summing them into one player-season is the
target builder's job.
"""
import argparse
import csv
import os

from psmodel import context, labels, statsapi

FIRST, LAST = 2013, 2026
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "labels.csv")
DEFAULT_STANDINGS = os.path.join(HERE, "..", "data", "standings.csv")


def sanitize_text(v):
    """CSV-injection guard for spreadsheet users. Applied to free-text fields
    ONLY: a numeric guard would prefix small floats like -1e-05 with an
    apostrophe and corrupt the column."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--standings", default=DEFAULT_STANDINGS)
    ap.add_argument("--games", type=int, default=None,
                    help="true games played; the file's Games column is calendar-estimated")
    ap.add_argument("--refresh", type=int, default=None,
                    help="refetch this season's MLB stats (cached while still in progress)")
    args = ap.parse_args()
    if args.refresh is not None:
        for group in ("hitting", "pitching"):
            n = statsapi.invalidate_season(args.refresh, group, statsapi.MLB)
            print(f"refresh {args.refresh} {group}: moved {n} cached page(s) aside")

    den = context.load_league_denominators(args.standings, games=args.games)
    print(f"denominators from {os.path.normpath(args.standings)}:")
    for cat in ("HR", "R", "SO", "OBP", "SLG", "ERA", "WHIP", "HR9"):
        print(f"  {cat:5} {den[cat]:.5f}")

    rows = []
    for season in range(FIRST, LAST + 1):
        hs = statsapi.season_stats(season, "hitting", statsapi.MLB)
        ps = statsapi.season_stats(season, "pitching", statsapi.MLB)
        frac = context.season_fraction(season)
        repl_h = context.hitter_replacement(hs, frac)
        repl_p = context.pitcher_replacement(ps, frac)
        avg_pa, avg_ip = context.league_averages()
        season_rows = []
        for r in hs:
            season_rows.append({"player_id": r["player_id"], "name": r["name"], "season": season,
                                "type": "H", "pa": r["pa"], "ip": 0.0,
                                "value": labels.hitter_sgp(r, repl_h, den, avg_pa)})
        for r in ps:
            season_rows.append({"player_id": r["player_id"], "name": r["name"], "season": season,
                                "type": "P", "pa": 0, "ip": r["ip"],
                                "value": labels.pitcher_sgp(r, repl_p, den, avg_ip)})
        rows.extend(season_rows)
        top = sorted(season_rows, key=lambda r: r["value"], reverse=True)[:3]
        print(f"{season}: {len(hs)} hitters, {len(ps)} pitchers | replH pa={repl_h['pa']:.0f} "
              f"obp={repl_h['obp']:.3f} | frac={frac:.2f} | top: " +
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
            r = dict(r, name=sanitize_text(r["name"]))
            w.writerow(r)
    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
