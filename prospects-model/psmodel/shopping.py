"""Sub-project 4: the data behind the prospect shopping list.

Joins the model's hitter ratings to the site's current FanGraphs board with plan
C's tested matching, and applies plan C's rules: FanGraphs' order for "how good",
the average of the FV and model percentiles for "closest to helping", and the
model alone for hitters FanGraphs doesn't grade. Only derived numbers, flags and
the board's own Name|Org key are written -- never FanGraphs grades.
"""
import csv

import numpy as np

from . import consensus as C

PITCHER_POS = frozenset({"p", "sp", "rp", "rhp", "lhp"})
DISAGREE = 0.25      # percentile points before the take mentions a disagreement
NEVER_LISTED = "Never on a FanGraphs list"


def board_key(name, org):
    """The page's join key: rawName|org exactly as written in data/prospects.csv."""
    return f"{name.strip()}|{org.strip()}"


def _cell(row, idx, header):
    i = idx.get(header)
    return row[i].strip() if i is not None and i < len(row) else ""


def load_current_board(path):
    """Graded hitters from the site's board file, shaped like consensus.load_board
    entries, with fg_id = the Name|Org join key. Pitchers are skipped."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head = next((i for i, r in enumerate(rows[:6]) if "Name" in r and "FV" in r), None)
    if head is None:
        raise ValueError(f"no Name/FV header in {path}")
    idx = {h.strip(): i for i, h in enumerate(rows[head])}
    out, seen = [], set()
    for r in rows[head + 1:]:
        name, fv = _cell(r, idx, "Name"), C.parse_fv(_cell(r, idx, "FV"))
        if not name or fv is None or _cell(r, idx, "Pos").lower() in PITCHER_POS:
            continue
        key = board_key(name, _cell(r, idx, "Org"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"fg_id": key, "name": name, "key": C.norm_name(name), "age": C._num(_cell(r, idx, "Age")),
                    "fv": fv, "top100": C._rank(_cell(r, idx, "Top 100")),
                    "org_rk": C._rank(_cell(r, idx, "Org Rk"))})
    return out


def _unguard(s):
    """Undo the CSV-injection guard model3c_final.py puts on names."""
    return s[1:] if len(s) > 1 and s[0] == "'" and s[1] in "=+-@" else s


def load_ratings(path):
    """The model's hitters from cache/hitter_ratings.csv (model3c_final.py)."""
    with open(path, encoding="utf-8", newline="") as fh:
        return [{"player_id": int(r["player_id"]), "name": _unguard(r["name"]), "level": r["level"],
                 "age": C._num(r["age"]), "rating": float(r["rating_sgp"]),
                 "rating_pct": float(r["rating_percentile"]) / 100, "soon": float(r["p_useful_within_2"])}
                for r in csv.DictReader(fh)]


def odds(p):
    """The 2-year probability as a whole percent rounded to 5; 0 means under 2.5%."""
    return int(round(p * 20)) * 5


def take(d_soon, d_rating):
    """One plain-language line on where the model disagrees with FanGraphs.
    d_* = model percentile - FV percentile within the pool."""
    soon = ("Model: readier than the grade suggests" if d_soon >= DISAGREE else
            "Model: further away than the grade suggests" if d_soon <= -DISAGREE else None)
    bat = ("likes the bat more (ceiling: unproven)" if d_rating >= DISAGREE else
           "likes the bat less (ceiling: unproven)" if d_rating <= -DISAGREE else None)
    if soon and bat:
        return f"{soon}; {bat}"
    if soon:
        return soon
    if bat:
        return f"Model {bat}"
    return "Model agrees"
