"""Step 1 of the prospect model: what hitter tracking metrics are worth, learned
on MLB and translated to AAA.

Tracking reached AAA only in 2022-23, too late for prospects with known careers,
so "batted-ball profile -> value" is learned from MLB (thousands of hitter-seasons
since 2015) and AAA readings are moved onto the MLB scale.
Spec: docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md.
"""
import csv

from . import features as F
from .savant import SPRAY_FIELDS

GROUPS = {
    "power": ["exit_velocity_avg", "avg_best_speed", "max_hit_speed", "hard_hit_percent", "barrel_batted_rate"],
    "launch": ["launch_angle_avg", "sweet_spot_percent", "groundballs_percent", "linedrives_percent",
               "flyballs_percent", "popups_percent"],
    "contact": ["whiff_percent", "iz_contact_percent", "oz_contact_percent"],
    "discipline": ["swing_percent", "oz_swing_percent", "z_swing_percent"],
    "spray": list(SPRAY_FIELDS),
}
BOX = ["k", "bb", "iso", "hr_pa", "obp", "slg"]
FULL_PA = 600
MIN_BBE = 100          # batted balls in season t for a row's metrics to count
MIN_PA_NEXT = 100      # the spec's peak-eligible floor, applied to the outcome season


def tracking_keys(groups=None):
    return [k for g in (GROUPS if groups is None else groups) for k in GROUPS[g]]


def _num(v):
    return None if v in (None, "") else float(v)


def load_table(path):
    """cache/{aaa,mlb}_tracking.csv -> {(player_id, season): {column: float | None}}."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(int(r["player_id"]), int(r["season"]))] = {
                k: _num(v) for k, v in r.items() if k not in ("player_id", "season", "level")}
    return out


def hitter_seasons(labels):
    """{player_id: {season: (value, pa)}} from dataset.load_labels output."""
    return {pid: {r["season"]: (r["value"], r["pa"]) for r in rows}
            for (pid, typ), rows in labels.items() if typ == "H"}


def value_at_full_time(value, pa):
    """SGP at 600 PA. Exact, because hitter_sgp scales linearly with playing time."""
    if not pa or pa < MIN_PA_NEXT:
        return None
    return value * FULL_PA / pa


def _features(metrics_row, stat_row):
    f = {k: metrics_row.get(k) for k in tracking_keys()}
    box = F.hitter_features(stat_row)
    f.update({k: box[k] for k in BOX})
    f["age"] = stat_row.get("age")
    return f


def mlb_rows(table, seasons, stats, threshold):
    """One row per MLB hitter with >=100 batted balls in t and >=100 PA in t+1.

    stats: {(player_id, season): StatsAPI hitter row} -- age and box score in t."""
    rows = []
    for (pid, t), m in table.items():
        if (m.get("bbe") or 0) < MIN_BBE:
            continue
        nxt = seasons.get(pid, {}).get(t + 1)
        st = stats.get((pid, t))
        target = value_at_full_time(*nxt) if nxt else None
        if target is None or st is None:
            continue
        rows.append({"player_id": pid, "season": t, "f": _features(m, st), "target": target,
                     "weight": float(nxt[1]), "useful": target >= threshold})
    return rows


def complete(rows, keys):
    return [r for r in rows if all(r["f"].get(k) is not None for k in keys)]
