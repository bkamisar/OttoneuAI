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
