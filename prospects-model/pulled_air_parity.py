"""Pulled-air parity: does our pull% x FB% (charted coordinates, game records)
reproduce Savant's for MLB hitters? Plan A's bar: r >= 0.98.
Only if it passes can pulled air be measured in AAA.

**The raw product is a flattered test and must not be the verdict.** Fly-ball rate
varies more between hitters than pull rate does and we measure it almost exactly
(r 0.9997), so it dominates the product: replacing our pull% with a CONSTANT still
correlates 0.88 with Savant's product. FB% is also already a model feature, so the
only thing pull x FB adds is the PULLED part. The verdict therefore uses the
product with FB regressed out of both sides (r 0.919 on 2023-26 -- a fail, in line
with pull% alone at 0.925).

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
                          pull, sv["pull_percent"], fb, sv["flyballs_percent"]))
        print(f"{season}: {len(pairs)} hitter-seasons so far", flush=True)
    a = np.array(pairs)
    ours, savant, our_pull, sv_pull, our_fb, sv_fb = (a[:, i] for i in range(6))

    def r(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    def without_fb(product, fb):
        return product - np.polyval(np.polyfit(fb, product, 1), fb)

    out = {"n": len(pairs), "bar": BAR,
           # The verdict: the pulled part, with fly-ball rate regressed out of both sides.
           "r_pulled_part": r(without_fb(ours, our_fb), without_fb(savant, sv_fb)),
           "r_product_raw": r(ours, savant),
           "r_product_constant_pull": r(np.mean(our_pull) * our_fb, savant),
           "r_pull": r(our_pull, sv_pull),
           "r_fb": r(our_fb, sv_fb),
           "bias_product": float(np.mean(ours - savant))}
    out["passed"] = out["r_pulled_part"] >= BAR
    print(json.dumps(out, indent=2))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
