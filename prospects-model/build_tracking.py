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
