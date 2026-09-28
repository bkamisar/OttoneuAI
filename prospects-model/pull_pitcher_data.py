"""Pulls the pitcher-track inputs into the HTTP cache: minor-league pitcher season
totals at four levels for 2012-2026 (with seasonAdvanced swing data), and MLB
pitching for 2005-2026 (the established-pitcher cut). Same host and endpoints as
the hitter pull (statsapi.mlb.com season aggregates -- no game records). Every
request is cached, so a rerun resumes where a killed run stopped.

Usage:  python pull_pitcher_data.py
"""
from psmodel import cohorts, milb, statsapi
from psmodel import features as F


def main():
    for s in range(cohorts.PA_HISTORY_FIRST, cohorts.CURRENT_SEASON + 1):
        rows = statsapi.season_stats(s, "pitching", statsapi.MLB)
        print(f"MLB {s}: {len(rows)} pitcher rows", flush=True)
    for s in cohorts.MILB_SEASONS:
        parts = []
        for sid in cohorts.LEVELS:
            rows = milb.season_rows(s, sid, "pitching", advanced=True)
            q = sum(1 for r in rows if r["ip"] >= F.PIT_MIN_IP)
            sw = sum(1 for r in rows if r.get("swings"))
            parts.append(f"{cohorts.LEVEL_NAMES[sid]} {len(rows)} ({q} with {F.PIT_MIN_IP:g}+ IP, {sw} with swings)")
        print(s, " | ".join(parts), flush=True)


if __name__ == "__main__":
    main()
