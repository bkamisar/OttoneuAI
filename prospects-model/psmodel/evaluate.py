"""Does a feature family add signal? Player-grouped cross-validation."""
import random

import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ALPHAS = np.logspace(-2, 3, 20)
KINDS = ("ridge", "gbm")


def assign_folds(rows, k, seed):
    """Every row of a player lands in the SAME fold. A prospect's 2017 AA and
    2018 AAA rows carry the same outcome; splitting them would leak it."""
    players = sorted({r["player_id"] for r in rows})
    random.Random(seed).shuffle(players)
    fold = {p: i % k for i, p in enumerate(players)}
    return [fold[r["player_id"]] for r in rows]


def guard_features(rows, keys):
    """NFLU's phantom-feature lesson: a declared feature that is missing or
    constant silently contributes nothing. Fail loudly instead."""
    for k in keys:
        vals = [r["f"].get(k) for r in rows]
        if any(v is None for v in vals):
            raise ValueError(f"feature {k!r} has missing values in the fit matrix")
        if len(set(vals)) < 2:
            raise ValueError(f"feature {k!r} is constant -- phantom feature")


def _model(kind="ridge"):
    if kind == "gbm":
        # Trees find conditional effects a linear model can't -- e.g. whiffs that
        # hurt a weak hitter but not a slugger. Shallow and regularized for n ~ 1e3.
        return HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                             min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    return make_pipeline(StandardScaler(), RidgeCV(alphas=ALPHAS))


def _fit(m, X, y, w, kind):
    if kind == "gbm":
        return m.fit(X, y, sample_weight=w)
    return m.fit(X, y, ridgecv__sample_weight=w)


def _xyw(rows, keys):
    X = np.array([[r["f"][k] for k in keys] for r in rows], dtype=float)
    y = np.array([r["target"] for r in rows], dtype=float)
    w = np.array([r["weight"] for r in rows], dtype=float)
    return X, y, w


def oof_predictions(rows, keys, k=5, seed=0, kind="ridge"):
    guard_features(rows, keys)
    X, y, w = _xyw(rows, keys)
    folds = np.array(assign_folds(rows, k, seed))
    pred = np.zeros(len(rows))
    for f in range(k):
        tr, te = folds != f, folds == f
        m = _fit(_model(kind), X[tr], y[tr], w[tr], kind)
        pred[te] = m.predict(X[te])
    return pred


def top_n_precision(rows, pred, n):
    """Share of the n players the model likes most who became useful. Counts
    PLAYERS: a prospect with an AA and an AAA row must not fill two slots."""
    best = {}
    for r, p in zip(rows, pred):
        pid = r["player_id"]
        if pid not in best or p > best[pid][0]:
            best[pid] = (p, r["useful"])
    top = sorted(best.values(), key=lambda t: -t[0])[:n]
    return sum(1 for _, u in top if u) / len(top)


def compare(rows, base, family, seeds=10, k=5, top_n=50, kind="ridge"):
    y = [r["target"] for r in rows]
    out = []
    for s in range(seeds):
        pb = oof_predictions(rows, base, k, s, kind)
        pf = oof_predictions(rows, base + family, k, s, kind)
        out.append({"seed": s,
                    "rho_base": float(spearmanr(pb, y).statistic),
                    "rho_fam": float(spearmanr(pf, y).statistic),
                    "top_base": top_n_precision(rows, pb, top_n),
                    "top_fam": top_n_precision(rows, pf, top_n)})
    return out


def adopt(results, min_wins=8):
    """Adopted only if the family improves rank accuracy WITHOUT lowering the
    top-N hit rate, in at least min_wins of the shuffles. Top-N moves in coarse
    2-point steps at n=50, so ties there are allowed."""
    wins = sum(1 for r in results if r["rho_fam"] > r["rho_base"] and r["top_fam"] >= r["top_base"])
    return wins >= min_wins, wins


def trait_ranking(rows, keys):
    """Standardized ridge coefficients on all rows, largest magnitude first."""
    guard_features(rows, keys)
    X, y, w = _xyw(rows, keys)
    m = _model().fit(X, y, ridgecv__sample_weight=w)
    coef = m.named_steps["ridgecv"].coef_
    return sorted(zip(keys, (float(c) for c in coef)), key=lambda t: -abs(t[1]))
