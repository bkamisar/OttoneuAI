"""Pulls the 3c-hitters inputs into the HTTP cache: minor-league hitter season
totals at four levels for 2012-2026 (swing data from WHIFF_FIRST), and MLB PA for
2005-2026 (the established-player cut). Every request is cached, so a rerun
resumes where a killed run stopped.

Usage:  python pull_3c_data.py
"""
from psmodel import cohorts, milb


def main():
    hist = cohorts.mlb_pa_history()
    print(f"MLB PA history: {len(hist)} players, {cohorts.PA_HISTORY_FIRST}-{cohorts.CURRENT_SEASON}", flush=True)
    for s in cohorts.MILB_SEASONS:
        parts = []
        for sid in cohorts.LEVELS:
            rows = milb.season_rows(s, sid, "hitting", advanced=s >= cohorts.WHIFF_FIRST)
            q = sum(1 for r in rows if r["pa"] >= cohorts.MIN_PA)
            sw = sum(1 for r in rows if r.get("swings"))
            parts.append(f"{cohorts.LEVEL_NAMES[sid]} {len(rows)} ({q} with {cohorts.MIN_PA}+ PA, {sw} with swings)")
        print(s, " | ".join(parts), flush=True)


if __name__ == "__main__":
    main()
