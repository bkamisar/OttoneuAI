"""FV+ Phase 2 (spec 2026-09-30-fv-plus-design.md, Amendment A): does FanGraphs'
FV plus pre-registered 4x4 adjustments beat FV alone?

Phases, each checkpointed to cache/fvplus_<phase>.json (skipped on relaunch;
--force redoes all): omnibus, guard, shuffle, components, weights, statcast, map.
Then the report (cache/fvplus_report.txt) and verdict (cache/fvplus_verdict.json).

Usage:  python fvplus_run.py [--force]
Reads cached data, the Board exports (cache/fv/) and the cached MLB standings
(run fetch_standings.py first). No network.
"""
import argparse
import datetime
import json
import os
import warnings

import numpy as np

import consensus_gate as CG
from psmodel import asof, cohorts, context, dataset, milb, mlbteams, pcohorts, spray, statsapi, step1
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import stuff
from psmodel import stuff_layer as SL
from psmodel import tracking
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "fvplus_report.txt")
VERDICT = os.path.join(CACHE, "fvplus_verdict.json")
NOW = cohorts.CURRENT_SEASON
MODELS = [("H", "rating"), ("H", "soon"), ("P", "rating"), ("P", "soon")]
EXPECTED_TESTS = {("H", "rating"): [2021, 2022], ("P", "rating"): [2021, 2022],
                  ("H", "soon"): [2021, 2022, 2023, 2024], ("P", "soon"): [2021, 2022, 2023, 2024]}
FIRST_TEST = 2018                                   # classes 2016-17 (lists 2017-18) are thin: training only
STATCAST_CLASSES = {"rating": (2022,), "soon": (2022, 2023, 2024)}
SEED = 0
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


def mkey(m):
    return f"{m[0]}_{m[1]}"


class Data:
    """Everything the phases need, built once on first use."""

    def __init__(self):
        self.labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
        self.rows, self.history, self.dec, self.boards = {}, {}, {}, {}
        for typ in ("H", "P"):
            asof.attach_ranks(self.labels, typ)
        for typ, noun in (("H", "hitters"), ("P", "pitchers")):
            mlb = {pid: r for (pid, t), r in self.labels.items() if t == typ}
            if typ == "H":
                self.history[typ] = cohorts.mlb_pa_history()
                self.rows[typ] = cohorts.add_products(cohorts.build_rows(cohorts.load_milb(), self.history[typ], mlb))
            else:
                self.history[typ] = pcohorts.mlb_ip_history()
                raw = pcohorts.load_milb()
                self.gb = F.gb_z(raw)
                self.rows[typ] = pcohorts.add_products(pcohorts.build_rows(raw, self.history[typ], mlb))
            with open(os.path.join(CACHE, CG.TYPES[typ]["decisions"]), encoding="utf-8") as fh:
                self.dec[typ] = json.load(fh)
            self.boards[typ] = {y: C.load_board(C.board_path(FV_DIR, y, noun)) for y in range(2017, NOW + 1)
                                if os.path.exists(C.board_path(FV_DIR, y, noun))}
        self.class_seasons = [c for c in range(2016, NOW) if c in cohorts.MILB_SEASONS and c + 1 in self.boards["H"]]
        self.win = {c: mlbteams.win_pct(c) for c in self.class_seasons}
        self.ctx = {(typ, v): asof.ref_curve(self.labels, v, typ) for typ in ("H", "P")
                    for v in self.class_seasons + [NOW]}
        self.classes, self.classes_r, self.counts = {}, {}, {}
        for typ in ("H", "P"):
            for t in ("rating", "soon"):
                g, r = {}, {}
                for c in self.class_seasons:
                    g[c], r[c], self.counts[(typ, t, c)] = self._class(typ, t, c)
                self.classes[(typ, t)], self.classes_r[(typ, t)] = g, r

    def _sm(self, typ, t, c):
        dec = self.dec[typ][t]
        got = W.predictions(self.rows[typ], dec["keys"], t, dec["kind"], {c: self.ctx[(typ, c)]}, (c,),
                            unseal=c in W.SEALED)
        if c not in got:
            return {}
        test, pred = CG.one_per_player(*got[c])
        return {r["player_id"]: float(p) for r, p in zip(test, pred)}

    def _class(self, typ, t, c):
        """(graded players, graded + restored graduates, counts) for class c, one row per player."""
        best = {}
        for r in self.rows[typ]:
            if r["season"] == c and (r["player_id"] not in best or r["sport_id"] < best[r["player_id"]]["sport_id"]):
                best[r["player_id"]] = r
        test = list(best.values())
        boards = self.boards[typ]
        nxt = C.match(CG.people(test), boards[c + 1])
        prev = C.match(CG.people(test), boards[c]) if c in boards else None
        skip = nxt["age_rejected"] | {a["player_id"] for a in nxt["ambiguous"]}
        med_n = F.medians(boards[c + 1], typ)
        med_p = F.medians(boards[c], typ) if c in boards else None
        sm = self._sm(typ, t, c)
        graded, restored, missing = [], [], {}
        for r in test:
            pid = r["player_id"]
            if pid in nxt["matched"]:
                e, med, out = nxt["matched"][pid], med_n, graded
            elif pid in skip:
                continue
            elif prev and pid in prev["matched"] and \
                    self.history[typ].get(pid, {}).get(c + 1, 0) >= CG.TYPES[typ]["graduate"]:
                e, med, out = prev["matched"][pid], med_p, restored
            else:
                continue
            for k in F.GRADE_KEYS[typ]:
                missing[k] = missing.get(k, 0) + (e.get(k) is None)
            gb = self.gb.get((pid, c, r["sport_id"])) if typ == "P" else None
            x = F.features(typ, e, r, med, self.win[c].get(mlbteams.team_of(e["org"])[0]), gb)
            out.append({"player_id": pid, "name": r["name"], "typ": typ, "cls": c, "fv_grade": e["fv"],
                        "x": x, "row": r, "sm_raw": sm.get(pid)})
        guard = [dict(p, x=dict(p["x"])) for p in graded + restored]    # copies: sm percentile differs
        for group in (graded, guard):
            scored = [p for p in group if p["sm_raw"] is not None]
            pct = C.pct([p["sm_raw"] for p in scored]) if scored else []
            for p, q in zip(scored, pct):
                p["x"]["sm"] = float(q)
        counts = {"graded": len(graded), "restored": len(restored), "missing_grades": missing}
        return graded, guard, counts

    def ctxs(self, typ):
        return {v: self.ctx[(typ, v)] for v in self.class_seasons}


def test_classes(d, m):
    """Test classes by the pre-registered rule; stops if they differ from Amendment A's list."""
    typ, t = m
    known = asof.rating_known if t == "rating" else asof.soon_known
    out = []
    for v in d.class_seasons:
        if v < FIRST_TEST or not known(v, NOW):
            continue
        train, _ = F.split(d.classes[m], v, t, d.ctx[(typ, v)])
        if F.trainable(train, t):
            out.append(v)
    if out != EXPECTED_TESTS[m]:
        raise SystemExit(f"{m}: the rule gives test classes {out}, Amendment A says {EXPECTED_TESTS[m]} -- stop")
    return out


def summary(res):
    if res is None:
        return None
    return {"fv": res["base"], "fvplus": res["fam"], "d": res["d"], "se": res["se"],
            "z": W.z_score(res["d"], res["se"])}


def phase_omnibus(d, classes_attr="classes"):
    out = {}
    for m in MODELS:
        typ, t = m
        res, _ = F.walk(getattr(d, classes_attr)[m], test_classes(d, m), t, F.keys(typ, t), d.ctxs(typ))
        dsum, z, n = F.pooled(res)
        out[mkey(m)] = {"classes": {str(v): summary(r) for v, r in res.items()}, "d": dsum, "z": z, "n": n,
                        "p": F.p_two_sided(z), "conditions": F.conditions(res, t)}
    return out


def phase_shuffle(d):
    out = {}
    for m in MODELS:
        typ, t = m
        cols, tests, rng = F.keys(typ, t), test_classes(d, m), np.random.default_rng(SEED)
        null = []
        for i in range(F.N_SHUFFLE):
            res, _ = F.walk(F.shuffled(d.classes[m], cols, rng), tests, t, cols, d.ctxs(typ))
            null.append(F.pooled(res)[0])
            if (i + 1) % 50 == 0:
                print(f"  shuffle {mkey(m)} {i + 1}/{F.N_SHUFFLE}", flush=True)
        out[mkey(m)] = null
    return out


def phase_components(d):
    out = {}
    for m in MODELS:
        typ, t = m
        tests = test_classes(d, m)
        _, full = F.walk(d.classes[m], tests, t, F.keys(typ, t), d.ctxs(typ))
        out[mkey(m)] = {}
        for g in F.GROUPS[m]:
            _, dropped = F.walk(d.classes[m], tests, t, F.keys(typ, t, drop=g), d.ctxs(typ))
            res = {v: C.head_to_head(full[v][0], dropped[v][1], full[v][1], t, d.ctx[(typ, v)])
                   for v in full if v in dropped}
            dsum, z, n = F.pooled(res)
            out[mkey(m)][g] = {"d": dsum, "z": z, "n": n}
    return out


def phase_weights(d):
    out = {}
    for m in MODELS:
        typ, t = m
        known = asof.rating_known if t == "rating" else asof.soon_known
        ctx = d.ctx[(typ, NOW)]
        train = [dict(p, y=W._y(p["row"], t, ctx)) for c, ps in d.classes[m].items() if known(c, NOW) for p in ps]
        out[mkey(m)] = F.weights(train, ["fv"] + F.keys(typ, t), t)
        print(f"  weights {mkey(m)} done", flush=True)
    return out


def _stuff_scores():
    with open(os.path.join(CACHE, "stuff_choice.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    s_keys, s_kind = sc["score_keys"], sc["kind"]
    sv_mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    sv_aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB)
                 for s in range(2015, stuff.LAST_OUTCOME_SEASON + 1)}
    mlb_stats = {(r["player_id"], s): r for s, rs in by_season.items() for r in rs}
    values = stuff.season_values(by_season, den)
    aaa_stats = {(r["player_id"], s): r for s in (2022, 2023, 2024)
                 for r in milb.season_rows(s, statsapi.AAA, "pitching")}
    out = {}
    for c in (2022, 2023, 2024):
        model = SL.stuff_model(c, sv_mlb, values, mlb_stats, s_keys, s_kind)
        off = SL.offsets(c, sv_aaa, sv_mlb, [k for k in s_keys if k != "age"])
        out.update(SL.aaa_scores(sv_aaa, aaa_stats, model, off, s_keys, {c}))
    return out


def phase_statcast(d):
    """Per-player measures and the provisional partial-Spearman tests (no fitting)."""
    aaa = step1.load_table(os.path.join(CACHE, "aaa_tracking.csv"))
    measures = {"pull_air": {}, "ev_low_air": {}, "ev": {}, "stuff": {}}
    for c in (2022, 2023, 2024):
        for pid, (rate, n) in spray.pulled_air(tracking.season_events(c, statsapi.AAA)).items():
            if n >= 100:
                measures["pull_air"][f"{pid}|{c}"] = rate
        pool = [(pid, r) for (pid, s), r in aaa.items() if s == c and (r.get("bbe") or 0) >= 100
                and r.get("avg_best_speed") is not None and r.get("linedrives_percent") is not None
                and r.get("flyballs_percent") is not None]
        ev = np.array([r["avg_best_speed"] for _, r in pool])
        air = np.array([r["linedrives_percent"] + r["flyballs_percent"] for _, r in pool])
        ev_hi, air_lo = np.percentile(ev, 200 / 3), np.percentile(air, 100 / 3)
        for (pid, r), e, a in zip(pool, ev, air):
            measures["ev_low_air"][f"{pid}|{c}"] = float(e >= ev_hi and a <= air_lo)
            measures["ev"][f"{pid}|{c}"] = float(e)
        print(f"  statcast measures {c} done", flush=True)
    measures["stuff"] = {f"{pid}|{s}": float(v) for (pid, s), v in _stuff_scores().items()}
    tests = {}
    for name, typ, meas in (("S-PA", "H", "pull_air"), ("S-EV", "H", "ev_low_air"), ("S-ST", "P", "stuff")):
        for t in ("rating", "soon"):
            per = {}
            for c in STATCAST_CLASSES[t]:
                ctx = d.ctx[(typ, c)]
                ps = [p for p in d.classes[(typ, t)][c]
                      if p["row"]["sport_id"] == statsapi.AAA and f"{p['player_id']}|{c}" in measures[meas]]
                if len(ps) < C.MIN_H2H:
                    per[str(c)] = None
                    continue
                y = [W._y(p["row"], t, ctx) for p in ps]
                if t == "soon" and len(set(y)) < 2:
                    per[str(c)] = None
                    continue
                x = [measures[meas][f"{p['player_id']}|{c}"] for p in ps]
                rho, se = F.partial_ci(x, y, [p["x"]["fv"] for p in ps])
                per[str(c)] = {"rho": rho, "se": se, "n": len(ps)}
            got = [v for v in per.values() if v is not None]
            s = float(sum(v["rho"] for v in got))
            se = float(np.sqrt(sum(v["se"] ** 2 for v in got)))
            z = s / se if se > 0 else 0.0
            tests[f"{name}_{t}"] = {"classes": per, "z": z, "p": F.p_two_sided(z), "n_classes": len(got)}
    return {"measures": measures, "tests": tests}


def _median_by_class(values):
    by = {}
    for k, v in values.items():
        by.setdefault(int(k.split("|")[1]), []).append(v)
    return {c: float(np.median(v)) for c, v in by.items()}


def phase_map(d, statcast):
    meas = statcast["measures"]
    pa_med, ev_med, st_med = (_median_by_class(meas[k]) for k in ("pull_air", "ev", "stuff"))
    out = {}
    for m in MODELS:
        typ, t = m
        known = asof.rating_known if t == "rating" else asof.soon_known
        ps = [dict(p, y=W._y(p["row"], t, d.ctx[(typ, c)])) for c, group in d.classes[m].items()
              if known(c, NOW) for p in group]
        res = F.residuals(ps)
        cells = {}

        def add(name, test):
            cells[name] = F.cell([r for p, r in zip(ps, res) if test(p)])

        if typ == "H":
            for k, get in (("hit", lambda x: x["hit"]), ("game_pwr", lambda x: x["gpwr"]),
                           ("raw_pwr", lambda x: x["raw_gap"] + x["gpwr"]), ("spd", lambda x: x["spd"])):
                for b in ("<=40", "45-50", ">50"):
                    add(f"{k} {b}", lambda p, get=get, b=b: F.gbin(get(p["x"])) == b)
            add("premium position", lambda p: p["x"]["prem"] == 1.0)
            add("other position", lambda p: p["x"]["prem"] == 0.0)
            for pa_hi in (True, False):
                for ev_hi in (True, False):
                    def test(p, pa_hi=pa_hi, ev_hi=ev_hi):
                        k = f"{p['player_id']}|{p['cls']}"
                        if k not in meas["pull_air"] or k not in meas["ev"]:
                            return False
                        return ((meas["pull_air"][k] >= pa_med[p["cls"]]) == pa_hi
                                and (meas["ev"][k] >= ev_med[p["cls"]]) == ev_hi)
                    add(f"pulled air {'high' if pa_hi else 'low'} x EV {'high' if ev_hi else 'low'}", test)
        else:
            for k in ("fb", "brk", "ch", "cmd"):
                for b in ("<=40", "45-50", ">50"):
                    add(f"{k} {b}", lambda p, k=k, b=b: F.gbin(p["x"][k]) == b)
            names = ("fb", "brk", "ch", "cmd")
            for i, a in enumerate(names):
                for b_ in names[i + 1:]:
                    for ha in (True, False):
                        for hb in (True, False):
                            add(f"{a} {'high' if ha else 'low'} x {b_} {'high' if hb else 'low'}",
                                lambda p, a=a, b_=b_, ha=ha, hb=hb:
                                (p["x"][a] >= 55 if ha else p["x"][a] <= 45)
                                and (p["x"][b_] >= 55 if hb else p["x"][b_] <= 45))
            add("profile: power arm", lambda p: p["x"]["fb"] >= 60 and p["x"]["cmd"] <= 40)
            add("profile: command artist", lambda p: p["x"]["cmd"] >= 55 and p["x"]["fb"] <= 50)
            add("profile: breaker-first", lambda p: p["x"]["brk"] >= 60 and p["x"]["fb"] <= 50)
            for st_hi in (True, False):
                for sec_hi in (True, False):
                    def test(p, st_hi=st_hi, sec_hi=sec_hi):
                        k = f"{p['player_id']}|{p['cls']}"
                        if k not in meas["stuff"]:
                            return False
                        sec = (p["x"]["cmd"] + max(p["x"]["brk"], p["x"]["ch"])) / 2
                        return (meas["stuff"][k] >= st_med[p["cls"]]) == st_hi and (sec >= 50) == sec_hi
                    add(f"stuff {'high' if st_hi else 'low'} x cmd+secondary {'high' if sec_hi else 'low'}", test)
        out[mkey(m)] = cells
    return out


def checkpoint(name, force, fn):
    path = os.path.join(CACHE, f"fvplus_{name}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    print(f"phase {name} ...", flush=True)
    out = fn()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    os.replace(tmp, path)
    return out


def fmt_res(r):
    if r is None:
        return "n/a"
    return (f"FV {r['fv']['rank']:.3f} t50 {r['fv']['top50']:.2f} | FV+ {r['fvplus']['rank']:.3f} "
            f"t50 {r['fvplus']['top50']:.2f} | gain {r['d']:+.4f} (z {r['z']:+.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every phase")
    force = ap.parse_args().force
    cache = {}

    def data():
        if "d" not in cache:
            print("building data ...", flush=True)
            cache["d"] = Data()
            with open(os.path.join(CACHE, "fvplus_counts.json"), "w", encoding="utf-8") as fh:
                json.dump({f"{k[0]}_{k[1]}_{k[2]}": v for k, v in cache["d"].counts.items()}, fh)
        return cache["d"]

    omni = checkpoint("omnibus", force, lambda: phase_omnibus(data()))
    guard = checkpoint("guard", force, lambda: phase_omnibus(data(), "classes_r"))
    null = checkpoint("shuffle", force, lambda: phase_shuffle(data()))
    comps = checkpoint("components", force, lambda: phase_components(data()))
    wts = checkpoint("weights", force, lambda: phase_weights(data()))
    stat = checkpoint("statcast", force, lambda: phase_statcast(data()))
    fmap = checkpoint("map", force, lambda: phase_map(data(), stat))
    with open(os.path.join(CACHE, "fvplus_counts.json"), encoding="utf-8") as fh:
        counts = json.load(fh)

    holm = F.holm_adjust({k: v["p"] for k, v in omni.items()})
    holm_g = F.holm_adjust({k: v["p"] for k, v in guard.items()})
    L = ["FV+ PHASE 2 -- does FV plus the pre-registered 4x4 adjustments beat FV alone?",
         "Spec 2026-09-30-fv-plus-design.md, Amendment A. Strict as-of walk-forward; gain = FV+ minus FV "
         "(Spearman for rating, AUC for soon) on the same graded players.", ""]
    L.append("0. Classes (graded / graduates restored; blank grades imputed):")
    for k, v in sorted(counts.items()):
        L.append(f"  {k}: graded {v['graded']}, restored {v['restored']}, blank grades {v['missing_grades']}")
    L.append("")
    verdict = {"generated": datetime.date.today().isoformat(), "models": {}}
    L.append("1. DECISION TESTS (one Holm family of 4)")
    for m in MODELS:
        k = mkey(m)
        o, g, c = omni[k], guard[k], omni[k]["conditions"]
        real, p95 = o["d"], float(np.percentile(null[k], F.SHUFFLE_PCT))
        gc = g["conditions"]
        main_ok = holm[k] < F.HOLM_ALPHA and c["majority"] and not c["harmed"] and c["top50_ok"] and real > p95
        guard_ok = holm_g[k] < F.HOLM_ALPHA and gc["majority"] and not gc["harmed"] and gc["top50_ok"]
        adopted = main_ok and guard_ok
        L.append(f"  {k}: adjustments {F.keys(*m)}")
        for v, r in o["classes"].items():
            L.append(f"    class {v} (list {int(v) + 1}): {fmt_res(r)}")
        L += [f"    pooled gain {o['d']:+.4f}, z {o['z']:+.2f}, p {o['p']:.4f}, Holm-adjusted p {holm[k]:.4f}",
              f"    majority {c['positive']}/{c['classes']} ({'ok' if c['majority'] else 'NO'}), "
              f"harm {'YES' if c['harmed'] else 'none'}, mean top-50 change {c['top50']:+.3f} "
              f"({'ok' if c['top50_ok'] else 'NO'}), shuffle 95th pct {p95:+.4f} vs real {real:+.4f} "
              f"({'ok' if real > p95 else 'NO'})",
              f"    guard (graduates restored): pooled gain {g['d']:+.4f}, z {g['z']:+.2f}, Holm p {holm_g[k]:.4f}, "
              f"majority {gc['positive']}/{gc['classes']}, harm {'YES' if gc['harmed'] else 'none'} "
              f"-> {'passes' if guard_ok else 'fails'}",
              f"    VERDICT {k}: {'ADOPT FV+' if adopted else 'FV stands'}", ""]
        verdict["models"][k] = {"adopted": adopted, "main_ok": main_ok, "guard_ok": guard_ok, "d": o["d"],
                                "z": o["z"], "holm_p": holm[k], "shuffle_p95": p95}
    L.append("2. COMPONENTS (explanation, not decision): pooled gain lost when the group is dropped")
    for m in MODELS:
        L.append(f"  {mkey(m)}: " + "; ".join(f"{g} {v['d']:+.4f} (z {v['z']:+.1f})"
                                               for g, v in comps[mkey(m)].items()))
    L += ["", "3. WEIGHTS (production fit on every answered class; standardized; 95% player bootstrap)"]
    for m in MODELS:
        L.append(f"  {mkey(m)}:")
        for col, (w, lo, hi) in wts[mkey(m)].items():
            exp = F.EXPECTED[m].get(col, "base")
            sig = "+" if lo > 0 else "-" if hi < 0 else "0"
            flag = "   SURPRISE (opposite to expected)" if exp in ("+", "-") and sig in ("+", "-") and sig != exp else ""
            L.append(f"    {col:9} {w:+.3f} [{lo:+.3f}, {hi:+.3f}]  expected {exp}{flag}")
    L += ["", "4. STATCAST GROUP -- PROVISIONAL (partial Spearman with the target, FV held fixed; decided after 2028)"]
    sh = F.holm_adjust({k: v["p"] for k, v in stat["tests"].items()})
    for k, v in stat["tests"].items():
        per = "; ".join(f"{c}: n/a" if r is None else f"{c}: {r['rho']:+.3f} (se {r['se']:.3f}, n {r['n']})"
                        for c, r in v["classes"].items())
        L.append(f"  {k}: {per} -> pooled z {v['z']:+.2f}, Holm p {sh[k]:.3f}")
    L += ["", "5. EXPLORATION MAP (descriptive; residual = outcome minus class-and-FV-bucket mean)"]
    queue = []
    for m in MODELS:
        L.append(f"  {mkey(m)}:")
        for name, cl in fmap[mkey(m)].items():
            if cl is None:
                L.append(f"    {name}: empty")
                continue
            q = F.queued(cl)
            L.append(f"    {name}: {cl[0]:+.3f} [{cl[1]:+.3f}, {cl[2]:+.3f}] n={cl[3]}" + ("   -> QUEUE" if q else ""))
            if q:
                queue.append(f"{mkey(m)}: {name} ({cl[0]:+.3f}, n={cl[3]})")
    L += ["", "6. CONFIRMATION QUEUE (pre-register for the 2025+ classes; nothing adopted now):"] + \
         [f"  - {q}" for q in queue or ["(empty)"]]
    verdict["queue"] = queue
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2)


if __name__ == "__main__":
    main()
