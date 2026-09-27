"""Joins minor-league feature rows to MLB outcomes for the whiff test."""
import csv
import statistics

from . import features as F
from . import targets

CURRENT_SEASON = 2026
ESTABLISHED_PA = 300    # MLB volume before the row's season that makes him not a prospect
ESTABLISHED_IP = 100
# "Good enough to start for one of 12 teams": 12 teams x 12 lineup slots for
# hitters; 12 x ~10 arms under the 1,500 IP cap for pitchers.
USEFUL_N = {"H": 144, "P": 120}


def load_labels(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault((int(r["player_id"]), r["type"]), []).append({
                "season": int(r["season"]), "value": float(r["value"]),
                "pa": int(float(r["pa"])), "ip": float(r["ip"])})
    return out


def useful_threshold(labels, typ, first=2015, last=2025):
    """Median over full seasons of the Nth-best season value by type."""
    by_season = {}
    for (_pid, t), rows in labels.items():
        if t != typ:
            continue
        for r in rows:
            if first <= r["season"] <= last and r["season"] != 2020:
                by_season.setdefault(r["season"], []).append(r["value"])
    n = USEFUL_N[typ]
    cuts = [sorted(v, reverse=True)[n - 1] for v in by_season.values() if len(v) >= n]
    if not cuts:
        raise ValueError(f"no season has {n} {typ} labels")
    return statistics.median(cuts)


def _prior_volume(mlb_rows, season, typ):
    return sum((r["pa"] if typ == "H" else r["ip"]) for r in mlb_rows if r["season"] < season)


def build(milb_rows, typ, labels, threshold):
    """Dataset rows {player_id, name, season, sport_id, f, target, weight, useful}.
    Applies the volume floor and drops established major leaguers (rehab stints)."""
    feat = F.hitter_features if typ == "H" else F.pitcher_features
    limit = ESTABLISHED_PA if typ == "H" else ESTABLISHED_IP
    out = []
    for r in milb_rows:
        if typ == "H" and r["pa"] < F.HIT_MIN_PA:
            continue
        if typ == "P" and r["ip"] < F.PIT_MIN_IP:
            continue
        mlb = labels.get((r["player_id"], typ), [])
        if _prior_volume(mlb, r["season"], typ) >= limit:
            continue
        t = targets.build_target(mlb, CURRENT_SEASON, snapshot_season=r["season"])
        if not t["labeled"]:
            continue
        out.append({"player_id": r["player_id"], "name": r["name"], "season": r["season"],
                    "sport_id": r["sport_id"], "f": feat(r), "target": t["peak_value"],
                    "weight": t["completeness"], "useful": t["peak_value"] >= threshold})
    return out


def complete_cases(rows, keys):
    """Both models must see IDENTICAL rows, or a 'win' could just be a different
    sample. Drop any row missing any feature in the union."""
    return [r for r in rows if all(r["f"].get(k) is not None for k in keys)]
