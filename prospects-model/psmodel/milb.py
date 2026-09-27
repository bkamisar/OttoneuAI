"""Minor-league season rows: basic stats plus seasonAdvanced swing data, one row
per player x season x level.

The Mexican League (classified AAA until 2021) is excluded. A player who changed
teams within one level can appear as several StatsAPI splits; those are combined
so each player has at most one row per (season, level).
"""
from . import statsapi

MEX_LEAGUES = {"MEX", "Mexican League"}
_HIT_SUM = ("g", "pa", "ab", "h", "hr", "r", "bb", "so", "sb", "np", "hbp")
_PIT_SUM = ("g", "gs", "ip", "so", "bb", "hr", "np", "strikes", "bf")


def _combine(rows, group):
    out = dict(rows[0])
    if len(rows) == 1:
        return out
    for k in (_HIT_SUM if group == "hitting" else _PIT_SUM):
        out[k] = sum(r.get(k) or 0 for r in rows)
    if group == "hitting":
        pa, ab = out["pa"] or 1, out["ab"] or 1
        out["obp"] = sum(r["obp"] * r["pa"] for r in rows) / pa
        out["slg"] = sum(r["slg"] * r["ab"] for r in rows) / ab
    else:
        ip = out["ip"] or 1
        out["era"] = sum(r["era"] * r["ip"] for r in rows) / ip
        out["whip"] = sum(r["whip"] * r["ip"] for r in rows) / ip
        out["hr9"] = out["hr"] * 9.0 / out["ip"] if out["ip"] else 0.0
    out["team"] = "multiple"
    return out


def combine_by_player(rows, group):
    by = {}
    for r in rows:
        by.setdefault(r["player_id"], []).append(r)
    return [_combine(v, group) for v in by.values()]


def season_rows(season, sport_id, group, advanced=True):
    """advanced=False skips seasonAdvanced (swing data): swings/whiffs become None,
    for seasons where the endpoint has no data."""
    basic = [r for r in statsapi.season_stats(season, group, sport_id)
             if r.get("league") not in MEX_LEAGUES]
    rows = combine_by_player(basic, group)
    adv = statsapi.season_advanced(season, group, sport_id) if advanced else None
    for r in rows:
        a = adv.get(r["player_id"], {}) if adv is not None else None
        r["swings"] = a.get("swings", 0) if a is not None else None
        r["whiffs"] = a.get("whiffs", 0) if a is not None else None
    return rows
