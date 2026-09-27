"""Step 1 of the prospect model: what hitter tracking metrics are worth, learned
on MLB and translated to AAA.

Tracking reached AAA only in 2022-23, too late for prospects with known careers,
so "batted-ball profile -> value" is learned from MLB (thousands of hitter-seasons
since 2015) and AAA readings are moved onto the MLB scale.
Spec: docs/superpowers/specs/2026-09-27-step1-tracking-score-design.md.
"""
import csv
import random

import numpy as np
from scipy.stats import spearmanr

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
MIN_BBE_PAIR = 50      # batted balls at EACH level for a same-season translation pair
LAST_OUTCOME_SEASON = 2026


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


def fit_translation(aaa, mlb, keys, min_bbe=MIN_BBE_PAIR, n_boot=1000, seed=0):
    """Per-metric AAA->MLB offset from hitters with both levels in the SAME season.

    A flat offset only. The MLB-on-AAA slope is reported, not applied: sampling
    noise in call-up-sized samples pulls it below 1 (errors-in-variables) whether
    or not the levels truly scale differently, so no held-out test can separate
    a real scale from noise."""
    pairs = [p for p in aaa if p in mlb
             and (aaa[p].get("bbe") or 0) >= min_bbe and (mlb[p].get("bbe") or 0) >= min_bbe]
    rng = random.Random(seed)
    out = {}
    for k in keys:
        pts = [(aaa[p][k], mlb[p][k], min(aaa[p]["bbe"], mlb[p]["bbe"])) for p in pairs
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
                  "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5)),
                  "slope": slope}
    return out


def translate(f, translation):
    """AAA feature dict -> MLB scale; metrics without an offset pass through."""
    out = dict(f)
    for k, t in translation.items():
        if out.get(k) is not None and t.get("offset") is not None:
            out[k] = out[k] + t["offset"]
    return out


def later_outcome(seasons, pid, season):
    """(arrived, best value at 600 PA) over MLB seasons after `season` with >=100 PA."""
    vals = [value_at_full_time(v, pa) for s, (v, pa) in seasons.get(pid, {}).items()
            if season < s <= LAST_OUTCOME_SEASON]
    vals = [x for x in vals if x is not None]
    return (bool(vals), max(vals) if vals else None)


def aaa_rows(table, stats, seasons, cohort_seasons, threshold):
    """AAA hitter-seasons with >=100 batted balls in the cohort seasons, keeping each
    player's FIRST qualifying season so nobody counts twice in the gate."""
    seen, rows = set(), []
    for pid, s in sorted(table, key=lambda k: (k[1], k[0])):
        m = table[(pid, s)]
        st = stats.get((pid, s))
        if s not in cohort_seasons or pid in seen or (m.get("bbe") or 0) < MIN_BBE or st is None:
            continue
        seen.add(pid)
        arrived, best = later_outcome(seasons, pid, s)
        rows.append({"player_id": pid, "season": s, "f": _features(m, st), "arrived": arrived,
                     "target": best, "useful": best is not None and best >= threshold})
    return rows


def spearman_ci(x, y, n_boot=2000, seed=0):
    """Spearman rho with a percentile bootstrap 95% interval."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        boots.append(float(spearmanr(x[i], y[i]).statistic))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return float(spearmanr(x, y).statistic), float(lo), float(hi)
