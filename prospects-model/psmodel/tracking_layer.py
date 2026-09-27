"""The tracking layer: a hitter's base prediction moves by the part of his step-1
tracking score that the base prediction doesn't already explain, times a trust
weight learned from AAA cohorts whose answers were known at the vantage.

Everything is as-of: step 1 is refit on MLB rows whose outcome season is <= v, and
the AAA->MLB offsets use same-season pairs in seasons <= v.
"""
import numpy as np

from . import evaluate, step1

MIN_AAA_BBE = step1.MIN_BBE


def step1_keys(choice):
    """Step-1 features usable in AAA: the chosen keys minus Savant-only spray."""
    return [k for k in choice["score_keys"] if k not in step1.GROUPS["spray"]]


def step1_model(v, mlb_table, seasons, mlb_stats, keys, kind):
    """Step 1 refit as-of v: MLB rows whose outcome season (t+1) is <= v."""
    rows = step1.complete(step1.mlb_rows({k: m for k, m in mlb_table.items() if k[1] <= v - 1},
                                         seasons, mlb_stats, threshold=0.0), keys)
    return evaluate.fit(rows, keys, kind)


def offsets(v, aaa_table, mlb_table, keys):
    """AAA->MLB offsets from same-season pairs in seasons <= v."""
    return step1.fit_translation({k: m for k, m in aaa_table.items() if k[1] <= v},
                                 {k: m for k, m in mlb_table.items() if k[1] <= v}, keys)


def aaa_scores(aaa_table, aaa_stats, model, translation, keys, seasons_wanted):
    """{(player_id, season): tracking score} for AAA rows with >=100 batted balls."""
    out = {}
    for (pid, s), m in aaa_table.items():
        st = aaa_stats.get((pid, s))
        if s not in seasons_wanted or st is None or (m.get("bbe") or 0) < MIN_AAA_BBE:
            continue
        f = step1.translate(step1._features(m, st), translation)
        if all(f.get(k) is not None for k in keys):
            out[(pid, s)] = float(evaluate.predict(model, [{"f": f}], keys)[0])
    return out


def residualize(score, base):
    """The part of the score a straight line on the base prediction doesn't explain.
    Returns (resid, (a, b)); apply the same line to new rows: score - (a + b * base)."""
    b, a = np.polyfit(base, score, 1)
    return score - (a + b * base), (float(a), float(b))


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _w_ls(y, base, resid, wt):
    den = float(np.sum(wt * resid ** 2))
    return float(np.sum(wt * resid * (y - base)) / den) if den > 0 else 0.0


def _w_logit(y, base, resid, wt, iters=100):
    """One-coefficient logistic fit with the base log-odds as a fixed offset."""
    o, w = _logit(base), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(o + w * resid)))
        h = float(np.sum(wt * resid ** 2 * p * (1 - p)))
        if h <= 0:
            break
        step = float(np.clip(np.sum(wt * resid * (y - p)) / h, -1.0, 1.0))
        w += step
        if abs(step) < 1e-10:
            break
    return w


def trust_weight(target, y, base, resid, wt, pids, n_boot=1000, seed=0):
    """(w, lo, hi): the adjustment weight and a player-bootstrap 95% interval."""
    fit = _w_logit if target == "soon" else _w_ls
    y, base, resid, wt, pids = (np.asarray(a) for a in (y, base, resid, wt, pids))
    w = fit(y, base, resid, wt)
    uniq = np.unique(pids)
    rows_of = {p: np.where(pids == p)[0] for p in uniq}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = np.concatenate([rows_of[p] for p in rng.choice(uniq, len(uniq))])
        boots.append(fit(y[i], base[i], resid[i], wt[i]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(w), float(lo), float(hi)


def adjust(target, base, resid, w):
    if target == "soon":
        return 1 / (1 + np.exp(-(_logit(base) + w * resid)))
    return base + w * resid
