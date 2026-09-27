"""Per-row features for the whiff test, normalized within (level, season).

Within-(sport_id, season) z-scores are what make a 2016 AA line comparable to a
2019 AAA line, and what absorb derived CSW's constant +1 pt offset. Never
normalize by league name: leagues changed levels in 2021.
"""
import statistics

HIT_MIN_PA = 150
PIT_MIN_IP = 40.0

BASE_H = ["age", "pa", "k", "bb", "iso", "hr_pa", "obp", "slg", "sb_pa", "is_aaa"]
FAMILY_H = ["whiff", "swing", "swstr"]
BASE_P = ["age", "ip", "k", "bb", "kbb", "hr9", "era", "whip", "is_aaa"]
FAMILY_P = ["whiff", "swstr", "csw"]
NOT_STANDARDIZED = {"is_aaa"}


def _ratio(a, b):
    return (a / b) if (a is not None and b) else None


def hitter_features(r):
    avg = _ratio(r["h"], r["ab"])
    return {
        "age": r.get("age"), "pa": r["pa"],
        "k": _ratio(r["so"], r["pa"]), "bb": _ratio(r["bb"], r["pa"]),
        "iso": (r["slg"] - avg) if avg is not None else None,
        "hr_pa": _ratio(r["hr"], r["pa"]), "obp": r["obp"], "slg": r["slg"],
        "sb_pa": _ratio(r["sb"], r["pa"]),
        "whiff": _ratio(r.get("whiffs", 0), r.get("swings", 0)),
        "swing": _ratio(r.get("swings", 0), r.get("np", 0)),
        "swstr": _ratio(r.get("whiffs", 0), r.get("np", 0)),
        "is_aaa": 1.0 if r["sport_id"] == 11 else 0.0,
    }


def pitcher_features(r):
    k = _ratio(r["so"], r.get("bf", 0))
    bb = _ratio(r["bb"], r.get("bf", 0))
    np_ = r.get("np", 0)
    # Every swing is a strike, so called = strikes - swings. Validated vs
    # pitch-by-pitch at r = 0.994 with a constant +1 pt offset (bunts).
    called = (r.get("strikes", 0) - r.get("swings", 0)) if np_ else None
    return {
        "age": r.get("age"), "ip": r["ip"], "k": k, "bb": bb,
        "kbb": (k - bb) if (k is not None and bb is not None) else None,
        "hr9": r["hr9"], "era": r["era"], "whip": r["whip"],
        "whiff": _ratio(r.get("whiffs", 0), r.get("swings", 0)),
        "swstr": _ratio(r.get("whiffs", 0), np_),
        "csw": _ratio(called + r.get("whiffs", 0), np_) if called is not None else None,
        "is_aaa": 1.0 if r["sport_id"] == 11 else 0.0,
    }


def standardize_within(rows, keys, group=("sport_id", "season")):
    """z-score each feature within its (level, season) group, in place."""
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[g] for g in group), []).append(r)
    for members in groups.values():
        for k in keys:
            if k in NOT_STANDARDIZED:
                continue
            vals = [m["f"][k] for m in members if m["f"].get(k) is not None]
            mu = statistics.fmean(vals) if vals else 0.0
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            for m in members:
                v = m["f"].get(k)
                m["f"][k] = None if v is None else ((v - mu) / sd if sd else 0.0)
    return rows
