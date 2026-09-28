"""Pitcher stuff score (P-C): what pitch tracking is worth, learned on MLB and
translated to AAA -- the pitcher counterpart of step1.py.

Target: the NEXT MLB season's line valued at a fixed WORKLOAD with the site's
SGP formula (labels.pitcher_sgp) -- strikeouts scaled to the workload, ERA / WHIP
/ HR9 as they were, replacement per season as in build_labels. Starters and
relievers are judged on the same scale; how many innings they get is the base
model's job (its role features).
Spec: docs/superpowers/specs/2026-09-28-pitchers-design.md, "Stuff layer design".
"""
import random

import numpy as np

from . import context, labels, pcohorts
from . import features as F

GROUPS = {
    "velocity": ["fb_speed"],
    "fastball_shape": ["fb_spin", "fb_ivb", "fb_hb"],
    "breaking": ["breaking_speed", "breaking_spin"],
    "whiff": ["whiff_percent"],
}
BOX = ["k", "bb"]
WORKLOAD = 100.0         # innings every pitcher's rate line is valued at
MIN_IP_NEXT = 25.0       # targets.MIN_IP, applied to the outcome season
MIN_PITCHES = 300        # tracked pitches in season t for a row's metrics to count
MIN_PITCH_PAIR = 150     # pitches at EACH level for a same-season translation pair
USEFUL_RANK = 120        # 12 teams x ~10 arms
LAST_OUTCOME_SEASON = 2026


def stuff_keys(groups=None):
    return [k for g in (GROUPS if groups is None else groups) for k in GROUPS[g]]


def value_at_workload(row, repl, den, avg_ip):
    """Site SGP of a pitcher's rate line over WORKLOAD innings; None under MIN_IP_NEXT."""
    ip = row.get("ip") or 0.0
    if ip < MIN_IP_NEXT:
        return None
    line = {"ip": WORKLOAD, "so": row["so"] * WORKLOAD / ip,
            "era": row["era"], "whip": row["whip"], "hr9": row["hr9"]}
    return labels.pitcher_sgp(line, repl, den, avg_ip)


def season_values(stats_by_season, den):
    """{player_id: {season: (value at WORKLOAD, ip)}} from StatsAPI MLB pitching rows."""
    _, avg_ip = context.league_averages()
    out = {}
    for s, rows in stats_by_season.items():
        repl = context.pitcher_replacement(rows, context.season_fraction(s))
        for r in rows:
            v = value_at_workload(r, repl, den, avg_ip)
            if v is not None:
                out.setdefault(r["player_id"], {})[s] = (v, r["ip"])
    return out


def useful_threshold(values):
    """Median across seasons of the USEFUL_RANK-th best value at WORKLOAD."""
    by = {}
    for seasons in values.values():
        for s, (v, _) in seasons.items():
            by.setdefault(s, []).append(v)
    return float(np.median([sorted(vs, reverse=True)[USEFUL_RANK - 1]
                            for vs in by.values() if len(vs) >= USEFUL_RANK]))
