"""Pitchers plan P-D: the final run (spec: docs/superpowers/specs/2026-09-28-pitchers-design.md,
"P-D: the pitcher final run"; every rule below was fixed before 2024 was opened).

1. Tests the rating tree leads (age x K, age x CSW) as explicit terms on the
   decision vantages, under the usual adoption rule.
2. OPENS THE SEALED 2024 PITCHER CLASS ONCE, for "soon": (a) trees vs plain logit,
   (b) the stuff layer on the chosen model. Both decisions are written to
   cache/model_p_2024_decisions.json the moment they are made; a later run reads
   them and never re-decides.
3. Carries P-E's as-of stuff gate.
4. Production fits as of 2026 -> cache/pitcher_ratings.csv.

Usage:  python model_p_final.py [--no-open]
  --no-open  run everything up to the 2024 opening (leads, stuff scores, frames), then stop.
Reads only cached data. Writes cache/model_p_final_report.txt, cache/model_p_final.json
and cache/pitcher_ratings.csv (gitignored).
"""
import argparse
import csv
import json
import os
import statistics
import warnings

import numpy as np

from psmodel import asof, cohorts, context, dataset, evaluate, milb, pcohorts, statsapi, step1, stuff
from psmodel import pfinal as PF
from psmodel import stuff_layer as SL
from psmodel import tracking_layer as TL
from psmodel import walkforward as W
from model3c_final import fmt, safe

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "model_p_final_report.txt")
DECISIONS = os.path.join(CACHE, "model_p_final.json")
FROZEN = os.path.join(CACHE, "model_p_2024_decisions.json")
RATINGS = os.path.join(CACHE, "pitcher_ratings.csv")
PRODUCTION = cohorts.CURRENT_SEASON
AAA_TRACKED = (2022, 2023, 2024, 2025, 2026)
MIN_LAYER_ROWS = 30          # scored training rows below which the layer weight isn't fit
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def load(name):
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return json.load(fh)


def scored(rows, scores):
    """(indices of AAA rows with a stuff score, their scores)."""
    idx = [i for i, r in enumerate(rows)
           if r["sport_id"] == statsapi.AAA and (r["player_id"], r["season"]) in scores]
    return idx, np.array([scores[(rows[i]["player_id"], rows[i]["season"])] for i in idx], dtype=float)


def plain(m):
    return {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in m.items()}


def finish(L):
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true", help="stop before the 2024 opening")
    args = ap.parse_args()

    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels, "P")
    mlb = {pid: rs for (pid, typ), rs in labels.items() if typ == "P"}
    rows = pcohorts.add_products(pcohorts.build_rows(pcohorts.load_milb(), pcohorts.mlb_ip_history(), mlb))
    choice, sc, final = load("model_p_choice.json"), load("stuff_choice.json"), load("stuff_choice_final.json")
    if final["choice"] != "season":
        raise SystemExit(f"stuff_choice_final.json says {final['choice']!r}; this run is written for 'season'")
    s_keys, s_kind = sc["score_keys"], sc["kind"]
    s_metrics = [k for k in s_keys if k != "age"]
    sv_mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    sv_aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB)
                 for s in range(2015, stuff.LAST_OUTCOME_SEASON + 1)}
    mlb_stats = {(r["player_id"], s): r for s, rs in by_season.items() for r in rs}
    values = stuff.season_values(by_season, den)
    aaa_stats = {(r["player_id"], s): r for s in AAA_TRACKED for r in milb.season_rows(s, statsapi.AAA, "pitching")}

    def stuff_scores(v, wanted):
        model = SL.stuff_model(v, sv_mlb, values, mlb_stats, s_keys, s_kind)
        off = SL.offsets(v, sv_aaa, sv_mlb, s_metrics)
        return SL.aaa_scores(sv_aaa, aaa_stats, model, off, s_keys, set(wanted))

    L, decisions = ["PITCHERS FINAL RUN (P-D)",
                    f"rows: {len(rows)} pitcher-season-levels; stuff score = P-C season-level {s_keys} ({s_kind})", ""], {}
    keys = {t: list(choice[t]["keys"]) for t in ("rating", "soon")}

    L.append("1. Rating tree leads as explicit terms (decision vantages, same adoption rule):")
    bars = {v: asof.ref_curve(labels, v, "P") for v in W.RATING_VANTAGES}
    decisions["leads"] = {}
    for lead, parents in pcohorts.LEADS.items():
        if not all(p in choice["rating"]["keys"] for p in parents):
            L.append(f"  {lead:10} not testable (a parent feature was dropped)")
            continue
        res = W.compare(rows, choice["rating"]["keys"], [lead], "rating", choice["rating"]["kind"], bars,
                        W.RATING_VANTAGES)
        ok, wins, avail = W.adopt(res)
        L.append(f"  {lead:10} {'ADOPT' if ok else 'drop':5} {wins}/{avail}  {fmt(res)}")
        decisions["leads"][lead] = bool(ok)
        if ok:
            keys["rating"].append(lead)
    L.append("")

    bar24 = asof.ref_curve(labels, 2024, "P")
    scores24 = stuff_scores(2024, (2022, 2024))
    train, test = W.frames(rows, "soon", 2024, bar24, keys["soon"], unseal=True)
    itr, s_tr = scored(train, scores24)
    ite, s_te = scored(test, scores24)
    L.append(f"Pre-flight: 'soon' as-of 2024 trains on {len(train)} rows, {len(itr)} AAA-2022 with a stuff score; "
             f"the 2024 class has {len(test)} rows, {len(ite)} AAA with a stuff score")
    if args.no_open:
        L.append("--no-open: stopping before the 2024 opening")
        return finish(L)

    frozen = PF.load_frozen(FROZEN)
    L.append("")
    L.append("2. SEALED 2024 PITCHER CLASS (soon only; rating answers for 2024 aren't in yet)")
    if frozen is not None:
        L.append(f"  decisions FROZEN from the first opening ({FROZEN}); reported, not re-decided")
    else:
        res = {}
        for kind in ("gbm", "logit"):
            t24, p24 = W.predictions(rows, keys["soon"], "soon", kind, {2024: bar24}, (2024,), unseal=True)[2024]
            m = plain(W.metrics(t24, p24, "soon", bar24))
            m["buckets"] = [list(map(float, b[:2])) + [int(b[2])] for b in W.calibration(t24, p24)]
            m["calib"] = PF.calibration_error(m["buckets"])
            res[kind] = m
        kind_s = PF.soon_kind(res["gbm"], res["logit"])

        oof = W.oof(train, keys["soon"], "soon", kind_s)
        _, pte = W.fit_predict(train, test, keys["soon"], "soon", kind_s)
        y_tr = [train[i]["y"] for i in itr]
        layer = {"n_train": len(itr), "train_hits": int(sum(y_tr)), "n_test": len(ite)}
        use_soon = False
        if len(itr) >= MIN_LAYER_ROWS and 0 < sum(y_tr) < len(y_tr) and ite:
            resid_tr, (a, b) = TL.residualize(s_tr, oof[itr])
            w, lo, hi = TL.trust_weight("soon", y_tr, oof[itr], resid_tr, np.ones(len(itr)),
                                        [train[i]["player_id"] for i in itr])
            b_te = pte[ite]
            adj = TL.adjust("soon", b_te, s_te - (a + b * b_te), w)
            sub = [test[i] for i in ite]
            d, se = W.paired_gain(sub, b_te, adj, "soon")
            mb, ma = W.metrics(sub, b_te, "soon", bar24), W.metrics(sub, adj, "soon", bar24)
            use_soon = bool((lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z)
            layer.update({"w": float(w), "ci": [float(lo), float(hi)], "auc_gain": float(d), "se": float(se),
                          "z": float(W.z_score(d, se)),
                          "auc_before": float(mb["rank"]), "auc_after": float(ma["rank"]),
                          "top50_before": float(mb["top50"]), "top50_after": float(ma["top50"]),
                          "test_hits": int(sum(r["y"] for r in sub))})
        else:
            layer["note"] = "too few scored rows or no outcome variation to fit the weight -- rule not met"
        frozen = {"soon_kind": kind_s, "kinds": res, "stuff_layer": layer, "use_soon_stuff": use_soon,
                  "percent_ok": bool(PF.percent_ok(res[kind_s]["buckets"]))}
        PF.freeze(FROZEN, frozen)
        L.append(f"  decisions made now and FROZEN to {FROZEN}")

    for kind in ("gbm", "logit"):
        m = frozen["kinds"][kind]
        L.append(f"  a. {kind:5}: AUC {m['rank']:.3f}, top25 {m['top25']:.2f}, top50 {m['top50']:.2f}, "
                 f"top100 {m['top100']:.2f}, calibration error {m['calib']:.4f} (n={m['n']})")
        L += [f"       {mp:.3f} -> {act:.3f} (n={n})" for mp, act, n in m["buckets"]]
    kind_s = frozen["soon_kind"]
    L.append(f"     rule (logit only if strictly better on top-50 AND calibration error) -> 'soon' uses {kind_s}")
    ly = frozen["stuff_layer"]
    if "w" in ly:
        L.append(f"  b. stuff layer for 'soon' on {kind_s}: trained on {ly['n_train']} AAA-2022 pitchers "
                 f"({ly['train_hits']} hits), w {ly['w']:+.3f} [{ly['ci'][0]:+.3f}, {ly['ci'][1]:+.3f}]")
        L.append(f"     on {ly['n_test']} AAA-2024 pitchers ({ly['test_hits']} hits): AUC {ly['auc_before']:.3f} -> "
                 f"{ly['auc_after']:.3f} (z {ly['z']:+.1f}), top50 {ly['top50_before']:.2f} -> {ly['top50_after']:.2f}")
    else:
        L.append(f"  b. stuff layer for 'soon': {ly['note']} (n_train {ly['n_train']}, hits {ly['train_hits']})")
    L.append(f"     rule (CI excludes 0 AND z >= {W.WIN_Z:g}) -> {'USE' if frozen['use_soon_stuff'] else 'not used'}")
    L.append(f"  soon odds as percentages (top bucket and overall inside the 95% Wilson interval): "
             f"{'OK' if frozen['percent_ok'] else 'NO -- rank tiers only'}")
    L.append("")
    decisions["sealed_2024"] = frozen

    g = final["season"]["rho_ci"]
    L += [f"3. As-of stuff gate (P-E, not rerun): season-level Spearman {g[0]:+.3f} [{g[1]:+.3f}, {g[2]:+.3f}] "
          f"on {final['n_arrived']} arrivals", ""]

    L.append(f"4. Production, as of {PRODUCTION}:")
    bar_now = asof.ref_curve(labels, PRODUCTION, "P")
    scores_now = stuff_scores(PRODUCTION, AAA_TRACKED)
    kinds = {"rating": choice["rating"]["kind"], "soon": kind_s}
    out = {}
    for t in ("rating", "soon"):
        kind = kinds[t]
        m_t, tr, te, pred = W.production(rows, keys[t], t, kind, bar_now, PRODUCTION)
        i_tr, sc_tr = scored(tr, scores_now)
        b_tr = W.oof(tr, keys[t], t, kind)[i_tr]
        yv = np.array([tr[i]["y"] for i in i_tr], dtype=float)
        wt = np.ones(len(i_tr))
        pids = [tr[i]["player_id"] for i in i_tr]
        if t == "rating":       # add the partly observed 2023-24 AAA classes, weighted by the share known
            extra = [r for r in rows if r["season"] in (2023, 2024) and r["sport_id"] == statsapi.AAA
                     and (r["player_id"], r["season"]) in scores_now
                     and all(r["f"].get(k) is not None for k in keys[t])]
            if extra:
                sc_tr = np.concatenate([sc_tr, [scores_now[(r["player_id"], r["season"])] for r in extra]])
                b_tr = np.concatenate([b_tr, evaluate.predict(m_t, extra, keys[t])])
                yv = np.concatenate([yv, [asof.rating_target(r["mlb"], r["season"], bar_now, "P") for r in extra]])
                wt = np.concatenate([wt, [(PRODUCTION - r["season"]) / asof.RATING_YEARS for r in extra]])
                pids += [r["player_id"] for r in extra]
        resid_tr, (a, b) = TL.residualize(sc_tr, b_tr)
        w, lo, hi = TL.trust_weight(t, yv, b_tr, resid_tr, wt, pids)
        use = bool((lo > 0 or hi < 0) and (t == "rating" or frozen["use_soon_stuff"]))
        L.append(f"  {t}: {kind} on {len(tr)} rows, keys {keys[t]}; stuff w {w:+.3f} [{lo:+.3f}, {hi:+.3f}] from "
                 f"{len(yv)} AAA pitcher-seasons -> "
                 + (("applied" + (" (PROVISIONAL: no later complete class to check it)" if t == "rating" else ""))
                    if use else "not applied"))
        fin = np.array(pred, dtype=float)
        i_te, sc_te = scored(te, scores_now)
        if use and i_te:
            fin[i_te] = TL.adjust(t, fin[i_te], sc_te - (a + b * fin[i_te]), w)
        out[t] = {"test": te, "pred": fin, "tracked": set(i_te) if use else set()}
        decisions[t] = {"kind": kind, "keys": keys[t], "stuff_w": float(w), "stuff_ci": [float(lo), float(hi)],
                        "stuff_used": use}

    by = {}
    for t in ("rating", "soon"):
        for i, (r, p) in enumerate(zip(out[t]["test"], out[t]["pred"])):
            e = by.setdefault((r["player_id"], r["sport_id"]), {"r": r})
            e[t], e[t + "_tracked"] = float(p), i in out[t]["tracked"]
    best = {}
    for (pid, sid), e in by.items():            # one row per pitcher: the highest level (lowest sportId)
        if "rating" in e and "soon" in e and (pid not in best or sid < best[pid]["r"]["sport_id"]):
            best[pid] = e
    ranked = sorted(best.values(), key=lambda e: e["rating"])
    for i, e in enumerate(ranked):
        e["pct"] = 100.0 * (i + 1) / len(ranked)
    with open(RATINGS, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["player_id", "name", "level", "age", "start_share", "rating_sgp", "rating_percentile",
                     "p_useful_within_2", "stuff_in_rating", "stuff_in_soon", "flags"])
        for e in sorted(ranked, key=lambda e: -e["rating"]):
            r = e["r"]
            flags = (["rating stuff provisional"] if e["rating_tracked"] else []) + \
                    ([] if frozen["percent_ok"] else ["soon odds: rank only"])
            ss = r.get("start_share")
            wr.writerow([r["player_id"], safe(r["name"]), cohorts.LEVEL_NAMES[r["sport_id"]], r["age_raw"],
                         "" if ss is None else f"{ss:.3f}", f"{e['rating']:.3f}", f"{e['pct']:.1f}",
                         f"{e['soon']:.3f}", "yes" if e["rating_tracked"] else "no",
                         "yes" if e["soon_tracked"] else "no", "; ".join(flags)])
    top = sorted(ranked, key=lambda e: -e["rating"])
    shares = [e["r"]["start_share"] for e in top[:50] if e["r"].get("start_share") is not None]
    L.append(f"  wrote {len(ranked)} pitchers -> {RATINGS}")
    L.append("  sanity, top 15 by rating: " + "; ".join(
        f"{e['r']['name']} ({cohorts.LEVEL_NAMES[e['r']['sport_id']]}, {e['r']['age_raw']}, "
        f"GS {e['r'].get('start_share') or 0:.0%}) {e['rating']:.2f}/{e['soon']:.1%}" for e in top[:15]))
    L.append(f"  sanity, top 50: median start share {statistics.median(shares):.2f}, "
             f"{sum(1 for s in shares if s < 0.5)} mostly relievers (start share < 0.5)")

    with open(DECISIONS, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)
    finish(L)


if __name__ == "__main__":
    main()
