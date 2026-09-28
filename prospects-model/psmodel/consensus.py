"""Plan C: does the model beat just following FanGraphs' FV?

The Board lists are the user's manual exports (cache/fv/board_<year>_hitters.csv,
gitignored, never committed). Only the grade columns (FV, Top 100, Org Rk) and the
name and age for matching are read; the Board's stat columns aren't as-of. The
Board carries no MLBAM id, so players are matched by name with an age guard, and
every same-name case is listed, never guessed (the Witt -> Witte lesson).
"""
import csv
import os
import unicodedata

import numpy as np
from scipy.stats import rankdata
from sklearn.linear_model import LinearRegression, LogisticRegression

from . import walkforward as W

AGE_TOLERANCE = 1.5      # years either side of the list's calibrated age offset
SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})
VERDICTS = ("follow FV", "model as tiebreaker", "model leads")     # most cautious first
CHANCE = {"rating": 0.0, "soon": 0.5}                              # Spearman, AUC
MIN_H2H = 30
N_BOOT = 300


def board_path(root, year):
    return os.path.join(root, f"board_{year}_hitters.csv")


def norm_name(name):
    """Accents folded, lowercase, punctuation and Jr./II-style suffixes dropped."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace("-", " ")
    for ch in ".,'’":
        s = s.replace(ch, "")
    return " ".join(t for t in s.split() if t not in SUFFIXES)


def parse_fv(text):
    """'45+' -> 47.5; blank -> None."""
    s = (text or "").strip()
    if not s:
        return None
    fv = float(s.rstrip("+")) + (2.5 if s.endswith("+") else 0.0)
    return fv if fv > 0 else None


def _rank(text):
    """Top 100 / Org Rk: blank, or 0 on the 2017-18 lists, means unranked."""
    s = (text or "").strip()
    return int(float(s)) if s and float(s) > 0 else None


def _num(text):
    s = (text or "").strip()
    return float(s) if s else None


def load_board(path):
    """Graded hitters from one Board export: [{fg_id, name, key, age, fv, top100, org_rk}]."""
    out, seen = [], set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            fv = parse_fv(r.get("FV"))
            if fv is None or r["playerId"] in seen:
                continue
            seen.add(r["playerId"])
            out.append({"fg_id": r["playerId"], "name": r["Name"], "key": norm_name(r["Name"]),
                        "age": _num(r.get("Age")), "fv": fv,
                        "top100": _rank(r.get("Top 100")), "org_rk": _rank(r.get("Org Rk"))})
    return out


def fv_score(e):
    """FanGraphs' order as one number, higher = better: FV, then Top 100, then org
    rank. Grades sit >= 2.5 apart and the tiebreaks add < 2, so they never cross a grade."""
    if e["top100"]:
        return e["fv"] + 1.0 + (101 - e["top100"]) / 101
    if e["org_rk"]:
        return e["fv"] + 0.9 * (1000 - min(e["org_rk"], 999)) / 1000
    return e["fv"]


def _cand(e):
    return f"{e['name']} ({e['fg_id']}, age {e['age']}, FV {e['fv']:g})"


def match(players, board):
    """Link our players [{player_id, name, age}] to one Board list by name, guarded by age.

    The Board's age is taken at a date that differs by list, so the offset (Board
    age - StatsAPI season age) is calibrated as the median over names unique on both
    sides; a candidate must sit within AGE_TOLERANCE of it. Returns
    {"matched": {player_id: entry}, "ambiguous": [{player_id, name, age, candidates}],
     "age_rejected": {player_id}, "offset": float}. A name with no Board entry at all
    is simply absent from every field (ungraded)."""
    by_key = {}
    for e in board:
        by_key.setdefault(e["key"], []).append(e)
    ours = {}
    for p in players:
        ours.setdefault(norm_name(p["name"]), []).append(p)
    diffs = [by_key[k][0]["age"] - ps[0]["age"] for k, ps in ours.items()
             if len(ps) == 1 and len(by_key.get(k, ())) == 1
             and by_key[k][0]["age"] is not None and ps[0]["age"] is not None]
    offset = float(np.median(diffs)) if diffs else 0.0

    ambiguous, rejected, claims = [], set(), {}
    for p in players:
        named = by_key.get(norm_name(p["name"]), [])
        if not named:
            continue
        cands = [e for e in named if p["age"] is not None and e["age"] is not None
                 and abs(e["age"] - p["age"] - offset) <= AGE_TOLERANCE]
        if not cands:
            rejected.add(p["player_id"])
        elif len(cands) > 1:
            ambiguous.append({"player_id": p["player_id"], "name": p["name"], "age": p["age"],
                              "candidates": [_cand(e) for e in cands]})
        else:
            claims.setdefault(cands[0]["fg_id"], (cands[0], []))[1].append(p)
    matched = {}
    for e, ps in claims.values():
        if len(ps) == 1:
            matched[ps[0]["player_id"]] = e
        else:
            ambiguous += [{"player_id": p["player_id"], "name": p["name"], "age": p["age"],
                           "candidates": [_cand(e)]} for p in ps]
    return {"matched": matched, "ambiguous": ambiguous, "age_rejected": rejected, "offset": offset}


def pct(x):
    """Percentile ranks in (0, 1], ties averaged."""
    x = np.asarray(x, dtype=float)
    return rankdata(x) / len(x)


def head_to_head(test, base, alt, target, ctx):
    """One class in W.adopt's shape: base = FanGraphs' order, alt = the challenger.
    test holds one row per player with 'y'. None if too few players, or (soon)
    only one outcome."""
    if len(test) < MIN_H2H or (target == "soon" and len({r["y"] for r in test}) < 2):
        return None
    base, alt = np.asarray(base, dtype=float), np.asarray(alt, dtype=float)
    d, se = W.paired_gain(test, base, alt, target)
    return {"base": W.metrics(test, base, target, ctx), "fam": W.metrics(test, alt, target, ctx),
            "d": d, "se": se}


def rank_ci(test, pred, target, n_boot=N_BOOT, seed=0):
    """(rank accuracy, 2.5%, 97.5%) from a bootstrap over players (one row each);
    None if untestable."""
    y = np.array([r["y"] for r in test], dtype=float)
    p = np.asarray(pred, dtype=float)
    if len(y) < MIN_H2H or len(set(y)) < 2:
        return None
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) < 2:
            continue
        s = W._rank(target, y[i], p[i])
        if np.isfinite(s):
            stats.append(s)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(W._rank(target, y, p)), float(lo), float(hi)


def verdict(model_res, blend_res):
    """Pre-registered (spec, plan C). {class: head_to_head | None} for each challenger.
    The model leads if it beats FV by the adoption rule; else it's a tiebreaker if
    the simple blend does; else follow FV."""
    if W.adopt(model_res)[0]:
        return VERDICTS[2]
    if W.adopt(blend_res)[0]:
        return VERDICTS[1]
    return VERDICTS[0]


def cautious(a, b):
    return VERDICTS[min(VERDICTS.index(a), VERDICTS.index(b))]


def sleepers_ok(cis, target):
    """Show the model for ungraded hitters only if its sleeper interval clears
    chance at >= 2 classes."""
    return sum(1 for c in cis.values() if c is not None and c[1] > CHANCE[target]) >= 2


def fit_blend(pm, pf, y, target):
    """Information only: a second-stage fit on the two percentile ranks."""
    m = LogisticRegression() if target == "soon" else LinearRegression()
    return m.fit(np.column_stack([pm, pf]), y)


def apply_blend(m, pm, pf, target):
    X = np.column_stack([pm, pf])
    return m.predict_proba(X)[:, 1] if target == "soon" else m.predict(X)
