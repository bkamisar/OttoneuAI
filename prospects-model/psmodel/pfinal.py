"""P-D's pre-registered decision rules and the write-once record of the 2024
opening (spec: 2026-09-28-pitchers-design.md, "P-D: the pitcher final run")."""
import json
import math
import os

Z95 = 1.959964


def calibration_error(buckets):
    """Size-weighted mean |mean predicted - actual| over walkforward.calibration buckets."""
    n = sum(b[2] for b in buckets)
    return sum(b[2] * abs(b[0] - b[1]) for b in buckets) / n


def soon_kind(trees, logit):
    """'logit' only if the trees LOSE on both: the logit's top-50 hit rate strictly
    higher AND its calibration error strictly lower. Otherwise the preset trees."""
    return "logit" if logit["top50"] > trees["top50"] and logit["calib"] < trees["calib"] else "gbm"


def wilson(k, n, z=Z95):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def _inside(pred, act, n):
    lo, hi = wilson(round(act * n), n)
    return lo <= pred <= hi


def percent_ok(buckets):
    """'Soon' odds may be shown as percentages only if the mean predicted rate is
    inside the actual rate's 95% Wilson interval in the TOP bucket and overall."""
    n = sum(b[2] for b in buckets)
    pred = sum(b[0] * b[2] for b in buckets) / n
    act = sum(b[1] * b[2] for b in buckets) / n
    return _inside(*buckets[-1]) and _inside(pred, act, n)


def load_frozen(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def freeze(path, decisions):
    """Write the 2024 decisions once. Refuses to overwrite: re-deciding on an opened
    class would be moving the goalposts (deleting the file takes the user's say-so)."""
    if os.path.exists(path):
        raise SystemExit(f"{path} exists -- the 2024 decisions are frozen; not overwriting")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)
    os.replace(tmp, path)
