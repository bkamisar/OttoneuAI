"""Statcast boom/bust check for named MLB hitters.

    python statcast_check.py "Fernando Tatis Jr." "Zach Neto" "Henry Bolte"
    python statcast_check.py --first 2024 --last 2026 --split 2026-07-01 "Zach Neto"

For each player, season by season (first..last), from Baseball Savant (first-party,
cached by psmodel.http so reruns never re-download):
  results vs expected  -- wOBA/xwOBA, SLG/xSLG, BABIP, HR vs barrels: the luck part
  contact + discipline -- barrel%, hard-hit%, EV, LA, chase, whiff, zone contact, K/BB
  bat tracking         -- bat speed, swing length, squared-up, blasts
  swing path           -- attack angle, attack direction, swing tilt, ideal-AA rate
  stance               -- foot separation, stance angle, depth/distance in the box
plus, for the last season, first-half vs second-half splits (split date) from the
player's pitch-level file: wOBA/xwOBA, bat speed, attack angle, hard-hit, barrels.
Each number carries its percentile among that season's regulars, and flags mark
the year-over-year changes big enough to matter. Interpretation is left to the reader:
luck gaps regress, bat speed / chase / swing-path changes tend to stick, stance
describes a change rather than predicting one.

Savant ignores bad parameters silently (see psmodel/http.py), so every board is
checked: rows present, a year column matching where one exists, and no two
seasons byte-identical.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import statistics
import sys
import unicodedata

from psmodel import http

S = "https://baseballsavant.mlb.com"
CUSTOM_SEL = ("pa,home_run,batting_avg,on_base_percent,slg_percent,woba,xba,xobp,xslg,xwoba,babip,"
              "barrel_batted_rate,hard_hit_percent,exit_velocity_avg,launch_angle_avg,sweet_spot_percent,"
              "oz_swing_percent,whiff_percent,iz_contact_percent,k_percent,bb_percent,pull_percent,"
              "flyballs_percent,sprint_speed")
BOARDS = {
    "custom": S + "/leaderboard/custom?year={y}&type=batter&min=1&selections=" + CUSTOM_SEL + "&csv=true",
    # dateStart/dateEnd only works for the current season; seasonStart/End works for all
    "bat": S + ("/leaderboard/bat-tracking?gameType=Regular&minSwings=1&minGroupSwings=1"
                "&seasonStart={y}&seasonEnd={y}&type=batter&csv=true"),
    "path": S + ("/leaderboard/bat-tracking/swing-path-attack-angle?gameType=Regular&minSwings=1"
                 "&minGroupSwings=1&seasonStart={y}&seasonEnd={y}&type=batter&csv=true"),
    "stance": S + "/visuals/batting-stance?seasonStart={y}&seasonEnd={y}&minSwings=1&csv=true",
}
PITCHES = S + ("/statcast_search/csv?all=true&hfGT=R%7C&hfSea={y}%7C&player_type=batter"
               "&batters_lookup%5B%5D={pid}&type=details&min_pitches=0&min_results=0")

# (board, column, label, decimals, flag threshold for a year-over-year change, higher-is-better)
ROWS = [
    ("custom", "pa", "PA", 0, None, None),
    ("custom", "woba", "wOBA", 3, None, True),
    ("custom", "xwoba", "xwOBA", 3, 0.020, True),
    ("custom", "on_base_percent", "OBP", 3, None, True),
    ("custom", "xobp", "xOBP", 3, 0.015, True),
    ("custom", "slg_percent", "SLG", 3, None, True),
    ("custom", "xslg", "xSLG", 3, 0.030, True),
    ("custom", "babip", "BABIP", 3, None, None),
    ("custom", "home_run", "HR", 0, None, True),
    ("custom", "barrel_batted_rate", "Barrel%", 1, 2.0, True),
    ("custom", "hard_hit_percent", "HardHit%", 1, 4.0, True),
    ("custom", "exit_velocity_avg", "EV", 1, 1.0, True),
    ("custom", "launch_angle_avg", "LA", 1, 3.0, None),
    ("custom", "sweet_spot_percent", "SweetSpot%", 1, 3.0, True),
    ("custom", "pull_percent", "Pull%", 1, 4.0, None),
    ("custom", "flyballs_percent", "FB%", 1, 4.0, None),
    ("custom", "oz_swing_percent", "Chase%", 1, 3.0, False),
    ("custom", "whiff_percent", "Whiff%", 1, 3.0, False),
    ("custom", "iz_contact_percent", "ZoneContact%", 1, 3.0, True),
    ("custom", "k_percent", "K%", 1, 3.0, False),
    ("custom", "bb_percent", "BB%", 1, 2.0, True),
    ("custom", "sprint_speed", "Sprint", 1, 0.5, True),
    ("bat", "avg_bat_speed", "BatSpeed", 1, 1.0, True),
    ("bat", "swing_length", "SwingLen", 2, 0.3, None),
    ("bat", "squared_up_per_swing", "SqUp/Sw", 3, 0.02, True),
    ("bat", "blast_per_swing", "Blast/Sw", 3, 0.02, True),
    ("bat", "hard_swing_rate", "HardSwing", 3, 0.05, None),
    ("path", "attack_angle", "AttackAng", 1, 3.0, None),
    ("path", "ideal_attack_angle_rate", "IdealAA%", 3, 0.05, True),
    ("path", "attack_direction", "AttackDir", 1, 3.0, None),
    ("path", "swing_tilt", "SwingTilt", 1, 3.0, None),
    ("stance", "avg_foot_sep", "FootSep", 1, 2.0, None),
    ("stance", "avg_stance_angle", "StanceAng", 1, 4.0, None),
    ("stance", "avg_batter_y_position", "BoxDepth", 1, 2.0, None),
    ("stance", "avg_batter_x_position", "PlateDist", 1, 2.0, None),
]
PCT_MIN = {"custom": ("pa", 300), "bat": ("swings_competitive", 500),
           "path": ("competitive_swings", 500), "stance": None}


def num(v):
    try:
        return float(str(v).strip().strip('"')) if v not in (None, "", "null") else None
    except ValueError:
        return None


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", " ").replace(",", " ").split())


def to_first_last(savant_name):
    if "," in savant_name:
        last, first = [x.strip() for x in savant_name.split(",", 1)]
        return first + " " + last
    return savant_name


def load_board(kind, year, seen):
    text = http.fetch_text(BOARDS[kind].format(y=year), ".csv").lstrip("﻿")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if (kind, digest) in seen:
        raise http.DataError(f"Savant {kind} board for {year} identical to {seen[(kind, digest)]} -- season ignored?")
    seen[(kind, digest)] = year
    rows = list(csv.DictReader(io.StringIO(text)))
    http.require_rows(rows, f"savant {kind} {year}")
    out = {}
    for r in rows:
        if kind == "custom":
            http.require_value(r.get("year"), year, f"savant custom {year}")
            pid, name = r["player_id"], r["last_name, first_name"]
        else:
            pid, name = r["id"], r["name"]
        out[int(pid)] = dict(r, _name=to_first_last(name))
    return out


def percentile(board, col, pid, kind):
    gate = PCT_MIN[kind]
    vals = [num(r.get(col)) for r in board.values()
            if num(r.get(col)) is not None and (gate is None or (num(r.get(gate[0])) or 0) >= gate[1])]
    v = num(board.get(pid, {}).get(col))
    if v is None or len(vals) < 20:
        return None
    return round(100 * sum(1 for x in vals if x < v) / len(vals))


def pitch_splits(pid, year, split):
    text = http.fetch_text(PITCHES.format(y=year, pid=pid), ".csv").lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text)))
    http.require_rows(rows, f"savant pitches {pid} {year}")
    for r in rows:
        if r.get("game_year") != str(year) or r.get("batter") != str(pid):
            raise http.DataError(f"pitch file for {pid} {year} has game_year={r.get('game_year')} batter={r.get('batter')}")
    halves = {"H1": [r for r in rows if r["game_date"] < split], "H2": [r for r in rows if r["game_date"] >= split]}
    out = {}
    for h, rs in halves.items():
        pa = [r for r in rs if r.get("woba_denom") not in ("", None) and num(r["woba_denom"])]
        den = sum(num(r["woba_denom"]) for r in pa)
        woba = sum(num(r["woba_value"]) or 0 for r in pa) / den if den else None
        # xwOBA: speed/angle estimate on balls in play, actual wOBA value otherwise (Savant's method)
        xw = sum((num(r["estimated_woba_using_speedangle"]) if num(r.get("estimated_woba_using_speedangle")) is not None
                  else (num(r["woba_value"]) or 0)) for r in pa) / den if den else None
        bs = sorted(x for x in (num(r.get("bat_speed")) for r in rs) if x is not None)
        comp = bs[len(bs) // 10:]                          # drop the slowest 10% (checked swings, bunts)
        aa = [num(r["attack_angle"]) for r in rs if num(r.get("attack_angle")) is not None and num(r.get("bat_speed")) and num(r["bat_speed"]) >= (comp[0] if comp else 0)]
        bip = [r for r in rs if num(r.get("launch_speed")) is not None and r.get("type") == "X"]
        out[h] = {
            "PA": round(den), "wOBA": woba, "xwOBA": xw,
            "BatSpeed": statistics.mean(comp) if comp else None,
            "AttackAng": statistics.mean(aa) if aa else None,
            "HardHit%": 100 * sum(1 for r in bip if num(r["launch_speed"]) >= 95) / len(bip) if bip else None,
            "Barrel%": 100 * sum(1 for r in bip if r.get("launch_speed_angle") == "6") / len(bip) if bip else None,
            "HR": sum(1 for r in rs if r.get("events") == "home_run"),
        }
    return out


def fmt(v, d):
    return "-" if v is None else f"{v:.{d}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--first", type=int, default=2024)
    ap.add_argument("--last", type=int, default=2026)
    ap.add_argument("--split", default=None, help="first/second-half split date for the last season (default {last}-07-01)")
    ap.add_argument("--json", default=None, help="also write the raw card data here")
    a = ap.parse_args()
    split = a.split or f"{a.last}-07-01"
    years = list(range(a.first, a.last + 1))
    seen, boards = {}, {}
    for y in years:
        for k in BOARDS:
            try:
                boards[(k, y)] = load_board(k, y, seen)
            except http.DataError as e:
                if k in ("bat", "path", "stance"):      # tracking boards start mid-decade
                    print(f"  ({k} {y} unavailable: {e})", file=sys.stderr)
                    boards[(k, y)] = {}
                else:
                    raise
    last_custom = boards[("custom", a.last)]
    cards = {}
    for name in a.names:
        hits = [pid for pid, r in last_custom.items() if norm(r["_name"]) == norm(name)]
        if not hits:
            hits = [pid for y in years for pid, r in boards[("custom", y)].items() if norm(r["_name"]) == norm(name)][:1]
        if not hits:
            print(f"\n{name}: not found on Savant's {a.first}-{a.last} batter boards")
            continue
        pid = hits[0]
        card = {"name": name, "id": pid, "seasons": {}, "flags": [], "halves": None}
        print(f"\n=== {name} (Savant id {pid}) ===")
        print(f"{'':13}" + "".join(f"{y:>16}" for y in years))
        for kind, col, label, d, thr, better in ROWS:
            cells, vals = [], []
            for y in years:
                b = boards[(kind, y)]
                v = num(b.get(pid, {}).get(col))
                p = percentile(b, col, pid, kind) if label not in ("PA", "HR") else None
                vals.append(v)
                card["seasons"].setdefault(y, {})[label] = {"v": v, "pct": p}
                cells.append(f"{fmt(v, d)}{'' if p is None else f' ({p})'}")
            print(f"{label:13}" + "".join(f"{c:>16}" for c in cells))
            if thr is not None and vals[-1] is not None:
                prior = [v for v in vals[:-1] if v is not None]
                if prior:
                    base = statistics.mean(prior)
                    delta = vals[-1] - base
                    if abs(delta) >= thr:
                        tone = "" if better is None else (" (good)" if (delta > 0) == better else " (bad)")
                        card["flags"].append(f"{label} {fmt(base, d)} -> {fmt(vals[-1], d)}{tone}")
        c = boards[("custom", a.last)].get(pid, {})
        luck = []
        for act, exp, lab in (("woba", "xwoba", "wOBA"), ("on_base_percent", "xobp", "OBP"), ("slg_percent", "xslg", "SLG")):
            if num(c.get(act)) is not None and num(c.get(exp)) is not None:
                luck.append(f"{lab} {num(c[act]) - num(c[exp]):+.3f} vs expected")
        print(f"{a.last} results minus expected: " + ", ".join(luck))
        print("Changes vs prior seasons' average: " + ("; ".join(card["flags"]) or "none past thresholds"))
        try:
            hv = pitch_splits(pid, a.last, split)
            card["halves"] = hv
            print(f"{a.last} halves (split {split}):")
            for h in ("H1", "H2"):
                r = hv[h]
                print(f"  {h}: PA {r['PA']}  wOBA {fmt(r['wOBA'], 3)}  xwOBA {fmt(r['xwOBA'], 3)}  HR {r['HR']}  "
                      f"Barrel% {fmt(r['Barrel%'], 1)}  HardHit% {fmt(r['HardHit%'], 1)}  "
                      f"BatSpeed {fmt(r['BatSpeed'], 1)}  AttackAng {fmt(r['AttackAng'], 1)}")
        except http.DataError as e:
            print(f"  (halves unavailable: {e})")
        cards[name] = card
    print("\n(percentile among regulars in parentheses: 300+ PA / 500+ competitive swings; stance among all)")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(cards, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
