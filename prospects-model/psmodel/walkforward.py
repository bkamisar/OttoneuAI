"""Walk-forward backtests that train only on what was known at each vantage year.

At vantage V the test set is cohort V; training is every cohort whose answer was
known by V (asof.rating_known / soon_known), minus every player in the test
cohort (a player's rows share one outcome). The 2024 cohort is SEALED for the
final check and refused unless unseal=True.
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import asof, evaluate, interactions

SEALED = frozenset({2024})
RATING_VANTAGES = (2019, 2021, 2022)
SOON_VANTAGES = (2021, 2022, 2023)
KINDS = {"rating": ("ridge", "gbm"), "soon": ("logit", "gbm")}   # (simple, complex)
MIN_TRAIN = 300
TOP_NS = (25, 50, 100)


def _y(r, target, bar):
    if target == "rating":
        return asof.rating_target(r["mlb"], r["season"])
    return 1.0 if asof.soon_target(r["mlb"], r["season"], bar) else 0.0


def frames(rows, target, v, bar, keys, unseal=False):
    """(train, test) at vantage v, complete on keys, with targets attached as 'y'."""
    if v in SEALED and not unseal:
        raise ValueError(f"cohort {v} is sealed until the final check")
    known = asof.rating_known if target == "rating" else asof.soon_known
    test = [r for r in rows if r["season"] == v]
    ids = {r["player_id"] for r in test}
    train = [r for r in rows if known(r["season"], v) and r["player_id"] not in ids]
    return [[dict(r, y=_y(r, target, bar)) for r in part if all(r["f"].get(k) is not None for k in keys)]
            for part in (train, test)]


def _model(target, kind):
    if target == "rating":
        return evaluate._model(kind)
    if kind == "gbm":
        return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                              min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=10, max_iter=2000))


def _X(rows, keys):
    return np.array([[r["f"][k] for k in keys] for r in rows], dtype=float)


def fit_predict(train, test, keys, target, kind):
    m = _model(target, kind).fit(_X(train, keys), np.array([r["y"] for r in train]))
    Xt = _X(test, keys)
    return m, (m.predict_proba(Xt)[:, 1] if target == "soon" else m.predict(Xt))


def metrics(test, pred, target, bar):
    """Rank accuracy (Spearman for rating, AUC for soon) and top-N precision,
    counting PLAYERS: each player's best-predicted row only."""
    y = [r["y"] for r in test]
    rank = roc_auc_score(y, pred) if target == "soon" else spearmanr(pred, y).statistic
    best = {}
    for r, p in zip(test, pred):
        useful = r["y"] >= bar if target == "rating" else r["y"] == 1.0
        if r["player_id"] not in best or p > best[r["player_id"]][0]:
            best[r["player_id"]] = (p, useful)
    ranked = sorted(best.values(), key=lambda t: -t[0])
    out = {"rank": float(rank), "n": len(test)}
    for n in TOP_NS:
        top = ranked[:n]
        out[f"top{n}"] = sum(u for _, u in top) / len(top)
    return out


def compare(rows, base, family, target, kind, bars, vantages, unseal=False):
    """{v: {'base': metrics, 'fam': metrics} | None}, both fits on IDENTICAL rows
    (complete on base + family)."""
    union = base + [k for k in family if k not in base]
    res = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], union, unseal)
        if len(train) < MIN_TRAIN or not test:
            res[v] = None
            continue
        res[v] = {}
        for name, keys in (("base", base), ("fam", union)):
            evaluate.guard_features(train, keys)
            res[v][name] = metrics(test, fit_predict(train, test, keys, target, kind)[1], target, bars[v])
    return res


def adopt(res, min_wins=2):
    """(adopted, wins, vantages available). A win = better rank accuracy without a
    lower top-50 or top-100. Needs >=2 available vantages."""
    avail = [r for r in res.values() if r is not None]
    wins = sum(1 for r in avail if r["fam"]["rank"] > r["base"]["rank"]
               and r["fam"]["top50"] >= r["base"]["top50"] and r["fam"]["top100"] >= r["base"]["top100"])
    return len(avail) >= 2 and wins >= min_wins, wins, len(avail)


def pick_kind(res, target):
    """The complex model only if it beats the simple one on rank at >=2 vantages."""
    simple, complex_ = KINDS[target]
    wins = sum(1 for r in res.values() if r is not None and r[1]["rank"] > r[0]["rank"])
    return complex_ if wins >= 2 else simple


def choose_kind(rows, keys, target, bars, vantages, unseal=False):
    res = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN or not test:
            res[v] = None
            continue
        evaluate.guard_features(train, keys)
        res[v] = tuple(metrics(test, fit_predict(train, test, keys, target, k)[1], target, bars[v])
                       for k in KINDS[target])
    return pick_kind(res, target), res


def group_importance(rows, groups, target, kind, bars, vantages):
    """{(group,): compare-result}: each group vs all the others. Groups that fail
    alone are also tested in pairs, since near-duplicates hide each other."""
    all_keys = [k for g in groups.values() for k in g]
    out = {}
    for g, keys in groups.items():
        out[(g,)] = compare(rows, [k for k in all_keys if k not in keys], keys, target, kind, bars, vantages)
    failing = [g for g in groups if not adopt(out[(g,)])[0]]
    for i, a in enumerate(failing):
        for b in failing[i + 1:]:
            fam = groups[a] + groups[b]
            out[(a, b)] = compare(rows, [k for k in all_keys if k not in fam], fam, target, kind, bars, vantages)
    return out


def predictions(rows, keys, target, kind, bars, vantages, unseal=False):
    """{v: (test rows, predictions)} for one model."""
    out = {}
    for v in vantages:
        train, test = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN or not test:
            continue
        evaluate.guard_features(train, keys)
        out[v] = (test, fit_predict(train, test, keys, target, kind)[1])
    return out


def calibration(test, pred, bins=10):
    """[(mean predicted, actual rate, n)] by predicted-probability bin."""
    pred = np.asarray(pred, dtype=float)
    return [(float(np.mean(pred[c])), float(np.mean([test[i]["y"] for i in c])), len(c))
            for c in np.array_split(np.argsort(pred), bins)]


class _Proba:
    """Makes a classifier's probability look like predict() for interactions.py."""
    def __init__(self, m):
        self.m = m

    def predict(self, X):
        return self.m.predict_proba(X)[:, 1]


def interactions_by_vantage(rows, keys, target, bars, vantages, n=10, sample=100, unseal=False):
    """{(key_a, key_b): [(vantage, strength)]} for pairs in each vantage's top n (trees)."""
    hits = {}
    for v in vantages:
        train, _ = frames(rows, target, v, bars[v], keys, unseal)
        if len(train) < MIN_TRAIN:
            continue
        m, _ = fit_predict(train, train[:1], keys, target, "gbm")
        model = _Proba(m) if target == "soon" else m
        idx = np.random.default_rng(v).choice(len(train), size=min(sample, len(train)), replace=False)
        for h, a, b in interactions.top_pairs(model, _X([train[i] for i in idx], keys), keys, n):
            hits.setdefault((a, b), []).append((v, h))
    return hits
