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


def _features(metrics_row, stat_row):
    f = {k: metrics_row.get(k) for k in stuff_keys()}
    box = F.pitcher_features(stat_row)
    f.update({k: box[k] for k in BOX})
    f["age"] = stat_row.get("age")
    return f


def mlb_rows(table, values, stats, threshold):
    """One row per MLB pitcher with >= MIN_PITCHES tracked pitches in t and a valued
    season (25+ IP) in t+1. stats: {(player_id, season): StatsAPI pitcher row}."""
    rows = []
    for (pid, t), m in table.items():
        if (m.get("pitches") or 0) < MIN_PITCHES:
            continue
        nxt = values.get(pid, {}).get(t + 1)
        st = stats.get((pid, t))
        if nxt is None or st is None:
            continue
        rows.append({"player_id": pid, "season": t, "f": _features(m, st), "target": nxt[0],
                     "weight": float(nxt[1]), "useful": nxt[0] >= threshold})
    return rows


def later_outcome(values, pid, season):
    """(arrived, best value at WORKLOAD) over MLB seasons after `season` with 25+ IP."""
    vals = [v for s, (v, _) in values.get(pid, {}).items() if season < s <= LAST_OUTCOME_SEASON]
    return bool(vals), (max(vals) if vals else None)


def aaa_rows(table, stats, values, cohort_seasons, threshold, ip_history):
    """AAA pitcher-seasons with >= MIN_PITCHES tracked pitches in the cohort seasons,
    for pitchers not yet established in MLB, each pitcher's FIRST qualifying
    season only so nobody counts twice in the gate."""
    seen, rows = set(), []
    for pid, s in sorted(table, key=lambda k: (k[1], k[0])):
        m = table[(pid, s)]
        st = stats.get((pid, s))
        if (s not in cohort_seasons or pid in seen or (m.get("pitches") or 0) < MIN_PITCHES or st is None
                or pcohorts.prior_mlb_ip(ip_history, pid, s) >= pcohorts.ESTABLISHED_IP):
            continue
        seen.add(pid)
        arrived, best = later_outcome(values, pid, s)
        rows.append({"player_id": pid, "season": s, "f": _features(m, st), "arrived": arrived,
                     "target": best, "useful": best is not None and best >= threshold})
    return rows


def fit_translation(aaa, mlb, keys, min_pitches=MIN_PITCH_PAIR, n_boot=1000, seed=0):
    """Per-metric AAA->MLB flat offset from pitchers who threw at both levels in the
    SAME season, weighted by the smaller pitch count. The slope is reported, not
    applied (errors-in-variables; see step1.fit_translation)."""
    pairs = [p for p in aaa if p in mlb
             and (aaa[p].get("pitches") or 0) >= min_pitches and (mlb[p].get("pitches") or 0) >= min_pitches]
    rng = random.Random(seed)
    out = {}
    for k in keys:
        pts = [(aaa[p][k], mlb[p][k], min(aaa[p]["pitches"], mlb[p]["pitches"])) for p in pairs
               if aaa[p].get(k) is not None and mlb[p].get(k) is not None]
        if not pts:
            out[k] = {"n": 0, "offset": None, "lo": None, "hi": None, "slope": None}
            continue
        a, b, w = (np.array(col, dtype=float) for col in zip(*pts))
        d = b - a
        boots = []
        for _ in range(n_boot):
            i = [rng.randrange(len(d)) for _ in range(len(d))]
            boots.append(float(np.average(d[i], weights=w[i])))
        slope = float(np.polyfit(a, b, 1, w=np.sqrt(w))[0]) if len(pts) >= 3 and np.ptp(a) > 0 else None
        out[k] = {"n": len(pts), "offset": float(np.average(d, weights=w)),
                  "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5)), "slope": slope}
    return out
