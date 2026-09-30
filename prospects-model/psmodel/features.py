"""Per-row features, z-scored within groups.

Within-level-season z-scores are what make a 2016 AA line comparable to a 2019
AAA line, and what absorb derived CSW's constant +1 pt offset. The 3c and pitcher
models go one step further and z-score within (level, season, league)
(standardize_within_league): the Pacific Coast League's offense is not the
International League's. Each group is a single season, so the 2021 league-level
changes don't matter. standardize_within stays for whiff_test.py.
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


LEAGUE_MIN_ROWS = 30


def _group_stats(members, keys):
    out = {}
    for k in keys:
        vals = [m["f"][k] for m in members if m["f"].get(k) is not None]
        out[k] = (statistics.fmean(vals) if vals else 0.0,
                  statistics.pstdev(vals) if len(vals) > 1 else 0.0)
    return out


def standardize_within_league(rows, keys, min_rows=LEAGUE_MIN_ROWS):
    """z-score each feature within its (level, season, league) group, in place. A
    row with no league, or in a league-season under min_rows, uses its (level,
    season) group. All group stats are taken before any value is replaced."""
    keys = [k for k in keys if k not in NOT_STANDARDIZED]
    level, league = {}, {}
    for r in rows:
        level.setdefault((r["sport_id"], r["season"]), []).append(r)
        if r.get("league") is not None:
            league.setdefault((r["sport_id"], r["season"], r["league"]), []).append(r)
    stats = {g: _group_stats(m, keys) for g, m in level.items()}
    stats.update({g: _group_stats(m, keys) for g, m in league.items() if len(m) >= min_rows})
    for r in rows:
        st = stats.get((r["sport_id"], r["season"], r.get("league"))) or stats[(r["sport_id"], r["season"])]
        for k in keys:
            v = r["f"].get(k)
            mu, sd = st[k]
            r["f"][k] = None if v is None else ((v - mu) / sd if sd else 0.0)
    return rows
