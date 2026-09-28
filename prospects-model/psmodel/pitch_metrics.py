"""Pitcher stuff metrics, named and defined to match Baseball Savant's pitcher
leaderboard, so MLB history (from Savant) and AAA (computed here from game
records) mean the same thing.

Built on each pitcher's PRIMARY fastball -- the most-thrown of four-seam (FF),
sinker (SI) and cutter (FC) -- so sinkerballers are measured on the pitch they
live on. Horizontal break is a magnitude: its sign flips with handedness.
Uncertain definitions are variant parameters; parity_pitch.py runs them on the
2024 MLB season and keeps whichever reproduces Savant.
"""
from .metrics import BUNT_CODES, CONTACT_CODES, WHIFF_CODES

FASTBALLS = ("FF", "SI", "FC")
FB_METRICS = ["fb_speed", "fb_spin", "fb_ivb", "fb_hb"]
BREAKING_METRICS = ["breaking_speed", "breaking_spin"]
PITCH_METRICS = FB_METRICS + BREAKING_METRICS + ["whiff_percent"]
BREAKING_WIDE = ("SL", "ST", "SV", "CU", "KC", "CS")
BREAKING_NARROW = ("SL", "ST", "CU", "KC")
# The whiff definition is the hitter parity's chosen variant (cache/tracking_definitions.json).
DEFAULT = {"breaking": BREAKING_WIDE, "movement": "breaks", "foul_tip_is_whiff": True, "count_bunts": True}
MIN_FB = 50          # primary fastballs thrown before the fastball metrics count
MIN_BREAKING = 30    # breaking balls thrown before the breaking metrics count


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pitcher_metrics(pitches, variant=None):
    """{pitcher_id: {metric: value, 'pitches', 'swings', 'fb_n', 'breaking_n'}} for
    the pitches given (normally one level-season)."""
    v = dict(DEFAULT, **(variant or {}))
    hx, vz = ("hb", "ivb") if v["movement"] == "breaks" else ("pfx_x", "pfx_z")
    acc = {}
    for p in pitches:
        pid = p.get("pitcher")
        if pid is None:
            continue
        a = acc.setdefault(pid, {"pitches": 0, "swings": 0, "whiffs": 0, "by": {}})
        a["pitches"] += 1
        code = p.get("code")
        whiff = code in WHIFF_CODES or (v["foul_tip_is_whiff"] and code == "T")
        contact = code in CONTACT_CODES and not whiff
        if code in BUNT_CODES and not v["count_bunts"]:
            whiff = contact = False
        a["swings"] += whiff or contact
        a["whiffs"] += whiff
        a["by"].setdefault(p.get("type"), []).append(p)

    out = {}
    for pid, a in acc.items():
        fb = a["by"].get(max(FASTBALLS, key=lambda t: len(a["by"].get(t, ()))), [])
        fb = fb if len(fb) >= MIN_FB else []
        brk = [p for t in v["breaking"] for p in a["by"].get(t, ())]
        brk = brk if len(brk) >= MIN_BREAKING else []
        hb = _mean([p.get(hx) for p in fb])
        out[pid] = {
            "fb_speed": _mean([p.get("speed") for p in fb]),
            "fb_spin": _mean([p.get("spin") for p in fb]),
            "fb_ivb": _mean([p.get(vz) for p in fb]),
            "fb_hb": abs(hb) if hb is not None else None,
            "breaking_speed": _mean([p.get("speed") for p in brk]),
            "breaking_spin": _mean([p.get("spin") for p in brk]),
            "whiff_percent": 100.0 * a["whiffs"] / a["swings"] if a["swings"] else None,
            "pitches": a["pitches"], "swings": a["swings"], "fb_n": len(fb), "breaking_n": len(brk),
        }
    return out
