"""Step 1 of the prospect model: what hitter tracking metrics are worth, learned on
MLB, translated to AAA, and checked on real prospects.

Usage:  python step1_run.py
Writes cache/step1_report.txt, cache/aaa_translation.csv and cache/step1_choice.json
(gitignored). Network: StatsAPI AAA season stats 2022-2024 (age, box score) on the
first run, cached after. Run the security audit first.
"""
import csv
import json
import os
import statistics

import numpy as np
from scipy.stats import spearmanr

from psmodel import dataset, evaluate, interactions, statsapi, step1

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "step1_report.txt")
TRANSLATION = os.path.join(CACHE, "aaa_translation.csv")
CHOICE = os.path.join(CACHE, "step1_choice.json")
SEEDS = 10
MLB_FIRST, MLB_LAST = 2015, 2025        # season t; outcomes run through 2026
GATE_COHORTS, LATE_COHORT = (2022, 2023), (2024,)
SPRAY = set(step1.GROUPS["spray"])


def stats_index(sport_id, seasons):
    out = {}
    for s in seasons:
        for r in statsapi.season_stats(s, "hitting", sport_id):
            if (r["player_id"], s) in out:
                raise SystemExit(f"duplicate StatsAPI row for {r['player_id']} in {s} (sport {sport_id})")
            out[(r["player_id"], s)] = r
    return out


def mean(results, key):
    return statistics.fmean(r[key] for r in results)


def mean_oof_rho(rows, keys, kind):
    y = [r["target"] for r in rows]
    return statistics.fmean(float(spearmanr(evaluate.oof_predictions(rows, keys, 5, s, kind), y).statistic)
                            for s in range(SEEDS))


def adoption_line(name, res):
    ok, wins = evaluate.adopt(res)
    return ok, (f"  {name:26} {'ADOPTED' if ok else 'rejected':9} {wins:2d}/10  "
                f"rho {mean(res, 'rho_base'):.4f} -> {mean(res, 'rho_fam'):.4f}  "
                f"top-50 {mean(res, 'top_base'):.3f} -> {mean(res, 'top_fam'):.3f}")


def main():
    L = []
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    threshold = dataset.useful_threshold(labels, "H")
    seasons = step1.hitter_seasons(labels)
    mlb = step1.load_table(os.path.join(CACHE, "mlb_tracking.csv"))
    aaa = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    mlb_stats = stats_index(statsapi.MLB, range(MLB_FIRST, MLB_LAST + 1))

    all_keys = ["age"] + step1.tracking_keys()
    built = step1.mlb_rows({k: v for k, v in mlb.items() if MLB_FIRST <= k[1] <= MLB_LAST},
                           seasons, mlb_stats, threshold)
    rows = step1.complete(built, all_keys + step1.BOX)
    L += ["STEP 1 -- what hitter tracking metrics are worth (learned on MLB)",
          f"rows: {len(rows)} hitter-seasons ({len(built) - len(rows)} dropped for a missing metric), "
          f"{len({r['player_id'] for r in rows})} players, seasons t={MLB_FIRST}-{MLB_LAST}",
          f"target: next-season 4x4 SGP at 600 PA; useful = >= {threshold:.3f} "
          f"({sum(r['useful'] for r in rows)} useful rows)", ""]

    kind_rho = {kind: mean_oof_rho(rows, all_keys, kind) for kind in evaluate.KINDS}
    kind = max(kind_rho, key=kind_rho.get)
    L += ["1. Model: " + ", ".join(f"{k} rho {v:.4f}" for k, v in kind_rho.items()) + f"  -> using {kind}", ""]

    L.append("2. Which groups earn their place (each vs age + all OTHER groups, 8/10 rule):")
    adopted = []
    for g in step1.GROUPS:
        others = [k for h in step1.GROUPS if h != g for k in step1.GROUPS[h]]
        ok, line = adoption_line(g, evaluate.compare(rows, ["age"] + others, step1.GROUPS[g],
                                                     seeds=SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted.append(g)
    if "power" not in adopted and "launch" not in adopted:
        others = [k for h in step1.GROUPS if h not in ("power", "launch") for k in step1.GROUPS[h]]
        ok, line = adoption_line("power + launch (jointly)", evaluate.compare(
            rows, ["age"] + others, step1.GROUPS["power"] + step1.GROUPS["launch"], seeds=SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted += ["power", "launch"]
    final_keys = ["age"] + step1.tracking_keys(adopted)
    L += [f"  adopted groups: {adopted or 'NONE'}", ""]

    if len(final_keys) > 1:
        box_base = ["age"] + step1.BOX
        ok, line = adoption_line("tracking on top of box", evaluate.compare(
            rows, box_base, step1.tracking_keys(adopted), seeds=SEEDS, kind=kind))
        L += ["3. Tracking vs box score (report only):",
              f"  box score + age alone      rho {mean_oof_rho(rows, box_base, kind):.4f}",
              f"  tracking + age alone       rho {mean_oof_rho(rows, final_keys, kind):.4f}", line, ""]

        L.append("4. Robustness (adopted tracking vs age alone):")
        for name, drop in (("without 2015", lambda r: r["season"] == 2015),
                           ("without 2020", lambda r: r["season"] in (2019, 2020))):
            sub = [r for r in rows if not drop(r)]
            L.append(adoption_line(name, evaluate.compare(sub, ["age"], step1.tracking_keys(adopted),
                                                          seeds=SEEDS, kind=kind))[1])
        L.append("")

        L.append("5. Strongest interactions (gbm, unnormalized H in SGP; finding = top-10 in >=8/10 runs):")
        counts, strength = {}, {}
        for s in range(SEEDS):
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

    tkeys = [k for k in step1.tracking_keys() if k not in SPRAY]
    translation = step1.fit_translation(aaa, mlb, tkeys)
    with open(TRANSLATION, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "n", "offset", "lo", "hi", "slope_reported_not_applied"])
        for k in tkeys:
            t = translation[k]
            w.writerow([k, t["n"], t["offset"], t["lo"], t["hi"], t["slope"]])
    L.append("6. AAA -> MLB translation (same-season two-level hitters, >=50 batted balls at each level):")
    for k in tkeys:
        t = translation[k]
        L.append(f"  {k:22} n={t['n']:3d}  " + (
            f"offset {t['offset']:+.3f} [{t['lo']:+.3f}, {t['hi']:+.3f}]  slope {t['slope'] or float('nan'):.2f}"
            if t["offset"] is not None else "no pairs"))
    L.append("")

    score_keys = [k for k in final_keys if k not in SPRAY]
    box_base = ["age"] + step1.BOX
    model, box_model = evaluate.fit(rows, score_keys, kind), evaluate.fit(rows, box_base, kind)
    # 3c rebuilds the score from these choices (refit on demand; nothing serialized but JSON).
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "adopted": adopted, "score_keys": score_keys,
                   "threshold": threshold, "mlb_seasons": [MLB_FIRST, MLB_LAST]}, fh, indent=2)
    aaa_stats = stats_index(statsapi.AAA, GATE_COHORTS + LATE_COHORT)
    gate_pass = False
    L.append(f"7. Prospect check -- AAA hitters scored on {score_keys} (spray excluded: not measurable in AAA)")
    for name, cohorts, gates in (("2022-23 (GATE)", GATE_COHORTS, True), ("2024 (report only)", LATE_COHORT, False)):
        pr = step1.complete(step1.aaa_rows(aaa, aaa_stats, seasons, cohorts, threshold), score_keys + box_base)
        arr = [i for i, r in enumerate(pr) if r["arrived"]]
        L.append(f"  {name}: {len(pr)} AAA hitters, {len(arr)} reached 100+ MLB PA, "
                 f"{sum(r['useful'] for r in pr)} became starter-quality")
        if len(arr) < 10:
            L.append("    too few arrivals to test")
            continue
        for r in pr:
            r["f"] = step1.translate(r["f"], translation)
        score = evaluate.predict(model, pr, score_keys)
        box = evaluate.predict(box_model, pr, box_base)
        ops = np.array([r["f"]["obp"] + r["f"]["slg"] for r in pr])
        outcome = [pr[i]["target"] for i in arr]
        for label, s in (("tracking score", score), ("box-score model", box), ("AAA OPS", ops)):
            rho, lo, hi = step1.spearman_ci(s[arr], outcome)
            L.append(f"    {label:16} Spearman vs later MLB value {rho:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            if gates and label == "tracking score":
                gate_pass = lo > 0
        order = np.argsort(-score)
        for q, chunk in enumerate(np.array_split(order, 5), 1):
            L.append(f"    score quintile {q}: arrived {np.mean([pr[i]['arrived'] for i in chunk]):.2f}, "
                     f"starter-quality {np.mean([pr[i]['useful'] for i in chunk]):.2f}")
    L.append("")

    if "spray" in adopted:
        L.append("SPRAY: ADOPTED on MLB -- the user's hypothesis holds there. AAA scoring leaves it out until "
                 "the follow-up spray-parity plan (our coordinate-based version vs Savant on the 2023-26 "
                 "MLB game records).")
    else:
        L.append("SPRAY: not adopted -- direction adds nothing beyond the other groups on MLB. No follow-up.")
    L.append("GATE: " + ("PASS -- the tracking score ranks later MLB success above chance; 3c may use it"
                         if gate_pass else "FAIL -- stop; do not hand the score to 3c until resolved"))

    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
