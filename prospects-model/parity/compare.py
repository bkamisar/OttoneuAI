"""Parity gate: the Python SGP math must equal shared.js to 1e-9.

If this fails, the labels are wrong and every downstream finding inherits the
error. Run it after ANY change to psmodel/labels.py.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from psmodel import labels                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEN = {"HR": 4.01009, "R": 12.45428, "OBP": 0.00765, "SLG": 0.01165,
       "SO": 41.3, "ERA": 0.2184, "WHIP": 0.0312, "HR9": 0.0975}
REPL_H = {"pa": 431.0, "ab": 389.0, "hr": 11.4, "r": 48.6, "obp": 0.3102, "slg": 0.3944}
REPL_P = {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711}
AVG_PA, AVG_IP = 6100.0, 1440.0

HITTERS = [
    {"pa": 477, "ab": 395, "hr": 27, "r": 63, "obp": 0.397, "slg": 0.522},   # Soto 2026
    {"pa": 600, "ab": 540, "hr": 40, "r": 100, "obp": 0.390, "slg": 0.560},
    {"pa": 431, "ab": 389, "hr": 11.4, "r": 48.6, "obp": 0.3102, "slg": 0.3944},  # == repl
    {"pa": 80, "ab": 72, "hr": 1, "r": 6, "obp": 0.260, "slg": 0.300},        # cameo
    {"pa": 0, "ab": 0, "hr": 0, "r": 0, "obp": 0.0, "slg": 0.0},              # empty
]
PITCHERS = [
    {"ip": 62 + 2 / 3, "so": 69, "era": 2.59, "whip": 0.99, "hr9": 0.574},   # Pearson 2019 AA
    {"ip": 200.0, "so": 240, "era": 2.80, "whip": 1.02, "hr9": 0.85},
    {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711},  # == repl
    {"ip": 30.0, "so": 45, "era": 1.90, "whip": 0.85, "hr9": 0.60},           # reliever
    {"ip": 0.0, "so": 0, "era": 0.0, "whip": 0.0, "hr9": 0.0},                # empty
]


def main() -> int:
    cases, expected = [], []
    for row in HITTERS:
        cases.append({"type": "H", "stats": row, "repl": REPL_H, "den": DEN,
                      "avgPA": AVG_PA, "avgIP": AVG_IP})
        expected.append(labels.hitter_sgp(row, REPL_H, DEN, AVG_PA))
    for row in PITCHERS:
        cases.append({"type": "P", "stats": row, "repl": REPL_P, "den": DEN,
                      "avgPA": AVG_PA, "avgIP": AVG_IP})
        expected.append(labels.pitcher_sgp(row, REPL_P, DEN, AVG_IP))

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cases, fh)
        case_file = fh.name
    try:
        proc = subprocess.run(["node", os.path.join(HERE, "js_side.js"), case_file],
                              capture_output=True, text=True, check=True)
    finally:
        os.unlink(case_file)
    got = json.loads(proc.stdout)

    worst, failures = 0.0, 0
    if len(got) != len(expected):
        print(f"FAIL - JS returned {len(got)} results for {len(expected)} cases")
        return 1
    for i, (py, js) in enumerate(zip(expected, got)):
        # NaN compares False against everything, so `diff > 1e-9` would let a
        # NaN on either side pass silently. Non-finite is always a failure.
        if js is None or not (math.isfinite(py) and math.isfinite(js)):
            failures += 1
            print(f"  NON-FINITE case {i}: python={py!r} js={js!r}")
            continue
        diff = abs(py - js)
        worst = max(worst, diff)
        if diff > 1e-9:
            failures += 1
            print(f"  MISMATCH case {i}: python={py!r} js={js!r} diff={diff:g}")
    print(f"parity: {len(cases)} cases, max abs diff {worst:.3e}, {failures} failures")
    if failures:
        print("FAIL - labels do not match shared.js; do not build on these labels")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
