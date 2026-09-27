"""Parity gate: our tracking-metric code, run on the 2024 MLB game records, must
reproduce Baseball Savant's published 2024 leaderboard numbers before any AAA
metric is trusted -- the same idea as parity/compare.py for the SGP labels.

Uncertain definitions are run as variants; the best-matching one is written to
cache/tracking_definitions.json, which build_tracking.py requires.

Usage:  python parity_tracking.py
"""
import json
import os

import numpy as np

from psmodel import metrics, savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "cache", "tracking_parity_report.txt")
DEFS = os.path.join(HERE, "cache", "tracking_definitions.json")
SEASON = 2024
MIN_BBE, MIN_SWINGS = 100, 300
GATE_R, GATE_R_BARREL = 0.98, 0.95          # barrel window is unpublished, so a looser bar
VARIANTS = [{"foul_tip_is_whiff": ft, "count_bunts": cb}
            for ft in (False, True) for cb in (True, False)]


def score(ours, theirs):
    per = {}
    for m in metrics.HITTER_METRICS:
        need, floor = ("bbe", MIN_BBE) if m in metrics.BATTED_BALL_METRICS else ("swings", MIN_SWINGS)
        pairs = [(o[m], theirs[p][m]) for p, o in ours.items()
                 if p in theirs and o[need] >= floor
                 and o[m] is not None and theirs[p].get(m) is not None]
        if len(pairs) < 30:
            per[m] = {"n": len(pairs), "r": None, "mad": None, "sd": None}
            continue
        a, b = np.array(pairs, dtype=float).T
        per[m] = {"n": len(pairs), "r": float(np.corrcoef(a, b)[0, 1]),
                  "mad": float(np.mean(np.abs(a - b))), "sd": float(np.std(b)),
                  "bias": float(np.mean(a - b))}
    return per


def loss(per):
    return sum(p["mad"] / p["sd"] for p in per.values() if p["mad"] is not None and p["sd"])


def main():
    games = tracking.season_games(SEASON, 1)
    if len(games) < 2400:
        raise SystemExit(f"only {len(games)} 2024 MLB games on disk -- finish the download first")
    events = list(tracking.season_events(SEASON, 1))
    theirs = savant.hitter_season(SEASON)
    results = sorted(((loss(per), v, per) for v in VARIANTS
                      for per in [score(metrics.hitter_metrics(events, v), theirs)]),
                     key=lambda t: t[0])
    best_loss, best, per = results[0]
    fails = [m for m, p in per.items()
             if p["r"] is None or p["r"] < (GATE_R_BARREL if m == "barrel_batted_rate" else GATE_R)]

    lines = [f"Tracking parity -- our code on {len(games)} 2024 MLB games vs Savant's 2024 leaderboards",
             f"Variants tried: {len(VARIANTS)}; ranked by total normalized error (lower is better):"]
    for l_, v, _ in results:
        lines.append(f"  {l_:7.3f}  {v}")
    lines.append(f"\nChosen: {best}\n")
    lines.append(f"  {'metric':22} {'n':>5} {'r':>7} {'mean|diff|':>11} {'bias':>7}  gate")
    for m in metrics.HITTER_METRICS:
        p = per[m]
        bar = GATE_R_BARREL if m == "barrel_batted_rate" else GATE_R
        ok = p["r"] is not None and p["r"] >= bar
        r_txt = f"{p['r']:.4f}" if p["r"] is not None else "   n/a"
        extra = f"{p['mad']:11.3f} {p['bias']:+7.3f}" if p["mad"] is not None else f"{'':11} {'':7}"
        lines.append(f"  {m:22} {p['n']:5d} {r_txt:>7} {extra}  {'PASS' if ok else 'FAIL (needs ' + str(bar) + ')'}")
    lines.append("\nVERDICT: " + ("PASS -- AAA metrics can be trusted on Savant's definitions" if not fails
                                  else f"FAIL on {fails} -- do not build AAA metrics until resolved"))
    text = "\n".join(lines)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(DEFS, "w", encoding="utf-8") as fh:
        json.dump({"season": SEASON, "variant": best, "passed": not fails, "failed": fails,
                   "per_metric": per}, fh, indent=2)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
