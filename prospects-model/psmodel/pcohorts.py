"""Pitcher rows: every minor-league pitcher-season-level from 2012 with 30+ IP at
the level, for pitchers not yet established in MLB, with the features the pitcher
base model tests and the pitcher's MLB labels attached. Mirrors cohorts.py.
Targets are attached later, per vantage, by walkforward.py -- rows carry typ 'P'
so the as-of targets use the pitcher line (top 120, 25 IP).
"""
from . import cohorts, milb, statsapi
from . import features as F

# 30 IP at the level (~130 batters faced, close to hitters' 150 PA). Measured
# 2026-09-28 on coverage only: 40 IP per level dropped ~21% of reliever seasons,
# because promoted relievers split their innings across levels; 30 drops ~6%.
MIN_IP = 30.0
ESTABLISHED_IP = 100.0         # prior MLB IP that ends prospect status (dataset.ESTABLISHED_IP)

GROUPS = {
    "age_level": ["age", "is_aaa", "is_aa", "is_higha"],
    "strikeouts": ["k", "whiff", "swstr", "csw"],
    "control": ["bb"],
    "run_prevention": ["era", "whip", "hr9"],
    "role": ["gs_share", "ip_per_g", "ip"],
    "trajectory": ["repeat_level", "multi_level"],
}
BINARY = {"is_aaa", "is_aa", "is_higha", "repeat_level", "multi_level"}
LEADS = {"age_x_k": ("age", "k"), "age_x_csw": ("age", "csw")}   # P-A tree leads (rating), tested in P-D
_BOX = ("age", "ip", "k", "bb", "era", "whip", "hr9", "whiff", "swstr", "csw")


def mlb_ip_history(first=cohorts.PA_HISTORY_FIRST, last=cohorts.CURRENT_SEASON):
    """{player_id: {season: MLB IP}}. MLB season stats are one row per player-season."""
    out = {}
    for s in range(first, last + 1):
        for r in statsapi.season_stats(s, "pitching", statsapi.MLB):
            out.setdefault(r["player_id"], {})[s] = r["ip"]
    return out


def prior_mlb_ip(history, pid, season):
    return sum(ip for s, ip in history.get(pid, {}).items() if s < season)


def add_products(rows):
    """The lead terms as products of the standardized features (cohorts.add_products)."""
    for r in rows:
        f = r["f"]
        for name, (a, b) in LEADS.items():
            f[name] = f[a] * f[b] if f.get(a) is not None and f.get(b) is not None else None
    return rows


def load_milb(seasons=cohorts.MILB_SEASONS, levels=cohorts.LEVELS):
    rows = []
    for s in seasons:
        for sid in levels:
            rows += milb.season_rows(s, sid, "pitching", advanced=True)
    return rows


def build_rows(milb_rows, ip_history, mlb_seasons):
    """Rows {player_id, name, season, sport_id, typ, age_raw, f, mlb} for pitchers
    with 30+ IP at a level who weren't established in MLB. Continuous features are
    z-scored within level-season-league, as for hitters."""
    seen = {}
    for r in milb_rows:
        seen.setdefault((r["player_id"], r["season"]), set()).add(r["sport_id"])
    rows = []
    for r in milb_rows:
        pid, s = r["player_id"], r["season"]
        if r["ip"] < MIN_IP or prior_mlb_ip(ip_history, pid, s) >= ESTABLISHED_IP:
            continue
        base = F.pitcher_features(r)
        f = {k: base[k] for k in _BOX}
        for sid, name in cohorts.LEVEL_FLAGS.items():
            f[name] = 1.0 if r["sport_id"] == sid else 0.0
        f["gs_share"] = r["gs"] / r["g"] if r.get("g") else None
        f["ip_per_g"] = r["ip"] / r["g"] if r.get("g") else None
        f["repeat_level"] = 1.0 if r["sport_id"] in seen.get((pid, cohorts.previous_season(s)), ()) else 0.0
        f["multi_level"] = 1.0 if len(seen[(pid, s)]) > 1 else 0.0
        rows.append({"player_id": pid, "name": r["name"], "season": s, "sport_id": r["sport_id"],
                     "league": r.get("league"), "typ": "P", "age_raw": r.get("age"), "start_share": r["gs"] / r["g"] if r.get("g") else None,
                     "f": f, "mlb": mlb_seasons.get(pid, [])})
    F.standardize_within_league(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
    return rows
