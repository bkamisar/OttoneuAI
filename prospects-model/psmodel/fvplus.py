"""FV+ (spec docs/superpowers/specs/2026-09-30-fv-plus-design.md, Amendment A).

FanGraphs' FV is the base; FV+ adds the pre-registered 4x4 adjustments in ONE
regularized model per player type and output (ridge for rating, logit for soon),
fit strictly as-of and tested walk-forward against FV alone. The groups, grades,
thresholds and rules here are the spec's, fixed before any result.
"""
import warnings

import numpy as np
from scipy.stats import norm, rankdata
from sklearn.linear_model import LogisticRegressionCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import asof, evaluate
from . import consensus as C
from . import features as FT
from . import walkforward as W

PREMIUM = frozenset({"C", "SS", "CF"})
NO_PITCH = 20.0
MIN_TRAIN_PLAYERS = 300
MIN_TRAIN_SUCCESSES = 30
N_SHUFFLE = 200
SHUFFLE_PCT = 95.0
HOLM_ALPHA = 0.05
MIN_IP = 30.0
QUEUE_MIN_N = 20

_RW = ["hit", "gpwr", "spd", "prem", "bb"]
_SH = ["fb", "brk", "ch", "cmd", "fb_x_cmd", "fb_x_brk", "rel"]
_PX = ["is_aaa", "is_aa", "is_higha", "age_rel"]
GROUPS = {
    ("H", "rating"): {"RW": _RW, "UP": ["age_rel", "raw_gap"], "OP": ["opp"], "SM": ["sm"]},
    ("H", "soon"): {"RW": _RW, "OP": ["opp"], "PX": _PX, "SM": ["sm"]},
    ("P", "rating"): {"SH": _SH, "GB": ["gb"], "OP": ["opp"], "SM": ["sm"]},
    ("P", "soon"): {"SH": _SH, "GB": ["gb"], "OP": ["opp"], "PX": _PX, "SM": ["sm"]},
}
# Expected weight signs from the spec's tables ('?' = no call).
EXPECTED = {
    ("H", "rating"): {"hit": "?", "gpwr": "+", "spd": "-", "prem": "?", "bb": "+", "age_rel": "-",
                      "raw_gap": "+", "opp": "-", "sm": "+"},
    ("H", "soon"): {"hit": "?", "gpwr": "+", "spd": "-", "prem": "?", "bb": "+", "opp": "-",
                    "is_aaa": "+", "is_aa": "+", "is_higha": "+", "age_rel": "+", "sm": "+"},
    ("P", "rating"): {"fb": "?", "brk": "+", "ch": "?", "cmd": "?", "fb_x_cmd": "?", "fb_x_brk": "?",
                      "rel": "?", "gb": "+", "opp": "-", "sm": "+"},
    ("P", "soon"): {"fb": "?", "brk": "+", "ch": "?", "cmd": "?", "fb_x_cmd": "?", "fb_x_brk": "?",
                    "rel": "+", "gb": "+", "opp": "-", "is_aaa": "+", "is_aa": "+", "is_higha": "+",
                    "age_rel": "+", "sm": "+"},
}
GRADE_KEYS = {"H": ("hit_fut", "pwr_fut", "raw_pwr_fut", "spd_fut"), "P": ("fb_fut", "cmd_fut")}


def keys(typ, target, drop=None):
    out = []
    for g, ks in GROUPS[(typ, target)].items():
        if g != drop:
            out += [k for k in ks if k not in out]
    return out


def medians(board, typ):
    """The list's median future grade for each tool imputed when blank."""
    out = {}
    for k in GRADE_KEYS[typ]:
        vals = [e[k] for e in board if e.get(k) is not None]
        out[k] = float(np.median(vals)) if vals else 50.0
    return out


def features(typ, e, r, med, opp, gb=None):
    """Adjustments for one graded player. e = Board entry (consensus.load_board),
    r = his model row for the class season, med = medians(that list), opp = the
    parent club's win% that season, gb = ground-ball z (pitchers)."""
    f = r["f"]
    x = {"fv": C.fv_score(e), "age_rel": f.get("age"), "opp": opp,
         "is_aaa": f.get("is_aaa"), "is_aa": f.get("is_aa"), "is_higha": f.get("is_higha")}
    if typ == "H":
        g = {k: med[k] if e.get(k) is None else e[k] for k in GRADE_KEYS["H"]}
        x.update(hit=g["hit_fut"], gpwr=g["pwr_fut"], spd=g["spd_fut"], raw_gap=g["raw_pwr_fut"] - g["pwr_fut"],
                 prem=1.0 if e.get("pos") in PREMIUM else 0.0, bb=f.get("bb"))
    else:
        fb = med["fb_fut"] if e.get("fb_fut") is None else e["fb_fut"]
        cmd = med["cmd_fut"] if e.get("cmd_fut") is None else e["cmd_fut"]
        brk = max([g for g in (e.get("sl_fut"), e.get("cb_fut")) if g is not None], default=NO_PITCH)
        ch = NO_PITCH if e.get("ch_fut") is None else e["ch_fut"]
        ss = r.get("start_share")
        x.update(fb=fb, brk=brk, ch=ch, cmd=cmd, fb_x_cmd=(fb - 50) * (cmd - 50) / 10,
                 fb_x_brk=(fb - 50) * (brk - 50) / 10, rel=None if ss is None else float(ss < 0.5), gb=gb)
    return x


def gb_z(raw_rows):
    """{(player_id, season, sport_id): ground-out share z within level-season-league}, 30+ IP rows."""
    rows = []
    for r in raw_rows:
        if r["ip"] < MIN_IP:
            continue
        outs = (r.get("go") or 0) + (r.get("ao") or 0)
        rows.append({"sport_id": r["sport_id"], "season": r["season"], "league": r.get("league"),
                     "key": (r["player_id"], r["season"], r["sport_id"]),
                     "f": {"gb": r["go"] / outs if outs else None}})
    FT.standardize_within_league(rows, ["gb"])
    return {r["key"]: r["f"]["gb"] for r in rows}


def matrix(players, cols, fill=None):
    X = np.array([[np.nan if p["x"].get(k) is None else float(p["x"][k]) for k in cols] for p in players],
                 dtype=float)
    if fill is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fill = np.nan_to_num(np.nanmean(X, axis=0))
    r, c = np.where(np.isnan(X))
    X[r, c] = fill[c]
    return X, fill


def _model(target):
    if target == "rating":
        return evaluate._model("ridge")
    return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=10, scoring="neg_log_loss", max_iter=2000))


def fit(train, cols, target):
    X, fill = matrix(train, cols)
    return _model(target).fit(X, np.array([p["y"] for p in train], dtype=float)), fill


def predict(model, fill, test, cols, target):
    X, _ = matrix(test, cols, fill)
    return model.predict_proba(X)[:, 1] if target == "soon" else model.predict(X)


def coefs(model):
    return np.ravel(model[-1].coef_)


def _split(classes, v, known, yfun):
    test = [dict(p, y=yfun(p)) for p in classes[v]]
    ids = {p["player_id"] for p in test}
    train = [dict(p, y=yfun(p)) for c, ps in classes.items() if c != v and known(c, v)
             for p in ps if p["player_id"] not in ids]
    return train, test


def split(classes, v, target, ctx):
    """(train, test) at test class v, strictly as-of, test players removed from training."""
    known = asof.rating_known if target == "rating" else asof.soon_known
    return _split(classes, v, known, lambda p: W._y(p["row"], target, ctx))


def trainable(train, target):
    if len(train) < MIN_TRAIN_PLAYERS:
        return False
    return target == "rating" or sum(p["y"] for p in train) >= MIN_TRAIN_SUCCESSES


def walk(classes, test_classes, target, cols, ctxs):
    """FV alone vs FV + cols at each test class: ({v: head_to_head | None}, {v: (test, pred)})."""
    res, preds = {}, {}
    full = ["fv"] + list(cols)
    for v in test_classes:
        train, test = split(classes, v, target, ctxs[v])
        if not trainable(train, target):
            res[v] = None
            continue
        m, fill = fit(train, full, target)
        p = predict(m, fill, test, full, target)
        preds[v] = (test, p)
        res[v] = C.head_to_head(test, C.pct([q["x"]["fv"] for q in test]), p, target, ctxs[v])
    return res, preds


def pooled(res):
    """(summed gain, pooled z, classes used) over {class: head_to_head | None}."""
    got = [r for r in res.values() if r is not None]
    d = float(sum(r["d"] for r in got))
    se = float(np.sqrt(sum(r["se"] ** 2 for r in got)))
    return d, (d / se if se > 0 else 0.0), len(got)


def p_two_sided(z):
    return float(2 * norm.sf(abs(z)))


def holm_adjust(p):
    """Holm step-down adjusted p-values for {name: p}."""
    out, run = {}, 0.0
    order = sorted(p, key=p.get)
    for i, k in enumerate(order):
        run = max(run, min(1.0, (len(order) - i) * p[k]))
        out[k] = run
    return out


def majority(n):
    return n // 2 + 1


def conditions(res, target):
    """Every adoption condition except Holm and the shuffle."""
    got = [r for r in res.values() if r is not None]
    pos = sum(1 for r in got if r["d"] > 0)
    t50 = float(np.mean([r["fam"]["top50"] - r["base"]["top50"] for r in got])) if got else 0.0
    return {"classes": len(got), "positive": pos, "majority": len(got) >= 2 and pos >= majority(len(got)),
            "harmed": any(W.z_score(r["d"], r["se"]) <= W.HARM_Z for r in got), "top50": t50,
            "top50_ok": target == "rating" or t50 >= -W.TOP50_TOLERANCE}


def shuffled(classes, cols, rng):
    """Copies with the cols block permuted jointly among players of the same FV grade, per class."""
    out = {}
    for c, ps in classes.items():
        by = {}
        for i, p in enumerate(ps):
            by.setdefault(p["fv_grade"], []).append(i)
        new = [dict(p, x=dict(p["x"])) for p in ps]
        for idx in by.values():
            for dst, src in zip(idx, rng.permutation(idx)):
                for k in cols:
                    new[dst]["x"][k] = ps[src]["x"][k]
        out[c] = new
    return out


def weights(train, cols, target, n_boot=200, seed=0):
    """{col: (standardized weight, 2.5%, 97.5%)} from a player bootstrap."""
    base = coefs(fit(train, cols, target)[0])
    pids = np.array([p["player_id"] for p in train])
    uniq = np.unique(pids)
    rows_of = {q: np.where(pids == q)[0] for q in uniq}
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        idx = np.concatenate([rows_of[q] for q in rng.choice(uniq, len(uniq))])
        sub = [train[i] for i in idx]
        if target == "soon" and len({p["y"] for p in sub}) < 2:
            continue
        boot.append(coefs(fit(sub, cols, target)[0]))
    lo, hi = np.percentile(np.array(boot), [2.5, 97.5], axis=0)
    return {k: (float(b), float(l), float(h)) for k, b, l, h in zip(cols, base, lo, hi)}


def partial_spearman(x, y, z):
    """Spearman of x and y with z's ranks regressed out of both (ties averaged)."""
    rx, ry, rz = (rankdata(a) for a in (x, y, z))
    A = np.column_stack([np.ones(len(rz)), rz])

    def resid(a):
        return a - A @ np.linalg.lstsq(A, a, rcond=None)[0]

    ex, ey = resid(rx), resid(ry)
    den = np.sqrt((ex @ ex) * (ey @ ey))
    return float(ex @ ey / den) if den > 1e-9 else 0.0


def partial_ci(x, y, z, n_boot=300, seed=0):
    """(partial Spearman, bootstrap SE) over players (one row each)."""
    x, y, z = (np.asarray(a, dtype=float) for a in (x, y, z))
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        if len(set(y[i])) < 2 or len(set(x[i])) < 2:
            continue
        boot.append(partial_spearman(x[i], y[i], z[i]))
    return partial_spearman(x, y, z), float(np.std(boot)) if boot else 0.0


def fv_bucket(fv_grade):
    return int(min(60, max(40, 5 * np.floor(fv_grade / 5))))


def gbin(g):
    return "<=40" if g <= 40 else ("45-50" if g <= 50 else ">50")


def residuals(players):
    """y minus the mean y of the same class and FV bucket."""
    groups = {}
    for p in players:
        groups.setdefault((p["cls"], fv_bucket(p["fv_grade"])), []).append(p["y"])
    means = {g: float(np.mean(v)) for g, v in groups.items()}
    return [p["y"] - means[(p["cls"], fv_bucket(p["fv_grade"]))] for p in players]


def cell(values, n_boot=500, seed=0):
    """(mean, 2.5%, 97.5%, n) of one map cell's residuals; None if empty."""
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return None
    rng = np.random.default_rng(seed)
    boot = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(a.mean()), float(lo), float(hi), len(a)


def queued(c):
    return c is not None and c[3] >= QUEUE_MIN_N and (c[1] > 0 or c[2] < 0)
