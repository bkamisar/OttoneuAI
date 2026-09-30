"""3c-hitters plan B: the final run.

1. Tests the tree leads (age x SLG, swstr x SLG) as explicit terms on the decision
   vantages, under the same adoption rule.
2. Reads the pulled-air parity verdict (pulled_air_parity.py must have run).
3. OPENS THE 2024 COHORT for "soon" and reports its metrics. The two decisions
   made at 2024's first opening (contact+approach kept; tracking-for-soon not
   used) are FROZEN -- re-deciding on a cohort already seen would be moving the
   goalposts.
4. Re-runs step 1's prospect gate with step 1 fit as-of each cohort.
5. Production fits as of 2026 -> cache/hitter_ratings.csv.

Usage:  python model3c_final.py
Reads only cached data. Writes cache/model3c_final_report.txt,
cache/model3c_final.json and cache/hitter_ratings.csv (gitignored).
"""
import csv
import json
import os
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset, evaluate, milb, statsapi, step1
from psmodel import tracking_layer as TL
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
REPORT = os.path.join(CACHE, "model3c_final_report.txt")
DECISIONS = os.path.join(CACHE, "model3c_final.json")
RATINGS = os.path.join(CACHE, "hitter_ratings.csv")
PRODUCTION = cohorts.CURRENT_SEASON
AAA_TRACKED = (2022, 2023, 2024, 2025, 2026)
FROZEN_SOON_GROUPS = ("contact", "approach")   # kept at 2024's first opening (2026-09-27); never re-decided
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def load(name):
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return json.load(fh)


def fmt(res):
    return "; ".join(f"{v}: n/a" if r is None else
                     f"{v}: {r['d']:+.4f} (z {W.z_score(r['d'], r['se']):+.1f}) "
                     f"t50 {r['base']['top50']:.2f}->{r['fam']['top50']:.2f}" for v, r in res.items())


def safe(text):
    """CSV-injection guard for the one free-text column."""
    s = "" if text is None else str(text)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def scored(rows, scores):
    """(indices of AAA rows with a tracking score, their scores)."""
    idx = [i for i, r in enumerate(rows)
           if r["sport_id"] == statsapi.AAA and (r["player_id"], r["season"]) in scores]
    return idx, np.array([scores[(rows[i]["player_id"], rows[i]["season"])] for i in idx], dtype=float)


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels)
    rows = cohorts.build_rows(cohorts.load_milb(), cohorts.mlb_pa_history(),
                              {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    cohorts.add_products(rows)
    choice, s1, parity = load("model3c_choice.json"), load("step1_choice.json"), load("pulled_air_parity.json")
    mlb_table = step1.load_table(os.path.join(CACHE, "mlb_tracking.csv"))
    aaa_table = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    seasons = step1.hitter_seasons(labels)
    mlb_stats = {(r["player_id"], s): r for s in range(2015, PRODUCTION)
                 for r in statsapi.season_stats(s, "hitting", statsapi.MLB)}
    aaa_stats = {(r["player_id"], s): r for s in AAA_TRACKED
                 for r in milb.season_rows(s, statsapi.AAA, "hitting")}
    s1_keys = TL.step1_keys(s1)

    def tracking_scores(v, wanted):
        model = TL.step1_model(v, mlb_table, seasons, mlb_stats, s1_keys, s1["kind"])
        off = TL.offsets(v, aaa_table, mlb_table, [k for k in s1_keys if k != "age"])
        return TL.aaa_scores(aaa_table, aaa_stats, model, off, s1_keys, set(wanted))

    L, decisions = ["3c-HITTERS FINAL RUN (plan B)", ""], {}
    keys = {t: list(choice[t]["keys"]) for t in ("rating", "soon")}
    for g in FROZEN_SOON_GROUPS:
        if g not in choice["soon"]["adopted"]:
            keys["soon"] += [k for k in cohorts.GROUPS[g] if k not in keys["soon"]]
            L.append(f"NOTE: the base run dropped '{g}' for soon; restored by the 2024 freeze")
    vants = {"rating": W.RATING_VANTAGES, "soon": W.SOON_VANTAGES}

    L.append("1. Tree leads as explicit terms (decision vantages, same adoption rule):")
    for t in ("rating", "soon"):
        bars = {v: asof.ref_curve(labels, v) for v in vants[t]}
        for lead, parents in cohorts.LEADS.items():
            if not all(p in keys[t] for p in parents):
                L.append(f"  {t:6} {lead:12} not testable (a parent feature was dropped)")
                continue
            res = W.compare(rows, keys[t], [lead], t, choice[t]["kind"], bars, vants[t])
            ok, wins, avail = W.adopt(res)
            L.append(f"  {t:6} {lead:12} {'ADOPT' if ok else 'drop':5} {wins}/{avail}  {fmt(res)}")
            if ok:
                keys[t].append(lead)
    L.append("")

    L.append(f"2. Pulled-air parity: pulled part (FB regressed out both sides) r = {parity['r_pulled_part']:.4f} "
             f"(raw product r {parity['r_product_raw']:.4f}, pull alone {parity['r_pull']:.4f}, n={parity['n']}) "
             f"-> {'PASS' if parity['passed'] else 'FAIL'}")
    if parity["passed"]:
        print("\n".join(L))
        raise SystemExit("pulled-air parity PASSED -- stop and hand to Opus for the follow-up plan")
    L += ["   pulled air stays a documented hypothesis; not used for AAA", ""]

    kind_s = choice["soon"]["kind"]
    bar24 = asof.ref_curve(labels, 2024)
    L.append("3. SEALED 2024 COHORT OPENED (soon only; the rating's 4-year answers for 2024 aren't in yet)")
    L.append("  2024 decisions are FROZEN from its first opening (2026-09-27, first labels): contact+approach "
             "kept, tracking-for-soon not used. The numbers below are for information only.")
    test24, p24 = W.predictions(rows, keys["soon"], "soon", kind_s, {2024: bar24}, (2024,), unseal=True)[2024]
    m = W.metrics(test24, p24, "soon", bar24)
    L.append(f"  final 'soon' model on 2024: AUC {m['rank']:.3f}, top25 {m['top25']:.2f}, "
             f"top50 {m['top50']:.2f}, top100 {m['top100']:.2f} (n={m['n']})")
    L += [f"    calibration {mp:.2f} -> {act:.2f} (n={n})" for mp, act, n in W.calibration(test24, p24)]

    scores24 = tracking_scores(2024, (2022, 2024))
    train, test = W.frames(rows, "soon", 2024, bar24, keys["soon"], unseal=True)
    oof = W.oof(train, keys["soon"], "soon", kind_s)
    _, pte = W.fit_predict(train, test, keys["soon"], "soon", kind_s)
    itr, s_tr = scored(train, scores24)
    ite, s_te = scored(test, scores24)
    resid_tr, (a, b) = TL.residualize(s_tr, oof[itr])
    w, lo, hi = TL.trust_weight("soon", [train[i]["y"] for i in itr], oof[itr], resid_tr,
                                np.ones(len(itr)), [train[i]["player_id"] for i in itr])
    b_te = pte[ite]
    adj = TL.adjust("soon", b_te, s_te - (a + b * b_te), w)
    sub = [test[i] for i in ite]
    d, se = W.paired_gain(sub, b_te, adj, "soon")
    mb, ma = W.metrics(sub, b_te, "soon", bar24), W.metrics(sub, adj, "soon", bar24)
    would_use = (lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z
    use_soon = False            # frozen at 2024's first opening
    L += [f"  tracking layer for 'soon': trained on {len(itr)} AAA-2022 hitters, w {w:+.3f} [{lo:+.3f}, {hi:+.3f}]",
          f"    on {len(ite)} AAA-2024 hitters: AUC {mb['rank']:.3f} -> {ma['rank']:.3f} "
          f"(z {W.z_score(d, se):+.1f}), top50 {mb['top50']:.2f} -> {ma['top50']:.2f} "
          f"-> frozen: not used (this run alone would say {'use' if would_use else 'do not use'})", ""]

    gate_rows = step1.complete(step1.aaa_rows(aaa_table, aaa_stats, seasons, (2022, 2023), s1["threshold"]),
                               s1_keys)
    sc = {}
    for c in (2022, 2023):
        sc.update(tracking_scores(c, (c,)))
    gate = [r for r in gate_rows if r["arrived"] and (r["player_id"], r["season"]) in sc]
    rho, glo, ghi = step1.spearman_ci([sc[(r["player_id"], r["season"])] for r in gate], [r["target"] for r in gate])
    L += [f"4. Step-1 prospect gate, as-of (step 1 fit through each cohort's own year): {len(gate)} arrivals, "
          f"Spearman {rho:+.3f} [{glo:+.3f}, {ghi:+.3f}] (first run, fit through 2025: +0.391) "
          f"-> {'PASS' if glo > 0 else 'FAIL'}", ""]

    L.append(f"5. Production, as of {PRODUCTION}:")
    bar_now = asof.ref_curve(labels, PRODUCTION)
    scores_now = tracking_scores(PRODUCTION, AAA_TRACKED)
    out = {}
    for t in ("rating", "soon"):
        kind = choice[t]["kind"]
        m_t, train, test, pred = W.production(rows, keys[t], t, kind, bar_now, PRODUCTION)
        itr, s_tr = scored(train, scores_now)
        b_tr = W.oof(train, keys[t], t, kind)[itr]
        y_tr = np.array([train[i]["y"] for i in itr], dtype=float)
        wt = np.ones(len(itr))
        pids = [train[i]["player_id"] for i in itr]
        if t == "rating":       # add the partly observed 2023-24 AAA cohorts, weighted by the share known
            extra = [r for r in rows if r["season"] in (2023, 2024) and r["sport_id"] == statsapi.AAA
                     and (r["player_id"], r["season"]) in scores_now
                     and all(r["f"].get(k) is not None for k in keys[t])]
            if extra:
                s_tr = np.concatenate([s_tr, [scores_now[(r["player_id"], r["season"])] for r in extra]])
                b_tr = np.concatenate([b_tr, evaluate.predict(m_t, extra, keys[t])])
                y_tr = np.concatenate([y_tr, [asof.rating_target(r["mlb"], r["season"], bar_now) for r in extra]])
                wt = np.concatenate([wt, [(PRODUCTION - r["season"]) / asof.RATING_YEARS for r in extra]])
                pids += [r["player_id"] for r in extra]
        resid_tr, (a, b) = TL.residualize(s_tr, b_tr)
        w, lo, hi = TL.trust_weight(t, y_tr, b_tr, resid_tr, wt, pids)
        use = (lo > 0 or hi < 0) and (t == "rating" or use_soon)
        L.append(f"  {t}: {kind} on {len(train)} rows; tracking w {w:+.3f} [{lo:+.3f}, {hi:+.3f}] from "
                 f"{len(y_tr)} AAA hitter-seasons -> "
                 + (("applied" + (" (PROVISIONAL: no later complete cohort to check it)" if t == "rating" else ""))
                    if use else "not applied"))
        final = np.array(pred, dtype=float)
        ite, s_te = scored(test, scores_now)
        if use and ite:
            final[ite] = TL.adjust(t, final[ite], s_te - (a + b * final[ite]), w)
        out[t] = {"test": test, "pred": final, "tracked": set(ite) if use else set()}
        decisions[t] = {"kind": kind, "keys": keys[t], "tracking_w": w, "tracking_ci": [lo, hi],
                        "tracking_used": bool(use)}
    decisions["soon"]["tracking_2024_check"] = {"auc_gain": d, "se": se, "used": bool(use_soon)}
    decisions["step1_gate_asof"] = {"n": len(gate), "rho": rho, "ci": [glo, ghi]}

    by = {}
    for t in ("rating", "soon"):
        for i, (r, p) in enumerate(zip(out[t]["test"], out[t]["pred"])):
            e = by.setdefault((r["player_id"], r["sport_id"]), {"r": r})
            e[t], e[t + "_tracked"] = float(p), i in out[t]["tracked"]
    best = {}
    for (pid, sid), e in by.items():            # one row per player: the highest level (lowest sportId)
        if "rating" in e and "soon" in e and (pid not in best or sid < best[pid]["r"]["sport_id"]):
            best[pid] = e
    ranked = sorted(best.values(), key=lambda e: e["rating"])
    for i, e in enumerate(ranked):
        e["pct"] = 100.0 * (i + 1) / len(ranked)
    with open(RATINGS, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["player_id", "name", "level", "age", "rating_sgp", "rating_percentile",
                     "p_useful_within_2", "tracking_in_rating", "tracking_in_soon", "flags"])
        for e in sorted(ranked, key=lambda e: -e["rating"]):
            r = e["r"]
            wr.writerow([r["player_id"], safe(r["name"]), cohorts.LEVEL_NAMES[r["sport_id"]], r["age_raw"],
                         f"{e['rating']:.3f}", f"{e['pct']:.1f}", f"{e['soon']:.3f}",
                         "yes" if e["rating_tracked"] else "no", "yes" if e["soon_tracked"] else "no",
                         "rating tracking provisional" if e["rating_tracked"] else ""])
    L.append(f"  wrote {len(ranked)} hitters -> {RATINGS}")
    L.append("  top 15 by rating: " + "; ".join(
        f"{e['r']['name']} ({cohorts.LEVEL_NAMES[e['r']['sport_id']]}, {e['r']['age_raw']}) "
        f"{e['rating']:.2f}/{e['soon']:.0%}" for e in sorted(ranked, key=lambda e: -e["rating"])[:15]))

    with open(DECISIONS, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
