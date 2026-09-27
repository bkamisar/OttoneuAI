"""3c-hitters plan A: as-of walk-forward backtests of the base model, for both
outputs -- rating (best season in the next 4) and soon (starter-quality season
within 2). Model choice, group importance, interactions, calibration. 2024 stays
sealed for plan B's final check.

Usage:  python model3c_base.py
Reads only cached data (run pull_3c_data.py and build_labels.py first).
Writes cache/model3c_base_report.txt and cache/model3c_choice.json (gitignored).
"""
import json
import os
import statistics

import numpy as np

from psmodel import asof, cohorts, dataset
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model3c_base_report.txt")
CHOICE = os.path.join(CACHE, "model3c_choice.json")


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['base']['rank']:.3f}->{r['fam']['rank']:.3f} "
                     f"top50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f}"
                     for v, r in res.items())


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    mlb = {pid: rows for (pid, typ), rows in labels.items() if typ == "H"}
    rows = cohorts.build_rows(cohorts.load_milb(), cohorts.mlb_pa_history(), mlb)
    L = ["3c-HITTERS BASE MODEL -- as-of walk-forward backtests (2024 sealed)",
         f"rows: {len(rows)} hitter-season-levels, {len({r['player_id'] for r in rows})} players",
         "per season: " + ", ".join(f"{s} {sum(1 for r in rows if r['season'] == s)}"
                                    for s in cohorts.MILB_SEASONS), ""]
    all_keys = [k for g in cohorts.GROUPS.values() for k in g]
    choice = {}
    for target, vantages in (("rating", W.RATING_VANTAGES), ("soon", W.SOON_VANTAGES)):
        bars = {v: asof.useful_bar(labels, v) for v in vantages}
        simple, complex_ = W.KINDS[target]
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; useful bar as-of: "
                 + ", ".join(f"{v} {b:.3f}" for v, b in bars.items()))
        kind, kres = W.choose_kind(rows, all_keys, target, bars, vantages)
        L.append(f"model: {kind}  (" + "; ".join(
            f"{v}: n/a" if r is None else f"{v}: {simple} {r[0]['rank']:.3f} vs {complex_} {r[1]['rank']:.3f}"
            for v, r in kres.items()) + ")")
        L.append("groups -- drop-and-refit; KEEP if dropping it hurts at >=2 vantages:")
        adopted = set()
        for gs, res in W.group_importance(rows, cohorts.GROUPS, target, kind, bars, vantages).items():
            ok, wins, avail = W.adopt(res)
            L.append(f"  {' + '.join(gs):24} {'KEEP' if ok else 'drop':4} {wins}/{avail}  {fmt(res)}")
            if ok:
                adopted.update(gs)
        keys = [k for g in cohorts.GROUPS if g in adopted for k in cohorts.GROUPS[g]]
        choice[target] = {"kind": kind, "adopted": sorted(adopted), "keys": keys}
        if not keys:
            L += ["  nothing adopted -- no final model", ""]
            continue
        preds = W.predictions(rows, keys, target, kind, bars, vantages)
        for v, (test, p) in preds.items():
            m = W.metrics(test, p, target, bars[v])
            L.append(f"final model {v}: rank {m['rank']:.3f}, top25 {m['top25']:.2f}, "
                     f"top50 {m['top50']:.2f}, top100 {m['top100']:.2f} (n={m['n']})")
        if target == "soon":
            test = [r for v in preds for r in preds[v][0]]
            pred = np.concatenate([preds[v][1] for v in preds])
            L.append("calibration, pooled test cohorts (predicted -> actual):")
            L += [f"  {mp:.2f} -> {act:.2f}  (n={n})" for mp, act, n in W.calibration(test, pred)]
        hits = W.interactions_by_vantage(rows, keys, target, bars, vantages)
        L.append("interactions (trees; finding = top-10 at >=2 vantages):")
        for (a, b), vs in sorted(hits.items(), key=lambda t: (-len(t[1]), -statistics.fmean(h for _, h in t[1])))[:10]:
            L.append(f"  {a} x {b}: {len(vs)} vantage(s), strength {statistics.fmean(h for _, h in vs):.3f} "
                     f"-> {'finding' if len(vs) >= 2 else 'hypothesis'}")
        wp = hits.get(("whiff", "iso"))
        L.append(f"  whiff x power rematch (whiff x iso): "
                 + (f"top-10 at {len(wp)} vantage(s)" if wp else "not in any vantage's top 10"
                    if "whiff" in keys and "iso" in keys else "not testable (a group was dropped)"))
        L.append("")
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump(choice, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
