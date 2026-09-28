"""Pitchers plan P-A: as-of walk-forward backtests of the pitcher base model, for
both outputs -- rating (best pitcher season in the next 4, 25+ IP) and soon (a
top-120 pitcher season within 2). Model choice, group importance, interactions,
calibration. 2024 stays sealed for the final check.

Usage:  python model_p_base.py
Reads only cached data (pull_pitcher_data.py and build_labels.py first).
Writes cache/model_p_base_report.txt and cache/model_p_choice.json (gitignored).
"""
import json
import os
import statistics
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset, pcohorts
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model_p_base_report.txt")
CHOICE = os.path.join(CACHE, "model_p_choice.json")
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['d']:+.4f} (z {W.z_score(r['d'], r['se']):+.1f}) "
                     f"t50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f} "
                     f"t100 {r['base']['top100']:.2f}->{r['fam']['top100']:.2f}"
                     for v, r in res.items())


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels, "P")
    mlb = {pid: rows for (pid, typ), rows in labels.items() if typ == "P"}
    rows = pcohorts.build_rows(pcohorts.load_milb(), pcohorts.mlb_ip_history(), mlb)
    L = ["PITCHERS BASE MODEL -- as-of walk-forward backtests (2024 sealed)",
         f"rows: {len(rows)} pitcher-season-levels, {len({r['player_id'] for r in rows})} players",
         "per season: " + ", ".join(f"{s} {sum(1 for r in rows if r['season'] == s)}"
                                    for s in cohorts.MILB_SEASONS), ""]
    all_keys = [k for g in pcohorts.GROUPS.values() for k in g]
    choice = {}
    for target, vantages in (("rating", W.RATING_VANTAGES), ("soon", W.SOON_VANTAGES)):
        bars = {v: asof.ref_curve(labels, v, "P") for v in vantages}
        simple, complex_ = W.KINDS[target]
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; useful line (typical value of pitcher rank "
                 f"{asof.STARTERS_BY['P']}) as-of: "
                 + ", ".join(f"{v} {asof.useful_value(b, 'P'):.3f}" for v, b in bars.items()))
        kind, kres = W.choose_kind(rows, all_keys, target, bars, vantages)
        L.append(f"model: {kind}  (" + "; ".join(
            f"{v}: n/a" if r is None else f"{v}: {simple} {r[0]['rank']:.3f} vs {complex_} {r[1]['rank']:.3f}"
            for v, r in kres.items()) + ")")
        L.append(f"groups -- drop-and-refit; KEEP = rank gain >= {W.WIN_Z:g} SE at >=2 vantages, none <= "
                 f"{W.HARM_Z:g} SE, mean top-50 change >= -{W.TOP50_TOLERANCE:g}:")
        adopted = set()
        for gs, res in W.group_importance(rows, pcohorts.GROUPS, target, kind, bars, vantages).items():
            ok, wins, avail = W.adopt(res)
            L.append(f"  {' + '.join(gs):28} {'KEEP' if ok else 'drop':4} {wins}/{avail}  {fmt(res)}")
            if ok:
                adopted.update(gs)
        keys = [k for g in pcohorts.GROUPS if g in adopted for k in pcohorts.GROUPS[g]]
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
        tree_wins = sum(1 for r in kres.values() if r is not None and r[1]["rank"] > r[0]["rank"])
        L.append(f"patterns the TREE model leans on ({complex_} beat {simple} at {tree_wins}/{len(vantages)} "
                 f"vantages; leads to test as explicit terms, not findings; 'replicated' = top-10 at >=2):")
        for (a, b), vs in sorted(hits.items(), key=lambda t: (-len(t[1]), -statistics.fmean(h for _, h in t[1])))[:10]:
            L.append(f"  {a} x {b}: {len(vs)} vantage(s), strength {statistics.fmean(h for _, h in vs):.3f} "
                     f"-> {'replicated' if len(vs) >= 2 else 'one vantage'}")
        L.append("")
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump(choice, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
