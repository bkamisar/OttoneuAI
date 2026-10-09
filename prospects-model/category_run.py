"""Roto category scores (spec 2026-10-09-category-score-design.md).

Phases, checkpointed to cache/category_<phase>.json (skipped on relaunch;
--force redoes all):
  rates  -- Part 2: as-of rate models per category; trust at vantages 2019/2021/2022
  race   -- Part 1: FV alone vs FV + stats for 4-year playing time (graded classes 2021/2022)
  ladder -- walk-up ladders per category (graded 2021+2022; ungraded 2019+2021+2022)
  scores -- production for 2026 players -> cache/category_scores.csv
Report: cache/category_report.txt; verdict: cache/category_verdict.json. No network.

Usage:  python category_run.py [--force]
"""
import argparse
import csv
import datetime
import json
import os
import warnings

import numpy as np
from scipy.stats import spearmanr

import consensus_gate as CG
import fvplus_run as R
from psmodel import asof, cohorts, context, pcohorts
from psmodel import categories as K
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import shopping as S
from psmodel import walkforward as W

CACHE, NOW = R.CACHE, R.NOW
BOARD = os.path.join(os.path.dirname(R.HERE), "data", "prospects.csv")
REPORT = os.path.join(CACHE, "category_report.txt")
VERDICT = os.path.join(CACHE, "category_verdict.json")
SCORES = os.path.join(CACHE, "category_scores.csv")
RATE_VANTAGES = (2019, 2021, 2022)
RACE_CLASSES = (2021, 2022)
UNGRADED_VANTAGES = (2019, 2021, 2022)
RATE_KEYS = {"H": [k for g in cohorts.GROUPS.values() for k in g],
             "P": [k for g in pcohorts.GROUPS.values() for k in g] + ["gb"]}
PT_KEYS = {"H": [k for g in ("age_level", "contact", "power", "speed") for k in cohorts.GROUPS[g]],
           "P": [k for g in ("age_level", "strikeouts") for k in pcohorts.GROUPS[g]]}
BASELINE = {"H": {"HR": "hr_pa", "R": None, "OBP": "obp", "SLG": "slg"},
            "P": {"K": "k", "ERA": "era", "WHIP": "whip", "HR9": "hr9"}}
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


class Ctx:
    def __init__(self):
        self.d = R.Data()
        for r in self.d.rows["P"]:
            r["f"]["gb"] = self.d.gb.get((r["player_id"], r["season"], r["sport_id"]))
        self.den = context.load_league_denominators(R.STANDINGS)
        self.avg = K.averages()
        self.tables = K.season_tables(2013, NOW)
        self._out = {}

    def out(self, typ, pid, v):
        key = (typ, pid, v)
        if key not in self._out:
            self._out[key] = K.outcome(pid, typ, v, self.tables, self.den, self.avg)
        return self._out[key]

    def best(self, typ, season):
        """One row per player for a season: the highest level."""
        b = {}
        for r in self.d.rows[typ]:
            if r["season"] == season and (r["player_id"] not in b or r["sport_id"] < b[r["player_id"]]["sport_id"]):
                b[r["player_id"]] = r
        return list(b.values())

    def rate_models(self, typ, v, exclude=frozenset()):
        """{cat: (model, fill)} fit on rows whose window is complete by v, players reaching MIN_PT."""
        train = [r for r in self.d.rows[typ] if r["season"] + K.WINDOW <= v and r["player_id"] not in exclude
                 and self.out(typ, r["player_id"], r["season"])[1] >= K.MIN_PT[typ]]
        pts = np.array([self.out(typ, r["player_id"], r["season"])[1] for r in train])
        models = {}
        for c in K.CATS[typ]:
            y = [self.out(typ, r["player_id"], r["season"])[2][c] for r in train]
            models[c] = K.fit_ridge(train, RATE_KEYS[typ], y, w=pts)
        return models, len(train)

    def pt_stats_model(self, typ, v, exclude=frozenset()):
        train = [r for r in self.d.rows[typ] if r["season"] + K.WINDOW <= v and r["player_id"] not in exclude]
        y = [self.out(typ, r["player_id"], r["season"])[1] for r in train]
        return K.fit_ridge(train, PT_KEYS[typ], y), len(train)


def _graded_rows(players):
    """Graded players as rows whose features are FV plus the model-row stats."""
    return [{"player_id": p["player_id"], "f": dict(p["row"]["f"], fv=p["x"]["fv"]), "row": p["row"],
             "fv": p["x"]["fv"]} for p in players]


def race_split(cx, typ, v):
    classes = cx.d.classes[(typ, "rating")]
    test = _graded_rows(classes[v])
    ids = {p["player_id"] for p in test}
    train = _graded_rows([p for c, ps in classes.items() if c != v and asof.rating_known(c, v)
                          for p in ps if p["player_id"] not in ids])
    for r in train + test:
        r["y"] = cx.out(typ, r["player_id"], r["row"]["season"])[1]
    return train, test


def phase_rates(cx):
    out = {}
    for typ in ("H", "P"):
        res = {c: {} for c in K.CATS[typ]}
        for v in RATE_VANTAGES:
            test = [r for r in cx.best(typ, v) if cx.out(typ, r["player_id"], v)[1] >= K.MIN_PT[typ]]
            models, n_train = cx.rate_models(typ, v, exclude={r["player_id"] for r in test})
            for c in K.CATS[typ]:
                y = [cx.out(typ, r["player_id"], v)[2][c] for r in test]
                pred = K.predict(*models[c], test, RATE_KEYS[typ])
                ci = C.rank_ci([{"y": t} for t in y], pred, "rating")
                base = BASELINE[typ][c]
                raw = [r["f"].get(base) for r in test] if base else None
                ok = [(a, b) for a, b in zip(raw, y) if a is not None] if raw else []
                res[c][str(v)] = {"n_train": n_train, "n_test": len(test), "ci": ci,
                                  "raw_rho": float(spearmanr(*zip(*ok)).statistic) if len(ok) > 30 else None}
            print(f"  rates {typ} {v}: train {n_train}, test {len(test)}", flush=True)
        out[typ] = {c: {"vantages": r, "trust": sum(1 for x in r.values() if x["ci"] and x["ci"][1] > 0) >= 2}
                    for c, r in res.items()}
    return out


def phase_race(cx):
    out = {}
    for typ in ("H", "P"):
        res, rhos = {}, {}
        for v in RACE_CLASSES:
            train, test = race_split(cx, typ, v)
            if len(train) < F.MIN_TRAIN_PLAYERS:
                raise SystemExit(f"{typ} race class {v}: {len(train)} training players < {F.MIN_TRAIN_PLAYERS} -- stop")
            y = [r["y"] for r in train]
            pa = K.predict(*K.fit_ridge(train, ["fv"], y), test, ["fv"])
            pb = K.predict(*K.fit_ridge(train, ["fv"] + PT_KEYS[typ], y), test, ["fv"] + PT_KEYS[typ])
            d, se = W.paired_gain(test, pa, pb, "rating")
            res[v] = {"d": d, "se": se}
            yt = [r["y"] for r in test]
            rhos[str(v)] = {"fv": float(spearmanr(pa, yt).statistic), "fv_stats": float(spearmanr(pb, yt).statistic),
                            "d": d, "se": se, "z": W.z_score(d, se), "n_train": len(train), "n_test": len(test)}
        dsum, z, n = F.pooled(res)
        harmed = any(W.z_score(r["d"], r["se"]) <= W.HARM_Z for r in res.values())
        out[typ] = {"classes": rhos, "pooled_d": dsum, "pooled_z": z,
                    "choice": "fv_stats" if (z >= W.WIN_Z and not harmed) else "fv"}
    return out


def _score_rows(cx, typ, test_rows, pt, models, v):
    rates = {c: K.predict(*models[c], test_rows, RATE_KEYS[typ]) for c in K.CATS[typ]}
    repl = cx.tables[v]["repl"][typ]
    return [K.expected_terms(typ, pt[i], {c: rates[c][i] for c in K.CATS[typ]}, repl, cx.den, cx.avg)
            for i in range(len(test_rows))]


def phase_ladder(cx, race):
    out = {"graded": {}, "ungraded": {}}
    for typ in ("H", "P"):
        cols = ["fv"] + (PT_KEYS[typ] if race[typ]["choice"] == "fv_stats" else [])
        g_score, g_act, g_fv = {c: [] for c in K.CATS[typ]}, {c: [] for c in K.CATS[typ]}, []
        for v in RACE_CLASSES:
            train, test = race_split(cx, typ, v)
            pt = np.maximum(K.predict(*K.fit_ridge(train, cols, [r["y"] for r in train]), test, cols), 0.0)
            models, _ = cx.rate_models(typ, v, exclude={r["player_id"] for r in test})
            for r, e in zip(test, _score_rows(cx, typ, [r["row"] for r in test], pt, models, v)):
                a = cx.out(typ, r["player_id"], v)[0]
                for c in K.CATS[typ]:
                    g_score[c].append(e[c])
                    g_act[c].append(a[c])
                g_fv.append(r["fv"])
        u_score, u_act = {c: [] for c in K.CATS[typ]}, {c: [] for c in K.CATS[typ]}
        for v in UNGRADED_VANTAGES:
            rows = cx.best(typ, v)
            m = C.match(CG.people(rows), cx.d.boards[typ][v + 1])
            skip = set(m["matched"]) | m["age_rejected"] | {a["player_id"] for a in m["ambiguous"]}
            test = [r for r in rows if r["player_id"] not in skip]
            ids = {r["player_id"] for r in test}
            (mp, fp), _ = cx.pt_stats_model(typ, v, exclude=ids)
            pt = np.maximum(K.predict(mp, fp, test, PT_KEYS[typ]), 0.0)
            models, _ = cx.rate_models(typ, v, exclude=ids)
            for r, e in zip(test, _score_rows(cx, typ, test, pt, models, v)):
                a = cx.out(typ, r["player_id"], v)[0]
                for c in K.CATS[typ]:
                    u_score[c].append(e[c])
                    u_act[c].append(a[c])
        for c in K.CATS[typ]:
            lad = K.ladder(g_score[c], g_act[c])
            lad["rho_score"] = float(spearmanr(g_score[c], g_act[c]).statistic)
            lad["rho_fv"] = float(spearmanr(g_fv, g_act[c]).statistic)
            out["graded"][f"{typ}_{c}"] = lad
            out["ungraded"][f"{typ}_{c}"] = K.ladder(u_score[c], u_act[c])
        print(f"  ladder {typ}: graded {len(g_fv)}, ungraded {len(u_act[K.CATS[typ][0]])}", flush=True)
    for pop in ("graded", "ungraded"):
        holm = F.holm_adjust({k: v["p"] for k, v in out[pop].items()})
        for k, v in out[pop].items():
            v["holm_p"] = holm[k]
            v["pass"] = K.ladder_pass(v, holm[k])
    return out


def labels(rates, ladder):
    out = {}
    for pop in ("graded", "ungraded"):
        for k, lad in ladder[pop].items():
            typ, c = k.split("_")
            trust = rates[typ][c]["trust"]
            out.setdefault(k, {})[pop] = ("trustworthy" if lad["pass"] and trust else
                                          "level only" if lad["pass"] else "not predictable")
    return out


def phase_scores(cx, race):
    rows_out = []
    for typ in ("H", "P"):
        rows = cx.best(typ, NOW)
        models, _ = cx.rate_models(typ, NOW)
        rates = {c: K.predict(*models[c], rows, RATE_KEYS[typ]) for c in K.CATS[typ]}
        board = S.load_current_board(BOARD, pitchers=typ == "P")
        matched = C.match(CG.people(rows), board)["matched"]
        cols = ["fv"] + (PT_KEYS[typ] if race[typ]["choice"] == "fv_stats" else [])
        classes = cx.d.classes[(typ, "rating")]
        train = _graded_rows([p for c, ps in classes.items() if asof.rating_known(c, NOW) for p in ps])
        for r in train:
            r["y"] = cx.out(typ, r["player_id"], r["row"]["season"])[1]
        mg, fg = K.fit_ridge(train, cols, [r["y"] for r in train])
        (ms, fs), _ = cx.pt_stats_model(typ, NOW)
        repl = cx.tables[NOW]["repl"][typ]
        for i, r in enumerate(rows):
            e = matched.get(r["player_id"])
            if e is not None:
                pt = K.predict(mg, fg, [{"f": dict(r["f"], fv=C.fv_score(e))}], cols)[0]
                path = "FV" if race[typ]["choice"] == "fv" else "FV+stats"
            else:
                pt = K.predict(ms, fs, [r], PT_KEYS[typ])[0]
                path = "stats"
            pt = max(pt, 0.0)
            terms = K.expected_terms(typ, pt, {c: rates[c][i] for c in K.CATS[typ]}, repl, cx.den, cx.avg)
            row = {"player_id": r["player_id"], "name": CG.safe(r["name"]), "type": typ,
                   "level": cohorts.LEVEL_NAMES.get(r["sport_id"], ""), "age": r.get("age_raw"),
                   "board_key": CG.safe(e["fg_id"]) if e else "", "pt_path": path, "expected_pt": round(pt, 1)}
            row.update({c: round(terms[c], 3) if c in terms else "" for c in K.HIT_CATS + K.PIT_CATS})
            rows_out.append(row)
    with open(SCORES, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    return {"n": {t: sum(1 for r in rows_out if r["type"] == t) for t in ("H", "P")}}


def checkpoint(name, force, fn):
    path = os.path.join(CACHE, f"category_{name}.json")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every phase")
    force = ap.parse_args().force
    holder = {}

    def cx():
        if "cx" not in holder:
            print("building data ...", flush=True)
            holder["cx"] = Ctx()
        return holder["cx"]

    rates = checkpoint("rates", force, lambda: phase_rates(cx()))
    race = checkpoint("race", force, lambda: phase_race(cx()))
    ladder = checkpoint("ladder", force, lambda: phase_ladder(cx(), race))
    scores = checkpoint("scores", force, lambda: phase_scores(cx(), race))
    lab = labels(rates, ladder)

    L = ["ROTO CATEGORY SCORES -- spec 2026-10-09-category-score-design.md", ""]
    L.append("1. PART 2 -- MLB rates when he plays (Spearman predicted vs actual rate; 95% CI; "
             "raw minor-league stat for reference)")
    for typ in ("H", "P"):
        for c, v in rates[typ].items():
            per = "; ".join(f"{y}: " + ("n/a" if x["ci"] is None else
                                        f"{x['ci'][0]:+.3f} [{x['ci'][1]:+.3f}, {x['ci'][2]:+.3f}]")
                            + (f" (raw {x['raw_rho']:+.3f})" if x["raw_rho"] is not None else "")
                            + f" n={x['n_test']}" for y, x in v["vantages"].items())
            L.append(f"  {typ} {c:4}: {per} -> {'TRUSTWORTHY' if v['trust'] else 'not trustworthy'}")
    L += ["", "2. PART 1 -- 4-year playing time race (graded; Spearman with actual PA/IP)"]
    for typ in ("H", "P"):
        v = race[typ]
        for y, x in v["classes"].items():
            L.append(f"  {typ} class {y}: FV {x['fv']:+.3f} vs FV+stats {x['fv_stats']:+.3f} "
                     f"(gain {x['d']:+.4f}, z {x['z']:+.1f}; train {x['n_train']}, test {x['n_test']})")
        L.append(f"  {typ}: pooled z {v['pooled_z']:+.2f} -> use "
                 f"{'FV + stats' if v['choice'] == 'fv_stats' else 'FV alone'}")
    for pop, title in (("graded", "graded classes 2021+2022"), ("ungraded", "ungraded, vantages 2019+2021+2022")):
        L += ["", f"3. WALK-UP LADDERS -- {title} (mean actual 4-year category SGP by score bucket, low -> high)"]
        for k, lad in ladder[pop].items():
            extra = f"; score rho {lad['rho_score']:+.3f} vs FV rho {lad['rho_fv']:+.3f}" if "rho_fv" in lad else ""
            L.append(f"  {k:6}: " + " < ".join(f"{m:+.2f}" for m in lad["means"])
                     + f"  (n {lad['counts'][0]}/bucket) top-bottom {lad['d']:+.2f} (z {lad['z']:+.1f}, Holm p "
                     f"{lad['holm_p']:.4f}), inversions {lad['inversions']} -> {'PASS' if lad['pass'] else 'fail'}{extra}")
    L += ["", "4. LABELS (per population)"]
    for k, v in lab.items():
        L.append(f"  {k:6}: graded {v['graded']}; ungraded {v['ungraded']}")
    L += ["", f"5. SCORES: {SCORES} ({scores['n']['H']} hitters, {scores['n']['P']} pitchers, 2026 rows)"]
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(VERDICT, "w", encoding="utf-8") as fh:
        json.dump({"generated": datetime.date.today().isoformat(), "labels": lab,
                   "pt_choice": {t: race[t]["choice"] for t in ("H", "P")}}, fh, indent=2)


if __name__ == "__main__":
    main()
