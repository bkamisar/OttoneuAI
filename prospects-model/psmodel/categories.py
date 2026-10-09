"""Roto category scores (spec docs/superpowers/specs/2026-10-09-category-score-design.md).

A prospect's 4-year contribution in each 4x4 category = playing time x (rate vs
replacement), valued with labels.py's per-category terms. One difference, fixed
before any result: the K term scales linearly with innings (labels.pitcher_sgp
never scales replacement K down for low-inning pitchers, a single-season
convention that would make a non-arrival's expected K score negative).
"""
import warnings

import numpy as np
from scipy.stats import norm, spearmanr

from . import context, evaluate, labels, statsapi

HIT_CATS = ("HR", "R", "OBP", "SLG")
PIT_CATS = ("K", "ERA", "WHIP", "HR9")
CATS = {"H": HIT_CATS, "P": PIT_CATS}
WINDOW = 4
MIN_PT = {"H": 200.0, "P": 50.0}
N_BUCKETS = 5
N_BOOT = 1000
HOLM_ALPHA = 0.05


def hitter_terms(row, repl, den, avg_pa):
    """labels.hitter_sgp split into its four categories (they sum to it)."""
    pa = row["pa"] or 0
    pa_ratio = (pa / repl["pa"]) if repl.get("pa") else 1.0
    return {"HR": (row["hr"] - repl["hr"] * pa_ratio) / den["HR"],
            "R": (row["r"] - repl["r"] * pa_ratio) / den["R"],
            "OBP": (row["obp"] - repl["obp"]) * pa / (avg_pa or 1) / den["OBP"],
            "SLG": (row["slg"] - repl["slg"]) * pa / (avg_pa or 1) / den["SLG"]}


def pitcher_terms(row, repl, den, avg_ip):
    """labels.pitcher_sgp's four categories, K scaled linearly with innings."""
    ip = row["ip"] or 0.0
    scale = ip / repl["ip"] if repl.get("ip") else 1.0
    return {"K": (row["so"] - repl["so"] * scale) / den["SO"],
            "ERA": (repl["era"] - row["era"]) * ip / (avg_ip or 1) / den["ERA"],
            "WHIP": (repl["whip"] - row["whip"]) * ip / (avg_ip or 1) / den["WHIP"],
            "HR9": (repl["hr9"] - row["hr9"]) * ip / (avg_ip or 1) / den["HR9"]}


TERMS = {"H": hitter_terms, "P": pitcher_terms}


def season_tables(first, last):
    """{season: {"H": {pid: MLB row}, "P": {...}, "repl": {"H": ..., "P": ...}}} from cached StatsAPI."""
    out = {}
    for s in range(first, last + 1):
        hs = statsapi.season_stats(s, "hitting", statsapi.MLB)
        ps = statsapi.season_stats(s, "pitching", statsapi.MLB)
        frac = context.season_fraction(s)
        out[s] = {"H": {r["player_id"]: r for r in hs}, "P": {r["player_id"]: r for r in ps},
                  "repl": {"H": context.hitter_replacement(hs, frac), "P": context.pitcher_replacement(ps, frac)}}
    return out


def averages():
    avg_pa, avg_ip = context.league_averages()
    return {"H": avg_pa, "P": avg_ip}


TOTAL = {"H": labels.hitter_sgp, "P": labels.pitcher_sgp}


def outcome(pid, typ, v, tables, den, avg, roster_only=False):
    """(category terms summed over seasons v+1..v+4, playing time, pooled rates or None).
    roster_only: count only seasons whose total SGP is > 0 (seasons a team would use)."""
    terms = dict.fromkeys(CATS[typ], 0.0)
    acc = {}
    for s in range(v + 1, v + WINDOW + 1):
        t = tables.get(s)
        r = t[typ].get(pid) if t else None
        if r is None:
            continue
        if roster_only and TOTAL[typ](r, t["repl"][typ], den, avg[typ]) <= 0:
            continue
        for k, x in TERMS[typ](r, t["repl"][typ], den, avg[typ]).items():
            terms[k] += x
        if typ == "H":
            pairs = (("pa", r["pa"]), ("ab", r["ab"]), ("hr", r["hr"]), ("r", r["r"]),
                     ("obp_pa", r["obp"] * r["pa"]), ("slg_ab", r["slg"] * r["ab"]))
        else:
            pairs = (("ip", r["ip"]), ("so", r["so"]), ("hr", r["hr"]),
                     ("era_ip", r["era"] * r["ip"]), ("whip_ip", r["whip"] * r["ip"]))
        for k, x in pairs:
            acc[k] = acc.get(k, 0.0) + x
    pt = acc.get("pa" if typ == "H" else "ip", 0)
    if not pt:
        return terms, 0, None
    if typ == "H":
        rates = {"HR": acc["hr"] / pt, "R": acc["r"] / pt, "OBP": acc["obp_pa"] / pt,
                 "SLG": acc["slg_ab"] / acc["ab"] if acc["ab"] else 0.0}
    else:
        rates = {"K": acc["so"] / pt, "ERA": acc["era_ip"] / pt, "WHIP": acc["whip_ip"] / pt,
                 "HR9": 9.0 * acc["hr"] / pt}
    return terms, pt, rates


def expected_terms(typ, pt, rates, repl, den, avg):
    """Category terms of an expected 4-season line: playing time pt at the given rates."""
    if typ == "H":
        row = {"pa": pt, "hr": rates["HR"] * pt, "r": rates["R"] * pt, "obp": rates["OBP"], "slg": rates["SLG"]}
    else:
        row = {"ip": pt, "so": rates["K"] * pt, "era": rates["ERA"], "whip": rates["WHIP"], "hr9": rates["HR9"]}
    return TERMS[typ](row, repl, den, avg[typ])


def design(rows, keys, fill=None):
    X = np.array([[np.nan if r["f"].get(k) is None else float(r["f"][k]) for k in keys] for r in rows],
                 dtype=float)
    if fill is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fill = np.nan_to_num(np.nanmean(X, axis=0))
    i, j = np.where(np.isnan(X))
    X[i, j] = fill[j]
    return X, fill


def fit_ridge(rows, keys, y, w=None):
    X, fill = design(rows, keys)
    m = evaluate._model("ridge")
    m.fit(X, np.asarray(y, dtype=float), **({} if w is None else {"ridgecv__sample_weight": np.asarray(w)}))
    return m, fill


def predict(m, fill, rows, keys):
    return m.predict(design(rows, keys, fill)[0])


def _parts(score, n):
    return np.array_split(np.argsort(np.asarray(score, dtype=float), kind="stable"), n)


def inversions(means):
    return sum(1 for a, b in zip(means, means[1:]) if b < a)


def ladder(score, actual, n=N_BUCKETS, n_boot=N_BOOT, seed=0):
    """Walk-up ladder: bucket means low -> high score, counts, inversions, and the
    top-minus-bottom difference with its bootstrap SE (buckets fixed by score)."""
    actual = np.asarray(actual, dtype=float)
    parts = _parts(score, n)
    means = [float(actual[p].mean()) for p in parts]
    lo, hi = parts[0], parts[-1]
    rng = np.random.default_rng(seed)
    boot = [actual[rng.choice(hi, len(hi))].mean() - actual[rng.choice(lo, len(lo))].mean() for _ in range(n_boot)]
    d, se = means[-1] - means[0], float(np.std(boot))
    z = d / se if se > 0 else 0.0
    return {"means": means, "counts": [len(p) for p in parts], "inversions": inversions(means),
            "d": d, "se": se, "z": z, "p": float(2 * norm.sf(abs(z)))}


def ladder_pass(lad, holm_p):
    return lad["inversions"] <= 1 and lad["d"] - 1.96 * lad["se"] > 0 and holm_p < HOLM_ALPHA


def rho_diff(a, b, y, n_boot=N_BOOT, seed=0):
    """(Spearman(a, y) - Spearman(b, y), its SE) from a paired player bootstrap."""
    a, b, y = (np.asarray(x, dtype=float) for x in (a, b, y))
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        boot.append(spearmanr(a[i], y[i]).statistic - spearmanr(b[i], y[i]).statistic)
    return float(spearmanr(a, y).statistic - spearmanr(b, y).statistic), float(np.nanstd(boot))
