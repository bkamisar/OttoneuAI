"""Pitchers P-C: the stuff score -- what pitch tracking is worth, learned on MLB
(Savant, seasons t = 2015-2025, outcomes through 2026), translated to AAA, and
checked on real prospects. The pitcher counterpart of step1_run.py.

Usage:  python stuff_run.py
Reads only cached data (build_pitch_tracking.py first). Writes cache/stuff_report.txt,
cache/aaa_pitch_translation.csv and cache/stuff_choice.json (gitignored).
"""
import csv
import json
import os
import statistics

import numpy as np

import step1_run as S1
from psmodel import context, evaluate, interactions, milb, pcohorts, statsapi, step1, stuff

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "stuff_report.txt")
TRANSLATION = os.path.join(CACHE, "aaa_pitch_translation.csv")
CHOICE = os.path.join(CACHE, "stuff_choice.json")
MLB_FIRST, MLB_LAST = 2015, 2025        # season t; outcomes run through 2026
GATE_COHORTS, LATE_COHORT = (2022, 2023), (2024,)


def adoption_line(name, res):
    """step1_run.adoption_line, on the corrected P-C rule (stuff.adopt)."""
    ok, wins = stuff.adopt(res)
    return ok, (f"  {name:30} {'ADOPTED' if ok else 'rejected':9} {wins:2d}/10  "
                f"rho {S1.mean(res, 'rho_base'):.4f} -> {S1.mean(res, 'rho_fam'):.4f}  "
                f"top-50 {S1.mean(res, 'top_base'):.3f} -> {S1.mean(res, 'top_fam'):.3f}")


def finish(L, code):
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return code


def main():
    L = []
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB)
                 for s in range(MLB_FIRST, stuff.LAST_OUTCOME_SEASON + 1)}
    stats = {}
    for s, rs in by_season.items():
        for r in rs:
            if (r["player_id"], s) in stats:
                raise SystemExit(f"duplicate StatsAPI MLB pitching row for {r['player_id']} in {s}")
            stats[(r["player_id"], s)] = r
    values = stuff.season_values(by_season, den)
    threshold = stuff.useful_threshold(values)
    mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))

    all_keys = ["age"] + stuff.stuff_keys()
    box_base = ["age"] + stuff.BOX
    built = stuff.mlb_rows({k: v for k, v in mlb.items() if MLB_FIRST <= k[1] <= MLB_LAST}, values, stats, threshold)
    rows = step1.complete(built, all_keys + stuff.BOX)
    L += ["STUFF SCORE (P-C) -- what pitch tracking is worth (learned on MLB)",
          f"rows: {len(rows)} pitcher-seasons ({len(built) - len(rows)} dropped for a missing metric), "
          f"{len({r['player_id'] for r in rows})} pitchers, seasons t={MLB_FIRST}-{MLB_LAST}",
          f"target: next season's line valued at {stuff.WORKLOAD:g} IP (25+ IP next season); useful = >= "
          f"{threshold:.3f}, the typical {stuff.USEFUL_RANK}th-best ({sum(r['useful'] for r in rows)} useful rows)", ""]

    kind_rho = {kind: S1.mean_oof_rho(rows, all_keys, kind) for kind in evaluate.KINDS}
    kind = max(kind_rho, key=kind_rho.get)
    L += ["1. Model: " + ", ".join(f"{k} rho {v:.4f}" for k, v in kind_rho.items()) + f"  -> using {kind}", ""]

    L.append("2. Which groups earn their place (each vs age + all OTHER groups; rank gain in >=8/10 shuffles, mean top-50 change >= -0.04):")
    adopted = []
    for g in stuff.GROUPS:
        others = [k for h in stuff.GROUPS if h != g for k in stuff.GROUPS[h]]
        ok, line = adoption_line(g, evaluate.compare(rows, ["age"] + others, stuff.GROUPS[g],
                                                        seeds=S1.SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted.append(g)
    final_keys = ["age"] + stuff.stuff_keys(adopted)
    L += [f"  adopted groups: {adopted or 'NONE'}", ""]
    if not adopted:
        L.append("GATE: FAIL -- no stuff group earns its place on MLB; the stuff layer stops here")
        return finish(L, 1)

    ok, line = adoption_line("stuff on top of box", evaluate.compare(
        rows, box_base, stuff.stuff_keys(adopted), seeds=S1.SEEDS, kind=kind))
    L += ["3. Stuff vs box score (report only):",
          f"  box (age, K%, BB%) alone   rho {S1.mean_oof_rho(rows, box_base, kind):.4f}",
          f"  stuff + age alone          rho {S1.mean_oof_rho(rows, final_keys, kind):.4f}", line, ""]

    L.append("4. Robustness (adopted stuff vs age alone):")
    for name, keep in (("Hawk-Eye era only (t >= 2020)", lambda r: r["season"] >= 2020),
                       ("without 2020", lambda r: r["season"] not in (2019, 2020))):
        sub = [r for r in rows if keep(r)]
        L.append(adoption_line(name, evaluate.compare(sub, ["age"], stuff.stuff_keys(adopted),
                                                         seeds=S1.SEEDS, kind=kind))[1])
    L.append("")

    L.append("5. Strongest interactions (gbm, unnormalized H in SGP; finding = top-10 in >=8/10 runs):")
    counts, strength = {}, {}
    for s in range(S1.SEEDS):
        folds = evaluate.assign_folds(rows, 5, s)
        train = [r for r, f in zip(rows, folds) if f != 0]
        m = evaluate.fit(train, final_keys, "gbm")
        idx = np.random.default_rng(s).choice(len(train), size=min(100, len(train)), replace=False)
        X = np.array([[train[i]["f"][k] for k in final_keys] for i in idx], dtype=float)
        for h, a, b in interactions.top_pairs(m, X, final_keys, n=10):
            counts[(a, b)] = counts.get((a, b), 0) + 1
            strength.setdefault((a, b), []).append(h)
    for (a, b), c in sorted(counts.items(), key=lambda t: (-t[1], -statistics.fmean(strength[t[0]])))[:10]:
        L.append(f"  {a} x {b}: strength {statistics.fmean(strength[(a, b)]):.3f}, top-10 in {c}/10 "
                 f"-> {'finding' if c >= 8 else 'hypothesis'}")
    L.append("")

    tkeys = stuff.stuff_keys()
    translation = stuff.fit_translation(aaa, mlb, tkeys)
    with open(TRANSLATION, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "n", "offset", "lo", "hi", "slope_reported_not_applied"])
        for k in tkeys:
            t = translation[k]
            w.writerow([k, t["n"], t["offset"], t["lo"], t["hi"], t["slope"]])
    L.append(f"6. AAA -> MLB translation (same-season two-level pitchers, >={stuff.MIN_PITCH_PAIR} pitches at each level):")
    for k in tkeys:
        t = translation[k]
        L.append(f"  {k:16} n={t['n']:3d}  " + (
            f"offset {t['offset']:+.3f} [{t['lo']:+.3f}, {t['hi']:+.3f}]  slope {t['slope'] or float('nan'):.2f}"
            if t["offset"] is not None else "no pairs"))
    L.append("")

    model, box_model = evaluate.fit(rows, final_keys, kind), evaluate.fit(rows, box_base, kind)
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "adopted": adopted, "score_keys": final_keys, "threshold": threshold,
                   "workload": stuff.WORKLOAD, "mlb_seasons": [MLB_FIRST, MLB_LAST]}, fh, indent=2)

    aaa_stats = {(r["player_id"], s): r for s in GATE_COHORTS + LATE_COHORT
                 for r in milb.season_rows(s, statsapi.AAA, "pitching")}
    ip_history = pcohorts.mlb_ip_history()
    gate_pass = False
    L.append(f"7. Prospect check -- AAA pitchers (not established, first qualifying season) scored on {final_keys}")
    for name, cohorts, gates in (("2022-23 (GATE)", GATE_COHORTS, True), ("2024 (report only)", LATE_COHORT, False)):
        pr = step1.complete(stuff.aaa_rows(aaa, aaa_stats, values, cohorts, threshold, ip_history),
                            final_keys + box_base)
        arr = [i for i, r in enumerate(pr) if r["arrived"]]
        L.append(f"  {name}: {len(pr)} AAA pitchers, {len(arr)} reached a 25+ IP MLB season, "
                 f"{sum(r['useful'] for r in pr)} reached the useful line")
        if len(arr) < 10:
            L.append("    too few arrivals to test")
            continue
        for r in pr:
            r["f"] = step1.translate(r["f"], translation)
        score = evaluate.predict(model, pr, final_keys)
        box = evaluate.predict(box_model, pr, box_base)
        kpct = np.array([r["f"]["k"] for r in pr])
        outcome = [pr[i]["target"] for i in arr]
        for label, sc in (("stuff score", score), ("box-score model", box), ("AAA K%", kpct)):
            rho, lo, hi = step1.spearman_ci(sc[arr], outcome)
            L.append(f"    {label:16} Spearman vs later MLB value {rho:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            if gates and label == "stuff score":
                gate_pass = lo > 0
        order = np.argsort(-score)
        for q, chunk in enumerate(np.array_split(order, 5), 1):
            L.append(f"    score quintile {q}: arrived {np.mean([pr[i]['arrived'] for i in chunk]):.2f}, "
                     f"useful {np.mean([pr[i]['useful'] for i in chunk]):.2f}")
    L += ["", "GATE: " + ("PASS -- the stuff score ranks later MLB value above chance; the pitcher final plan "
                          "may test it as a layer" if gate_pass else
                          "FAIL -- stop; the stuff layer is not handed to the pitcher model")]
    return finish(L, 0 if gate_pass else 1)


if __name__ == "__main__":
    raise SystemExit(main())
