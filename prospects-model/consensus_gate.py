"""3c-hitters plan C: the consensus gate -- does the model beat just following FV?

For each test class Y, the prospects that Board list Y+1 grades are ranked three
ways -- FanGraphs' order, the model (fit as-of Y), and the average of the two
percentile ranks -- and scored on the same targets and adoption rule as the
backtests. The verdict rules were fixed in the spec before this ran.

Groups per class: graded (decides); graduates restored from list Y (the guard);
sleepers, i.e. ungraded players (is the model better than chance there?).

Usage:  python consensus_gate.py
Reads cached data and the user's Board exports (cache/fv/). No network. Writes
cache/consensus_report.txt, cache/consensus_verdict.json and
cache/consensus_ambiguous.csv (all gitignored).
"""
import csv
import datetime
import json
import os
import warnings

import numpy as np

from psmodel import asof, cohorts, dataset
from psmodel import consensus as C
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
REPORT = os.path.join(CACHE, "consensus_report.txt")
VERDICT = os.path.join(CACHE, "consensus_verdict.json")
AMBIGUOUS = os.path.join(CACHE, "consensus_ambiguous.csv")
TESTS = {"rating": W.RATING_VANTAGES, "soon": W.SOON_VANTAGES}
INFO = {"rating": (), "soon": (2024,)}      # opened in plan B: reported, never decides
FIRST_LIST, LAST_LIST = 2017, 2026
GRADUATE_PA = 100               # MLB PA in Y+1 marking a player missing from list Y+1 as a graduate
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def safe(text):
    """CSV-injection guard for free-text columns."""
    s = "" if text is None else str(text)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def one_per_player(test, pred):
    """Each player's row at the highest level of that season (lowest sportId)."""
    best = {}
    for r, p in zip(test, pred):
        if r["player_id"] not in best or r["sport_id"] < best[r["player_id"]][0]["sport_id"]:
            best[r["player_id"]] = (r, float(p))
    return [b[0] for b in best.values()], np.array([b[1] for b in best.values()])


def people(test):
    return [{"player_id": r["player_id"], "name": r["name"],
             "age": None if r["age_raw"] is None else float(r["age_raw"])} for r in test]


def fmt(m):
    return f"{m['rank']:.3f} t25 {m['top25']:.2f} t50 {m['top50']:.2f}"


def line(label, res):
    if res is None:
        return f"    {label}: n/a"
    return (f"    {label}: FV {fmt(res['base'])} | challenger {fmt(res['fam'])} | "
            f"gain {res['d']:+.4f} (z {W.z_score(res['d'], res['se']):+.1f})")


def summary(res):
    if res is None:
        return None
    return {"fv": res["base"], "challenger": res["fam"], "gain": res["d"], "se": res["se"],
            "z": W.z_score(res["d"], res["se"])}


def main():
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels)
    pa_history = cohorts.mlb_pa_history()
    rows = cohorts.build_rows(cohorts.load_milb(), pa_history,
                              {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    cohorts.add_products(rows)
    with open(os.path.join(CACHE, "model3c_final.json"), encoding="utf-8") as fh:
        dec = json.load(fh)
    boards = {y: C.load_board(C.board_path(FV_DIR, y)) for y in range(FIRST_LIST, LAST_LIST + 1)
              if os.path.exists(C.board_path(FV_DIR, y))}
    missing = sorted({v + 1 for t in TESTS for v in TESTS[t] + INFO[t]} - set(boards))
    if missing:
        raise SystemExit(f"Board lists missing from {FV_DIR}: {missing}")

    memo = {}

    def scored(t, c, ctx_y):
        """(one row per player, y on ctx_y; model score) for class c, the model fit as-of c."""
        if (t, c) not in memo:
            got = W.predictions(rows, dec[t]["keys"], t, dec[t]["kind"], {c: asof.ref_curve(labels, c)}, (c,),
                                unseal=c in INFO[t])
            memo[(t, c)] = one_per_player(*got[c]) if c in got else ([], np.array([]))
        test, pred = memo[(t, c)]
        return [dict(r, y=W._y(r, t, ctx_y)) for r in test], pred

    def groups(t, c, ctx_y):
        test, pred = scored(t, c, ctx_y)
        nxt = C.match(people(test), boards[c + 1])
        prev = C.match(people(test), boards[c]) if c in boards else None
        skip = nxt["age_rejected"] | {a["player_id"] for a in nxt["ambiguous"]}
        graded, restored, sleepers = [], [], []
        for r, p in zip(test, pred):
            pid = r["player_id"]
            if pid in nxt["matched"]:
                graded.append((r, p, C.fv_score(nxt["matched"][pid])))
            elif pid in skip:
                continue
            elif prev and pid in prev["matched"] and pa_history.get(pid, {}).get(c + 1, 0) >= GRADUATE_PA:
                restored.append((r, p, C.fv_score(prev["matched"][pid])))
            else:
                sleepers.append((r, p))
        return nxt, graded, restored, sleepers

    def challenge(group, t, ctx):
        """(model vs FV, simple blend vs FV) on one group of graded players."""
        if not group:
            return None, None
        test = [g[0] for g in group]
        pm, pf = C.pct([g[1] for g in group]), C.pct([g[2] for g in group])
        return C.head_to_head(test, pf, pm, t, ctx), C.head_to_head(test, pf, (pm + pf) / 2, t, ctx)

    def fitted(t, v, ctx, group):
        """Information only: a blend fit on earlier classes that have a list, each
        scored by its own as-of model."""
        known = asof.rating_known if t == "rating" else asof.soon_known
        pm_all, pf_all, ys = [], [], []
        for c in range(FIRST_LIST - 1, v):
            if c not in cohorts.MILB_SEASONS or c + 1 not in boards or not known(c, v):
                continue
            _, g, _, _ = groups(t, c, ctx)
            if g:
                pm_all += list(C.pct([x[1] for x in g]))
                pf_all += list(C.pct([x[2] for x in g]))
                ys += [x[0]["y"] for x in g]
        if not group or len(ys) < C.MIN_H2H or (t == "soon" and len(set(ys)) < 2):
            return None
        m = C.fit_blend(np.array(pm_all), np.array(pf_all), np.array(ys), t)
        test = [g[0] for g in group]
        pm, pf = C.pct([g[1] for g in group]), C.pct([g[2] for g in group])
        return C.head_to_head(test, pf, C.apply_blend(m, pm, pf, t), t, ctx)

    L = ["3c-HITTERS CONSENSUS GATE (plan C): does the model beat just following FV?",
         "Class Y vs Board list Y+1 (preseason; built from information through Y). Base model, fit as-of Y.",
         "Each line: FanGraphs' order vs the challenger on the same players; z = gain in noise-widths.", ""]
    out, ambiguous = {"generated": datetime.date.today().isoformat()}, {}
    for t in ("rating", "soon"):
        L.append(f"{t.upper()} ({dec[t]['kind']}; features: {', '.join(dec[t]['keys'])})")
        res = {k: {} for k in ("model", "blend", "model_r", "blend_r")}
        cis, classes = {}, {}
        for v in TESTS[t] + INFO[t]:
            ctx = asof.ref_curve(labels, v)
            nxt, graded, restored, sleepers = groups(t, v, ctx)
            for a in nxt["ambiguous"]:
                ambiguous[(v + 1, a["player_id"])] = a
            mo, bl = challenge(graded, t, ctx)
            mo_r, bl_r = challenge(graded + restored, t, ctx)
            ci = C.rank_ci([s[0] for s in sleepers], [s[1] for s in sleepers], t) if sleepers else None
            fit = fitted(t, v, ctx, graded)
            info = v in INFO[t]
            if not info:
                res["model"][v], res["blend"][v], res["model_r"][v], res["blend_r"][v] = mo, bl, mo_r, bl_r
                cis[v] = ci
            L.append(f"  class {v} vs list {v + 1}{'  (INFORMATION ONLY: opened in plan B)' if info else ''}: "
                     f"graded {len(graded)}, ungraded {len(sleepers)}, graduates restored {len(restored)}, "
                     f"ambiguous {len(nxt['ambiguous'])}, age-rejected {len(nxt['age_rejected'])}, "
                     f"age offset {nxt['offset']:+.2f}")
            L += [line("model", mo), line("blend (average of percentiles)", bl),
                  line("model, graduates restored", mo_r), line("blend, graduates restored", bl_r),
                  line("fitted blend (information only)", fit),
                  "    sleepers: n/a" if ci is None else
                  f"    sleepers: model rank accuracy {ci[0]:.3f} [{ci[1]:.3f}, {ci[2]:.3f}] "
                  f"(chance {C.CHANCE[t]:.1f}, n={len(sleepers)})"]
            classes[str(v)] = {"list": v + 1, "information_only": info, "n_graded": len(graded),
                               "n_ungraded": len(sleepers), "n_restored": len(restored),
                               "n_ambiguous": len(nxt["ambiguous"]), "n_age_rejected": len(nxt["age_rejected"]),
                               "age_offset": nxt["offset"], "model": summary(mo), "blend": summary(bl),
                               "model_restored": summary(mo_r), "blend_restored": summary(bl_r),
                               "fitted_blend": summary(fit), "sleepers": ci}
        main_v = C.verdict(res["model"], res["blend"])
        rest_v = C.verdict(res["model_r"], res["blend_r"])
        final, show = C.cautious(main_v, rest_v), C.sleepers_ok(cis, t)
        _, mw, ma = W.adopt(res["model"])
        _, bw, ba = W.adopt(res["blend"])
        L += [f"  model beat FV (>= 1 SE) in {mw}/{ma} classes; blend beat FV in {bw}/{ba}",
              f"  VERDICT ({t}): {final.upper()}"
              + (f"  [UNSTABLE: graded-only says '{main_v}', graduates-restored says '{rest_v}'; "
                 f"the more cautious stands]" if main_v != rest_v else ""),
              f"  model shown for ungraded hitters: {'yes' if show else 'no'}", ""]
        out[t] = {"verdict": final, "verdict_graded": main_v, "verdict_restored": rest_v,
                  "unstable": main_v != rest_v, "show_model_for_ungraded": show, "classes": classes}

    with open(AMBIGUOUS, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["list", "player_id", "name", "age", "board_candidates"])
        for (lst, pid), a in sorted(ambiguous.items()):
            wr.writerow([lst, pid, safe(a["name"]), a["age"], safe("; ".join(a["candidates"]))])
    L.append(f"{len(ambiguous)} ambiguous same-name cases left out -> {AMBIGUOUS}")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
