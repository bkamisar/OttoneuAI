"""Parity gate for pitch tracking: our pitch-metric code, run on the 2024 MLB game
records, must reproduce Baseball Savant's published 2024 pitcher numbers before any
AAA pitch metric is trusted (the hitters' parity_tracking.py, for pitchers).

Gate per metric: r >= 0.98 AND |mean bias| <= 0.1 SD. Units matter here
(movement in inches), not just correlation. Uncertain definitions run as
variants; the best is written to cache/pitch_definitions.json, which
build_pitch_tracking.py requires.

Usage:  python parity_pitch.py
Network: one Savant CSV (2024 pitchers), cached. Run the security audit first.
"""
import json
import os

import numpy as np

from psmodel import pitch_metrics as PM
from psmodel import savant, tracking

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "cache", "pitch_parity_report.txt")
DEFS = os.path.join(HERE, "cache", "pitch_definitions.json")
SEASON = 2024
MIN_FB, MIN_BREAKING, MIN_SWINGS = 100, 50, 200
GATE_R, GATE_BIAS_SD = 0.98, 0.10
VARIANTS = [{"breaking": b, "movement": mv}
            for b in (PM.BREAKING_WIDE, PM.BREAKING_NARROW) for mv in ("breaks", "pfx")]


def _floor(m):
    if m in PM.FB_METRICS:
        return "fb_n", MIN_FB
    if m in PM.BREAKING_METRICS:
        return "breaking_n", MIN_BREAKING
    return "swings", MIN_SWINGS


def score(ours, theirs):
    per = {}
    for m in PM.PITCH_METRICS:
        need, floor = _floor(m)
        pairs = [(o[m], theirs[p][m]) for p, o in ours.items()
                 if p in theirs and o[need] >= floor and o[m] is not None and theirs[p].get(m) is not None]
        if len(pairs) < 30:
            per[m] = {"n": len(pairs), "r": None, "mad": None, "sd": None, "bias": None}
            continue
        a, b = np.array(pairs, dtype=float).T
        per[m] = {"n": len(pairs), "r": float(np.corrcoef(a, b)[0, 1]), "mad": float(np.mean(np.abs(a - b))),
                  "sd": float(np.std(b)), "bias": float(np.mean(a - b))}
    return per


def loss(per):
    return sum(p["mad"] / p["sd"] for p in per.values() if p["mad"] is not None and p["sd"])


def passes(p):
    return p["r"] is not None and p["r"] >= GATE_R and abs(p["bias"]) <= GATE_BIAS_SD * p["sd"]


def main():
    games = tracking.season_games(SEASON, 1)
    if len(games) < 2400:
        raise SystemExit(f"only {len(games)} 2024 MLB games on disk")
    pitches = list(tracking.season_pitches(SEASON, 1))
    theirs = savant.pitcher_season(SEASON)
    results = sorted(((loss(per), v, per) for v in VARIANTS
                      for per in [score(PM.pitcher_metrics(pitches, v), theirs)]), key=lambda t: t[0])
    best_loss, best, per = results[0]
    fails = [m for m, p in per.items() if not passes(p)]

    L = [f"Pitch-tracking parity -- our code on {len(games)} 2024 MLB games ({len(pitches)} pitches) "
         f"vs Savant's 2024 pitcher leaderboard",
         f"Variants tried: {len(VARIANTS)}; ranked by total normalized error (lower is better):"]
    L += [f"  {l_:7.3f}  breaking={list(v['breaking'])} movement={v['movement']}" for l_, v, _ in results]
    L += [f"\nChosen: breaking={list(best['breaking'])} movement={best['movement']}\n",
          f"  {'metric':16} {'n':>5} {'r':>7} {'mean|diff|':>11} {'bias':>8} {'sd':>8}  gate"]
    for m in PM.PITCH_METRICS:
        p = per[m]
        if p["r"] is None:
            L.append(f"  {m:16} {p['n']:5d}     n/a  FAIL (too few pairs)")
            continue
        L.append(f"  {m:16} {p['n']:5d} {p['r']:7.4f} {p['mad']:11.3f} {p['bias']:+8.3f} {p['sd']:8.3f}  "
                 + ("PASS" if passes(p) else f"FAIL (needs r >= {GATE_R}, |bias| <= {GATE_BIAS_SD} sd)"))
    L.append("\nVERDICT: " + ("PASS -- AAA pitch metrics can be trusted on Savant's definitions" if not fails
                              else f"FAIL on {fails} -- do not build the pitch tables until resolved"))
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(DEFS, "w", encoding="utf-8") as fh:
        json.dump({"season": SEASON, "variant": dict(best, breaking=list(best["breaking"])),
                   "passed": not fails, "failed": fails, "per_metric": per}, fh, indent=2)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
