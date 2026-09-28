"""Pitch-level stuff model (P-E): grade every pitch on its physical characteristics
only (location excluded, as in public stuff models) -- the chance of a whiff when
swung at, and the expected damage when put in play -- then average per
pitcher-season into two features the stuff-score machinery maps to fantasy value.
Spec: docs/superpowers/specs/2026-09-28-pitchers-design.md, "P-E".
"""
import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from .metrics import CONTACT_CODES, WHIFF_CODES
from .pitch_metrics import BREAKING_WIDE

FASTBALLS = ("FF", "SI", "FC")
FAMILIES = {"FB": FASTBALLS, "BRK": BREAKING_WIDE, "OFF": ("CH", "FS", "FO", "SC")}
FAMILY_CODE = {t: i for i, ts in enumerate(FAMILIES.values()) for t in ts}      # FB 0, breaking 1, offspeed 2
FEATURES = ["speed", "spin", "ivb", "hb_arm", "ext", "rel_side", "rel_height", "same_side",
            "d_speed", "d_ivb", "d_hb"]
IN_PLAY = frozenset({"X", "D", "E"})
WOBA = {"single": 0.89, "double": 1.27, "triple": 1.62, "home_run": 2.10}     # every other result: 0
MIN_FB = 30          # primary fastballs thrown before the gap features are defined
MIN_TRAIN = 50       # swings / balls in play of a family before it gets a model
NAN = float("nan")


def _f(v):
    return NAN if v is None else float(v)


def season_frame(pitches):
    """One level-season of pitch events (tracking.iter_pitch_events) -> numpy arrays:
    X (n x FEATURES, NaN = missing), fam (0 fastball / 1 breaking / 2 offspeed),
    swing / whiff / bip flags, ev / la, woba (NaN off in-play pitches), pitcher ids.
    Pitches outside the three families are dropped. Horizontal break and release side
    are sign-flipped for left-handers; the gaps are to the pitcher-season's primary
    fastball (the most-thrown of FF/SI/FC, >= MIN_FB thrown)."""
    cols = {k: [] for k in ("pitcher", "fam", "fbt", "speed", "spin", "ivb", "hb_arm", "ext", "rel_side",
                            "rel_height", "same_side", "swing", "whiff", "bip", "ev", "la", "woba")}
    fb_acc = {}
    for p in pitches:
        fam = FAMILY_CODE.get(p.get("type"))
        pid = p.get("pitcher")
        if fam is None or pid is None:
            continue
        s = -1.0 if p.get("p_hand") == "L" else 1.0
        hb = _f(p.get("hb")) * s
        code = p.get("code")
        whiff = code in WHIFF_CODES or code == "T"
        contact = code in CONTACT_CODES and not whiff
        bip = code in IN_PLAY
        fbt = FASTBALLS.index(p["type"]) if p["type"] in FASTBALLS else -1
        vals = {"pitcher": pid, "fam": fam, "fbt": fbt, "speed": _f(p.get("speed")), "spin": _f(p.get("spin")),
                "ivb": _f(p.get("ivb")), "hb_arm": hb, "ext": _f(p.get("ext")), "rel_side": _f(p.get("x0")) * s,
                "rel_height": _f(p.get("z0")),
                "same_side": 1.0 if p.get("p_hand") and p.get("p_hand") == p.get("b_side") else 0.0,
                "swing": whiff or contact, "whiff": whiff, "bip": bip,
                "ev": _f(p.get("ev")) if bip else NAN, "la": _f(p.get("la")) if bip else NAN,
                "woba": WOBA.get(p.get("event"), 0.0) if bip else NAN}
        for k, v in vals.items():
            cols[k].append(v)
        if fbt >= 0:
            a = fb_acc.setdefault((pid, fbt), [0, [], [], []])
            a[0] += 1
            a[1].append(vals["speed"])
            a[2].append(vals["ivb"])
            a[3].append(hb)

    primary = {}
    for (pid, fbt), a in fb_acc.items():
        if a[0] >= MIN_FB and a[0] > primary.get(pid, (0,))[0]:
            primary[pid] = (a[0], float(np.nanmean(a[1])), float(np.nanmean(a[2])), float(np.nanmean(a[3])))
    ref = np.array([primary.get(pid, (0, NAN, NAN, NAN))[1:] for pid in cols["pitcher"]], dtype=float).reshape(-1, 3)

    fr = {"pitcher": np.array(cols["pitcher"], dtype=np.int64), "fam": np.array(cols["fam"], dtype=np.int8)}
    for k in ("swing", "whiff", "bip"):
        fr[k] = np.array(cols[k], dtype=bool)
    for k in ("ev", "la", "woba"):
        fr[k] = np.array(cols[k], dtype=np.float32)
    base = np.column_stack([np.array(cols[k], dtype=float) for k in FEATURES[:8]]) if cols["pitcher"] \
        else np.empty((0, 8))
    gaps = base[:, [0, 2, 3]] - ref if len(base) else np.empty((0, 3))
    fr["X"] = np.column_stack([base, gaps]).astype(np.float32) if len(base) else np.empty((0, len(FEATURES)), np.float32)
    return fr


def _concat(frames):
    return {k: np.concatenate([f[k] for f in frames]) for k in frames[0]}


def _clf():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
                                          min_samples_leaf=100, l2_regularization=1.0, random_state=0)


def _reg():
    return HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
                                         min_samples_leaf=100, l2_regularization=1.0, random_state=0)


def train(frames):
    """Pitch models on the MLB frames given -- the caller passes only seasons <= the
    vantage. Returns {"xdamage": EV/LA -> wOBA model, family code: (whiff|swing
    classifier, damage|contact regressor)}. The damage regressor learns the SMOOTHED
    xdamage(EV, LA) of each ball in play, not its noisy actual result."""
    F = _concat(frames)
    ok = F["bip"] & np.isfinite(F["ev"]) & np.isfinite(F["la"])
    xd = _reg().fit(np.column_stack([F["ev"][ok], F["la"][ok]]), F["woba"][ok])
    dmg = np.full(len(F["fam"]), np.nan)
    dmg[ok] = xd.predict(np.column_stack([F["ev"][ok], F["la"][ok]]))
    models = {"xdamage": xd}
    for code in range(len(FAMILIES)):
        sw = F["swing"] & (F["fam"] == code)
        bb = ok & (F["fam"] == code)
        if sw.sum() < MIN_TRAIN or bb.sum() < MIN_TRAIN:
            models[code] = None           # too few pitches of this family to grade it
            continue
        models[code] = (_clf().fit(F["X"][sw], F["whiff"][sw]), _reg().fit(F["X"][bb], dmg[bb]))
    return models


def pitcher_features(models, frame):
    """{pitcher_id: {"pitches", "pl_whiff", "pl_damage"}}: each pitcher's mean predicted
    whiff-on-swing chance and mean predicted damage-on-contact over their graded
    pitches (every pitch graded as if swung at / put in play; location excluded).
    'pitches' counts all their pitches in the three families."""
    n = len(frame["fam"])
    pw, pd = np.full(n, np.nan), np.full(n, np.nan)
    for code in range(len(FAMILIES)):
        m = frame["fam"] == code
        if m.any() and models.get(code) is not None:
            clf, reg = models[code]
            pw[m] = clf.predict_proba(frame["X"][m])[:, 1]
            pd[m] = reg.predict(frame["X"][m])
    ids, inv = np.unique(frame["pitcher"], return_inverse=True)
    graded = np.isfinite(pw)
    cnt, ng = np.bincount(inv), np.bincount(inv, weights=graded)
    sw = np.bincount(inv, weights=np.where(graded, pw, 0.0))
    sd = np.bincount(inv, weights=np.where(graded, pd, 0.0))
    return {int(pid): {"pitches": int(c), "pl_whiff": float(a / g) if g else None,
                       "pl_damage": float(b / g) if g else None}
            for pid, c, g, a, b in zip(ids, cnt, ng, sw, sd)}


def paired_rho_diff(a, b, y, n_boot=2000, seed=0):
    """(Spearman(a, y) - Spearman(b, y), its paired player-bootstrap SE): both scores
    are re-ranked on the SAME resampled players each draw."""
    a, b, y = (np.asarray(v, dtype=float) for v in (a, b, y))
    d = float(spearmanr(a, y).statistic - spearmanr(b, y).statistic)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        boots.append(float(spearmanr(a[i], y[i]).statistic - spearmanr(b[i], y[i]).statistic))
    return d, float(np.nanstd(boots, ddof=1))


def choose(season_lo, pitch_lo, diff, se):
    """The pre-registered P-E rule. A score is usable only if its as-of Spearman CI
    lower bound is > 0 (None = not run). Pitch-level replaces season-level only if it
    is usable AND beats it by >= 1 paired SE; a tie keeps season-level. If
    season-level fails, a usable pitch-level score (the single pre-registered second
    attempt) is used. Returns "pitch", "season" or "none"."""
    s_ok = season_lo is not None and season_lo > 0
    p_ok = pitch_lo is not None and pitch_lo > 0
    if p_ok and (not s_ok or diff >= se):
        return "pitch"
    return "season" if s_ok else "none"
