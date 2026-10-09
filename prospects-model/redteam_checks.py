"""Red-team checks (spec 2026-10-09-category-score-design.md, "Red-team checks";
rules pre-registered before this ran):
  1. FV+ soon vs FV + level + age (what the preseason board showed)
  2. category score vs volume only (predicted playing time)
  3. roster-worthy outcomes (seasons with total SGP > 0)

Usage:  python redteam_checks.py   -> cache/redteam_report.txt (gitignored). No network.
Needs category_run.py's cache/category_race.json.
"""
import json
import os

import numpy as np

import category_run as CR
import consensus_gate as CG
import fvplus_run as R
from psmodel import categories as K
from psmodel import consensus as C
from psmodel import fvplus as F

REPORT = os.path.join(R.CACHE, "redteam_report.txt")
BOARD_COLS = ["fv", "is_aaa", "is_aa", "is_higha", "age_raw"]


def check1(cx, L):
    L.append("1. FV+ soon vs FV + level + age (L). Gain = FV+ minus L; also L minus FV alone.")
    for typ in ("H", "P"):
        m = (typ, "soon")
        classes = {c: [dict(p, x=dict(p["x"], age_raw=p["row"].get("age_raw"))) for p in ps]
                   for c, ps in cx.d.classes[m].items()}
        full = ["fv"] + F.keys(typ, "soon")
        plus, lvf = {}, {}
        for v in R.EXPECTED_TESTS[m]:
            ctx = cx.d.ctx[(typ, v)]
            train, test = F.split(classes, v, "soon", ctx)
            pf = F.predict(*F.fit(train, full, "soon"), test, full, "soon")
            pb = F.predict(*F.fit(train, BOARD_COLS, "soon"), test, BOARD_COLS, "soon")
            plus[v] = C.head_to_head(test, pb, pf, "soon", ctx)
            lvf[v] = C.head_to_head(test, C.pct([q["x"]["fv"] for q in test]), pb, "soon", ctx)
            L.append(f"  {typ} class {v}: AUC FV {lvf[v]['base']['rank']:.3f}, L {pb_auc(lvf[v]):.3f}, "
                     f"FV+ {plus[v]['fam']['rank']:.3f} | FV+ - L {plus[v]['d']:+.4f} (z {plus[v]['d'] / plus[v]['se']:+.1f})")
        d, z, n = F.pooled(plus)
        pos = sum(1 for r in plus.values() if r["d"] > 0)
        d2, z2, _ = F.pooled(lvf)
        verdict = "FV+ ADDS beyond the board" if (z >= 1.96 and pos >= F.majority(n)) else "FV+ ~ FV + level + age"
        L.append(f"  {typ}: FV+ over L pooled {d:+.4f} (z {z:+.2f}, {pos}/{n} positive); L over FV pooled "
                 f"{d2:+.4f} (z {z2:+.2f}) -> {verdict}")
    L.append("")


def pb_auc(res):
    return res["fam"]["rank"]


def vectors(cx, race, typ):
    """Graded and ungraded ladder populations: score, predicted playing time, actual and roster-only actual."""
    cols = ["fv"] + (CR.PT_KEYS[typ] if race[typ]["choice"] == "fv_stats" else [])
    pops = {}
    g = {"score": {c: [] for c in K.CATS[typ]}, "act": {c: [] for c in K.CATS[typ]},
         "floor": {c: [] for c in K.CATS[typ]}, "pt": []}
    for v in CR.RACE_CLASSES:
        train, test = CR.race_split(cx, typ, v)
        pt = np.maximum(K.predict(*K.fit_ridge(train, cols, [r["y"] for r in train]), test, cols), 0.0)
        models, _ = cx.rate_models(typ, v, exclude={r["player_id"] for r in test})
        add(cx, typ, v, [r["row"] for r in test], [r["player_id"] for r in test], pt, models, g)
    pops["graded"] = g
    u = {"score": {c: [] for c in K.CATS[typ]}, "act": {c: [] for c in K.CATS[typ]},
         "floor": {c: [] for c in K.CATS[typ]}, "pt": []}
    for v in CR.UNGRADED_VANTAGES:
        rows = cx.best(typ, v)
        m = C.match(CG.people(rows), cx.d.boards[typ][v + 1])
        skip = set(m["matched"]) | m["age_rejected"] | {a["player_id"] for a in m["ambiguous"]}
        test = [r for r in rows if r["player_id"] not in skip]
        ids = {r["player_id"] for r in test}
        (mp, fp), _ = cx.pt_stats_model(typ, v, exclude=ids)
        pt = np.maximum(K.predict(mp, fp, test, CR.PT_KEYS[typ]), 0.0)
        models, _ = cx.rate_models(typ, v, exclude=ids)
        add(cx, typ, v, test, [r["player_id"] for r in test], pt, models, u)
    pops["ungraded"] = u
    return pops


def add(cx, typ, v, rows, pids, pt, models, acc):
    for pid, p, e in zip(pids, pt, CR._score_rows(cx, typ, rows, pt, models, v)):
        a = cx.out(typ, pid, v)[0]
        fl = K.outcome(pid, typ, v, cx.tables, cx.den, cx.avg, roster_only=True)[0]
        acc["pt"].append(p)
        for c in K.CATS[typ]:
            acc["score"][c].append(e[c])
            acc["act"][c].append(a[c])
            acc["floor"][c].append(fl[c])


def checks23(cx, L):
    race = json.load(open(os.path.join(R.CACHE, "category_race.json"), encoding="utf-8"))
    pops = {typ: vectors(cx, race, typ) for typ in ("H", "P")}
    L.append("2. Category score vs volume only: Spearman(score, actual) - Spearman(predicted playing time, actual)")
    for pop in ("graded", "ungraded"):
        res = {}
        for typ in ("H", "P"):
            v = pops[typ][pop]
            for c in K.CATS[typ]:
                d, se = K.rho_diff(v["score"][c], v["pt"], v["act"][c])
                res[f"{typ}_{c}"] = (d, se, F.p_two_sided(d / se if se else 0.0))
        holm = F.holm_adjust({k: r[2] for k, r in res.items()})
        L.append(f"  {pop}:")
        for k, (d, se, p) in res.items():
            adds = d > 0 and holm[k] < 0.05
            L.append(f"    {k:6}: {d:+.3f} (z {d / se:+.1f}, Holm p {holm[k]:.4f}) -> "
                     f"{'shape ADDS' if adds else 'volume explains it'}")
    L += ["", "3. Roster-worthy outcomes (seasons with total SGP > 0)"]
    for typ in ("H", "P"):
        g = pops[typ]["graded"]
        for c in K.CATS[typ]:
            cl = F.cell(g["floor"][c])
            raw = F.cell(g["act"][c])
            lad = K.ladder(g["score"][c], g["floor"][c])
            L.append(f"  graded {typ}_{c:4}: mean all-seasons {raw[0]:+.3f} [{raw[1]:+.3f}, {raw[2]:+.3f}] -> "
                     f"roster-worthy {cl[0]:+.3f} [{cl[1]:+.3f}, {cl[2]:+.3f}]; ladder on roster-worthy: "
                     + " < ".join(f"{x:+.2f}" for x in lad["means"]) + f" (inversions {lad['inversions']}, z {lad['z']:+.1f})")
    hurt = [c for c in ("ERA", "WHIP", "HR9") if F.cell(pops["P"]["graded"]["floor"][c])[2] < 0]
    L.append(f"  -> 'pitching prospects hurt the ratios' {'SURVIVES for ' + ', '.join(hurt) if hurt else 'does NOT survive'}")


def main():
    cx = CR.Ctx()
    L = ["RED-TEAM CHECKS (pre-registered in the category-score spec)", ""]
    check1(cx, L)
    checks23(cx, L)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
