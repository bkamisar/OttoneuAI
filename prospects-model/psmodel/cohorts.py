"""3c-hitters rows: every minor-league hitter-season-level from 2012, with the
features the base model uses and the player's MLB labels attached. Targets are
attached later, per vantage year, by walkforward.py -- never here.
"""
from . import features as F
from . import milb, statsapi

CURRENT_SEASON = 2026
PA_HISTORY_FIRST = 2005        # MLB PA before the first cohort, for the established cut
MILB_SEASONS = tuple(s for s in range(2012, CURRENT_SEASON + 1) if s != 2020)   # no 2020 MiLB season
LEVELS = (11, 12, 13, 14)
LEVEL_NAMES = {11: "AAA", 12: "AA", 13: "High-A", 14: "Single-A"}
LEVEL_FLAGS = {11: "is_aaa", 12: "is_aa", 13: "is_higha"}   # Single-A is the baseline
WHIFF_FIRST = 2012             # first season with minor-league swing data (plan A Task 1 probe)
MIN_PA = F.HIT_MIN_PA          # 150 at the level
ESTABLISHED_PA = 300           # prior MLB PA that makes him not a prospect

GROUPS = {
    "age_level": ["age", "is_aaa", "is_aa", "is_higha"],
    "contact": ["k", "whiff", "swstr"],
    "approach": ["bb", "obp", "swing"],
    "power": ["iso", "hr_pa", "slg"],
    "speed": ["sb_pa"],
    "trajectory": ["repeat_level", "multi_level", "pa"],
}
BINARY = {"is_aaa", "is_aa", "is_higha", "repeat_level", "multi_level"}
_BOX = ("age", "pa", "k", "bb", "iso", "hr_pa", "obp", "slg", "sb_pa", "whiff", "swing", "swstr")

# Tree patterns from plan A, tested as explicit terms (products of standardized features).
LEADS = {"age_x_slg": ("age", "slg"), "swstr_x_slg": ("swstr", "slg")}


def add_products(rows):
    for r in rows:
        f = r["f"]
        for name, (a, b) in LEADS.items():
            f[name] = f[a] * f[b] if f.get(a) is not None and f.get(b) is not None else None
    return rows


def mlb_pa_history(first=PA_HISTORY_FIRST, last=CURRENT_SEASON):
    """{player_id: {season: MLB PA}}."""
    out = {}
    for s in range(first, last + 1):
        for r in statsapi.season_stats(s, "hitting", statsapi.MLB):
            out.setdefault(r["player_id"], {})[s] = r["pa"]
    return out


def prior_mlb_pa(history, pid, season):
    return sum(pa for s, pa in history.get(pid, {}).items() if s < season)


def load_milb(seasons=MILB_SEASONS, levels=LEVELS):
    rows = []
    for s in seasons:
        for sid in levels:
            rows += milb.season_rows(s, sid, "hitting", advanced=s >= WHIFF_FIRST)
    return rows


def previous_season(season):
    return 2019 if season == 2021 else season - 1


def build_rows(milb_rows, pa_history, mlb_seasons):
    """Rows {player_id, name, season, sport_id, f, mlb} for hitters with >=150 PA at
    a level who weren't established in MLB. Repeat/multi-level flags look at ALL
    minor-league rows (any PA). Continuous features are z-scored within
    level-season, so age becomes age relative to the level."""
    seen = {}
    for r in milb_rows:
        seen.setdefault((r["player_id"], r["season"]), set()).add(r["sport_id"])
    rows = []
    for r in milb_rows:
        pid, s = r["player_id"], r["season"]
        if r["pa"] < MIN_PA or prior_mlb_pa(pa_history, pid, s) >= ESTABLISHED_PA:
            continue
        base = F.hitter_features(r)
        f = {k: base[k] for k in _BOX}
        for sid, name in LEVEL_FLAGS.items():
            f[name] = 1.0 if r["sport_id"] == sid else 0.0
        f["repeat_level"] = 1.0 if r["sport_id"] in seen.get((pid, previous_season(s)), ()) else 0.0
        f["multi_level"] = 1.0 if len(seen[(pid, s)]) > 1 else 0.0
        rows.append({"player_id": pid, "name": r["name"], "season": s, "sport_id": r["sport_id"],
                     "age_raw": r.get("age"), "f": f, "mlb": mlb_seasons.get(pid, [])})
    F.standardize_within(rows, [k for g in GROUPS.values() for k in g if k not in BINARY])
    return rows
