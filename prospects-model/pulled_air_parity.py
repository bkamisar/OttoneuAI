"""Pulled-air parity: does our pull% x FB% (charted coordinates, game records)
reproduce Savant's pull% x FB% for MLB hitters? Plan A's bar: r >= 0.98.
Only if it passes can pulled air be measured in AAA.

Usage:  python pulled_air_parity.py
Reads MLB game records 2023-2026 and cache/mlb_tracking.csv; writes
cache/pulled_air_parity.json. No network.
"""
import json
import os

import numpy as np

from psmodel import spray, step1, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "pulled_air_parity.json")
SEASONS = (2023, 2024, 2025, 2026)
BAR = 0.98


def main():
    savant = step1.load_table(os.path.join(HERE, "cache", "mlb_tracking.csv"))
    pairs = []
    for season in SEASONS:
        for pid, (pull, fb, n) in spray.pull_and_fb(tracking.season_events(season, 1)).items():
            sv = savant.get((pid, season)) or {}
            if n < 100 or pull is None or sv.get("pull_percent") is None or sv.get("flyballs_percent") is None:
                continue
            pairs.append((pull * fb / 100.0, sv["pull_percent"] * sv["flyballs_percent"] / 100.0,
                          pull, sv["pull_percent"]))
        print(f"{season}: {len(pairs)} hitter-seasons so far", flush=True)
    a = np.array(pairs)
    r_product = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    r_pull = float(np.corrcoef(a[:, 2], a[:, 3])[0, 1])
    out = {"n": len(pairs), "r_product": r_product, "r_pull": r_pull,
           "bias_product": float(np.mean(a[:, 0] - a[:, 1])), "bar": BAR, "passed": r_product >= BAR}
    print(json.dumps(out, indent=2))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
