"""Hitter tracking metrics, named and defined to match Baseball Savant's
leaderboard columns, so MLB history (from Savant) and AAA (computed here from
game records) mean the same thing.

Every definition that is not certain is a variant parameter; parity_tracking.py
runs them all on the 2024 MLB season and keeps whichever reproduces Savant.
"""
import math

WHIFF_CODES = {"S", "W", "M", "Q"}                         # swinging strike (+blocked), missed bunt, swinging pitchout
CONTACT_CODES = {"F", "T", "L", "O", "R", "X", "D", "E"}   # fouls, foul tip, foul bunt/tip bunt, foul pitchout, in play
IN_PLAY = {"X", "D", "E"}
BUNT_CODES = {"L", "M", "O"}
BUNT_TRAJ = {"bunt_grounder": "ground_ball", "bunt_popup": "popup", "bunt_line_drive": "line_drive"}

DEFAULT = {"foul_tip_is_whiff": False, "count_bunts": True, "pull_deg": 15.0}

BATTED_BALL_METRICS = [
    "exit_velocity_avg", "max_hit_speed", "avg_best_speed", "hard_hit_percent", "barrel_batted_rate",
    "sweet_spot_percent", "launch_angle_avg", "avg_distance",
    "groundballs_percent", "linedrives_percent", "flyballs_percent", "popups_percent",
    "pull_percent", "straightaway_percent", "opposite_percent",
]
DISCIPLINE_METRICS = [
    "whiff_percent", "swing_percent", "oz_swing_percent", "z_swing_percent",
    "oz_contact_percent", "iz_contact_percent",
]
HITTER_METRICS = BATTED_BALL_METRICS + DISCIPLINE_METRICS


def is_barrel(ev, la):
    """Statcast barrel: EV >= 98 mph with a launch-angle window that widens with
    EV -- 26-30 deg at 98 mph out to 8-50 deg at 116 mph and above. Savant's exact
    window is unpublished; parity_tracking.py measures how close this gets."""
    if ev is None or la is None or ev < 98.0:
        return False
    x = min(ev, 116.0) - 98.0
    return (26.0 - x) <= la <= (30.0 + x * (20.0 / 18.0))


def direction(e, pull_deg):
    """'pull' | 'straight' | 'oppo' from Savant-style spray angle, mirrored for
    left-handed batters; None when coordinates or handedness are missing."""
    x, y, side = e.get("hc_x"), e.get("hc_y"), e.get("bat_side")
    if x is None or y is None or side not in ("R", "L") or y >= 198.27:
        return None
    angle = math.degrees(math.atan((x - 125.42) / (198.27 - y)))
    if side == "L":
        angle = -angle
    if angle < -pull_deg:
        return "pull"
    if angle > pull_deg:
        return "oppo"
    return "straight"


def _pct(n, d):
    return 100.0 * n / d if d else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def hitter_metrics(events, variant=None):
    """{batter_id: {metric: value, 'bbe', 'swings', 'pitches'}} for the events given
    (normally one level-season)."""
    v = dict(DEFAULT, **(variant or {}))
    acc = {}
    for e in events:
        b = e.get("batter")
        if b is None:
            continue
        a = acc.setdefault(b, {"pitches": 0, "swings": 0, "whiffs": 0, "iz": 0, "oz": 0,
                               "iz_sw": 0, "oz_sw": 0, "iz_con": 0, "oz_con": 0, "bbe": []})
        code = e.get("code")
        a["pitches"] += 1
        whiff = code in WHIFF_CODES or (v["foul_tip_is_whiff"] and code == "T")
        contact = code in CONTACT_CODES and not whiff
        if code in BUNT_CODES and not v["count_bunts"]:
            whiff = contact = False
        swing = whiff or contact
        z = e.get("zone")
        a["swings"] += swing
        a["whiffs"] += whiff
        if z is not None and 1 <= z <= 9:
            a["iz"] += 1; a["iz_sw"] += swing; a["iz_con"] += contact
        elif z is not None and z >= 11:
            a["oz"] += 1; a["oz_sw"] += swing; a["oz_con"] += contact
        if code in IN_PLAY and e.get("ev") is not None:
            if e.get("traj") in BUNT_TRAJ and not v["count_bunts"]:
                continue
            a["bbe"].append(e)

    out = {}
    for b, a in acc.items():
        bb = a["bbe"]
        n = len(bb)
        evs = sorted((x["ev"] for x in bb), reverse=True)
        las = [x["la"] for x in bb if x.get("la") is not None]
        traj = [BUNT_TRAJ.get(x.get("traj"), x.get("traj")) for x in bb]
        spray = [d for d in (direction(x, v["pull_deg"]) for x in bb) if d]
        out[b] = {
            "exit_velocity_avg": _mean(evs),
            "max_hit_speed": evs[0] if evs else None,
            "avg_best_speed": _mean(evs[:math.ceil(n / 2)]) if n else None,
            "hard_hit_percent": _pct(sum(1 for s in evs if s >= 95.0), n),
            "barrel_batted_rate": _pct(sum(1 for x in bb if is_barrel(x["ev"], x.get("la"))), n),
            "sweet_spot_percent": _pct(sum(1 for la in las if 8.0 <= la <= 32.0), len(las)),
            "launch_angle_avg": _mean(las),
            "avg_distance": _mean([x["dist"] for x in bb if x.get("dist") is not None]),
            "groundballs_percent": _pct(traj.count("ground_ball"), n),
            "linedrives_percent": _pct(traj.count("line_drive"), n),
            "flyballs_percent": _pct(traj.count("fly_ball"), n),
            "popups_percent": _pct(traj.count("popup"), n),
            "pull_percent": _pct(spray.count("pull"), len(spray)),
            "straightaway_percent": _pct(spray.count("straight"), len(spray)),
            "opposite_percent": _pct(spray.count("oppo"), len(spray)),
            "whiff_percent": _pct(a["whiffs"], a["swings"]),
            "swing_percent": _pct(a["swings"], a["pitches"]),
            "oz_swing_percent": _pct(a["oz_sw"], a["oz"]),
            "z_swing_percent": _pct(a["iz_sw"], a["iz"]),
            "oz_contact_percent": _pct(a["oz_con"], a["oz_sw"]),
            "iz_contact_percent": _pct(a["iz_con"], a["iz_sw"]),
            "bbe": n, "swings": a["swings"], "pitches": a["pitches"],
        }
    return out
