"""Spray direction from charted hit coordinates (Gameday coordX/coordY), with plan
A's geometry: home plate at (125.42, 198.27), angle mirrored for left-handed
batters, pulled = more than 15 degrees to the pull side. Plan A found overall
pull% from these coordinates caps near r 0.96 vs Savant; pulled_air_parity.py
tests whether pull% x FB% does better.
"""
import math

from .metrics import IN_PLAY

HOME_X, HOME_Y = 125.42, 198.27


def angle(e):
    x, y, side = e.get("hc_x"), e.get("hc_y"), e.get("bat_side")
    if x is None or y is None or side not in ("R", "L") or y >= HOME_Y:
        return None
    a = math.degrees(math.atan((x - HOME_X) / (HOME_Y - y)))
    return -a if side == "L" else a


def pull_and_fb(events, pull_deg=15.0):
    """{batter: (pull %, fly-ball %, batted balls)}. Bunts are included, as in Savant's rates."""
    acc = {}
    for e in events:
        if e.get("code") not in IN_PLAY or e.get("ev") is None:
            continue
        a = acc.setdefault(e["batter"], [0, 0, 0, 0])      # batted balls, with angle, pulled, fly balls
        a[0] += 1
        ang = angle(e)
        if ang is not None:
            a[1] += 1
            a[2] += ang < -pull_deg
        a[3] += e.get("traj") == "fly_ball"
    return {b: (100.0 * a[2] / a[1] if a[1] else None, 100.0 * a[3] / a[0], a[0]) for b, a in acc.items()}
