"""Sub-project 4: the data behind the prospect shopping list.

Joins the model's hitter ratings to the site's current FanGraphs board with plan
C's tested matching, and applies plan C's rules: FanGraphs' order for "how good",
FV+ soon (build_fvplus_scores.py) for "closest to helping", and the model alone
for players FanGraphs doesn't grade. Only derived numbers, flags and the board's
own Name|Org key are written -- never FanGraphs grades.
"""
import csv
import os

from . import consensus as C

PITCHER_POS = frozenset({"p", "sp", "rp", "rhp", "lhp"})
DISAGREE = 0.25      # percentile points before the take mentions a disagreement
NEVER_LISTED = "Never on a FanGraphs list"
GRADE_COLS = {"hit_fut": "Hit_Fut", "pwr_fut": "Game_Fut", "raw_pwr_fut": "Raw_Fut", "spd_fut": "Spd_Fut",
              "fb_fut": "FB_Fut", "sl_fut": "SL_Fut", "cb_fut": "CB_Fut", "ch_fut": "CH_Fut", "cmd_fut": "CMD_Fut"}


def board_key(name, org):
    """The page's join key: rawName|org exactly as written in data/prospects.csv."""
    return f"{name.strip()}|{org.strip()}"


def _cell(row, idx, header):
    i = idx.get(header)
    return row[i].strip() if i is not None and i < len(row) else ""


def load_current_board(path, pitchers=False):
    """Graded hitters (or, with pitchers=True, graded pitchers) from the site's board
    file, shaped like consensus.load_board entries, with fg_id = the Name|Org join key."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head = next((i for i, r in enumerate(rows[:6]) if "Name" in r and "FV" in r), None)
    if head is None:
        raise ValueError(f"no Name/FV header in {path}")
    idx = {h.strip(): i for i, h in enumerate(rows[head])}
    out, seen = [], set()
    for r in rows[head + 1:]:
        name, fv = _cell(r, idx, "Name"), C.parse_fv(_cell(r, idx, "FV"))
        if not name or fv is None or (_cell(r, idx, "Pos").lower() in PITCHER_POS) != pitchers:
            continue
        key = board_key(name, _cell(r, idx, "Org"))
        if key in seen:
            continue
        seen.add(key)
        e = {"fg_id": key, "name": name, "key": C.norm_name(name), "age": C._num(_cell(r, idx, "Age")),
             "fv": fv, "top100": C._rank(_cell(r, idx, "Top 100")),
             "org_rk": C._rank(_cell(r, idx, "Org Rk")),
             "org": _cell(r, idx, "Org"), "pos": _cell(r, idx, "Pos").split("/")[0].strip()}
        e.update({k: C.parse_fv(_cell(r, idx, h)) for k, h in GRADE_COLS.items()})
        out.append(e)
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


def load_pitcher_ratings(path):
    """The model's pitchers from cache/pitcher_ratings.csv (model_p_final.py)."""
    with open(path, encoding="utf-8", newline="") as fh:
        return [{"player_id": int(r["player_id"]), "name": _unguard(r["name"]), "level": r["level"],
                 "age": C._num(r["age"]), "rating": float(r["rating_sgp"]),
                 "rating_pct": float(r["rating_percentile"]) / 100, "soon": float(r["p_useful_within_2"]),
                 "start_share": C._num(r["start_share"])}
                for r in csv.DictReader(fh)]


def tier(p):
    """A pitcher's 'soon' rank among every rated pitcher (percentile in (0, 1]) as
    5 / 10 / 25 for the top 5% / 10% / 25%, else 0. The model's percentages are
    overconfident for pitchers, so only the rank is shown."""
    return 5 if p > 0.95 else 10 if p > 0.90 else 25 if p > 0.75 else 0


def role(start_share):
    return "" if start_share is None else "SP" if start_share >= 0.5 else "RP"


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


def take_pitcher(d_soon, d_rating):
    """Like take(), for pitchers: FanGraphs won both tests, so every disagreement is unproven."""
    soon = ("Model: readier than the grade suggests" if d_soon >= DISAGREE else
            "Model: further away than the grade suggests" if d_soon <= -DISAGREE else None)
    arm = ("likes the arm more" if d_rating >= DISAGREE else
           "likes the arm less" if d_rating <= -DISAGREE else None)
    if soon and arm:
        return f"{soon}; {arm} (unproven)"
    if soon:
        return f"{soon} (unproven)"
    if arm:
        return f"Model {arm} (unproven)"
    return "Model agrees"


def build(ratings, board, history, pitchers=False):
    """(graded, ungraded, unreadable_keys).

    pitchers=True: no percentages; graded rows carry a 'soon' tier (see tier()) and
    ungraded rows a tier and an SP/RP role.

    graded: board players with a model read, sorted by key.
    ungraded: model hitters not on the board, by model rating percentile, each with
    the latest earlier list they appeared on (history = {year: consensus.load_board}).
    unreadable_keys: board rows whose name is shared with a model hitter who can't
    be told apart."""
    people = [{"player_id": r["player_id"], "name": r["name"], "age": r["age"]} for r in ratings]
    by_id = {r["player_id"]: r for r in ratings}
    m = C.match(people, board)
    tiers = dict(zip(by_id, map(tier, C.pct([r["soon"] for r in ratings])))) if pitchers else {}
    pids = list(m["matched"])
    graded = []
    if pids:
        rs = [by_id[p] for p in pids]
        es = [m["matched"][p] for p in pids]
        fv_p = C.pct([C.fv_score(e) for e in es])
        soon_p = C.pct([r["soon"] for r in rs])
        rat_p = C.pct([r["rating"] for r in rs])
        if pitchers:
            graded = sorted(({"key": e["fg_id"], "player_id": r["player_id"], "tier": tiers[r["player_id"]],
                              "take": take_pitcher(s - f, t - f)}
                             for r, e, f, s, t in zip(rs, es, fv_p, soon_p, rat_p)),
                            key=lambda g: g["key"])
        else:
            graded = sorted(({"key": e["fg_id"], "player_id": r["player_id"], "odds": odds(r["soon"]),
                              "take": take(s - f, t - f)}
                             for r, e, f, s, t in zip(rs, es, fv_p, soon_p, rat_p)),
                            key=lambda g: g["key"])

    listed = {}
    for y in sorted(history):                       # ascending, so the latest list wins
        for pid in C.match(people, history[y])["matched"]:
            listed[pid] = y
    amb = {a["player_id"] for a in m["ambiguous"]}
    ungraded = []
    for r in ratings:
        pid = r["player_id"]
        if pid in m["matched"]:
            continue
        if pid in amb:
            note = "Name shared with a FanGraphs prospect — check"
        elif pid in m["age_rejected"]:
            note = "Name matches a FanGraphs prospect of a different age — check"
        elif pid in listed:
            note = f"On the {listed[pid]} list, since dropped"
        else:
            note = NEVER_LISTED
        u = {"player_id": pid, "name": r["name"], "level": r["level"], "age": r["age"],
             "rating_pct": r["rating_pct"], "listed": listed.get(pid), "take": note}
        if pitchers:
            u.update(tier=tiers[pid], role=role(r["start_share"]))
        else:
            u["odds"] = odds(r["soon"])
        ungraded.append(u)
    ungraded.sort(key=lambda u: -u["rating_pct"])
    amb_names = {C.norm_name(a["name"]) for a in m["ambiguous"]}
    unreadable = sorted(e["fg_id"] for e in board if e["key"] in amb_names)
    return graded, ungraded, unreadable


def load_fvplus(path):
    """{'H': {key: {'rank', 'tier'}}, 'P': {...}} from cache/fvplus_scores.csv; empty when absent."""
    out = {"H": {}, "P": {}}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["type"]][r["key"]] = {"rank": int(r["rank"]), "tier": int(r["tier"])}
    return out
