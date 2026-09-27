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

DEFAULT = {"foul_tip_is_whiff": False, "count_bunts": True}

# No pull/straightaway/opposite: Savant's come from tracked launch direction, which
# game records lack; charted hit coordinates cap at r~0.87 vs Savant (spec, 3b parity).
BATTED_BALL_METRICS = [
    "exit_velocity_avg", "max_hit_speed", "avg_best_speed", "hard_hit_percent", "barrel_batted_rate",
    "sweet_spot_percent", "launch_angle_avg", "avg_distance",
    "groundballs_percent", "linedrives_percent", "flyballs_percent", "popups_percent",
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


def sweet_spot_weight(la):
    """Game-record launch angles are whole degrees, so a ball recorded at 8 or 32 is
    only half inside Savant's 8-32 window; counting it fully biased the rate +1.4 pts."""
    if la is None:
        return 0.0
    if 8.0 < la < 32.0:
        return 1.0
    return 0.5 if la in (8.0, 32.0) else 0.0


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
            a["bbe"].append(e)

    out = {}
    for b, a in acc.items():
        bb = a["bbe"]
        n = len(bb)
        # Savant keeps bunts in batted-ball rates and types but not in the EV/LA averages.
        swung = [x for x in bb if x.get("traj") not in BUNT_TRAJ]
        evs = sorted((x["ev"] for x in swung), reverse=True)
        las = [x["la"] for x in swung if x.get("la") is not None]
        las_all = [x["la"] for x in bb if x.get("la") is not None]
        traj = [BUNT_TRAJ.get(x.get("traj"), x.get("traj")) for x in bb]
        out[b] = {
            "exit_velocity_avg": _mean(evs),
            "max_hit_speed": max(x["ev"] for x in bb) if bb else None,
            "avg_best_speed": _mean(evs[:math.ceil(len(evs) / 2)]) if evs else None,
            "hard_hit_percent": _pct(sum(1 for x in bb if x["ev"] >= 95.0), n),
            "barrel_batted_rate": _pct(sum(1 for x in bb if is_barrel(x["ev"], x.get("la"))), n),
            "sweet_spot_percent": _pct(sum(sweet_spot_weight(la) for la in las_all), len(las_all)),
            "launch_angle_avg": _mean(las),
            "avg_distance": _mean([x["dist"] for x in bb if x.get("dist") is not None]),
            "groundballs_percent": _pct(traj.count("ground_ball"), n),
            "linedrives_percent": _pct(traj.count("line_drive"), n),
            "flyballs_percent": _pct(traj.count("fly_ball"), n),
            "popups_percent": _pct(traj.count("popup"), n),
            "whiff_percent": _pct(a["whiffs"], a["swings"]),
            "swing_percent": _pct(a["swings"], a["pitches"]),
            "oz_swing_percent": _pct(a["oz_sw"], a["oz"]),
            "z_swing_percent": _pct(a["iz_sw"], a["iz"]),
            "oz_contact_percent": _pct(a["oz_con"], a["oz_sw"]),
            "iz_contact_percent": _pct(a["iz_con"], a["iz_sw"]),
            "bbe": n, "swings": a["swings"], "pitches": a["pitches"],
        }
    return out
