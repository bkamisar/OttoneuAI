"""Pitchers P-E: the pitch-level stuff score, and the PRE-REGISTERED choice between it
and P-C's season-level score (spec: docs/superpowers/specs/2026-09-28-pitchers-design.md,
"P-E: the pitch-level stuff model").

  1. Adoption on MLB t = 2020-25 (pitch models trained on MLB 2020-26; in-sample, disclosed).
  2. The as-of prospect gate for BOTH scores on identical AAA pitchers, cohorts 2022-23,
     vantage c = the cohort year: pitch models on MLB <= c, value mapping on MLB t <= c-1,
     AAA->MLB offsets from same-season pairs <= c. The season-level score is refit the same
     way (Savant t <= c-1).
  3. The paired player-bootstrap difference, and the verdict by pitchlevel.choose.

Usage:  python pitchlevel_run.py [--force]
Reads only cached data (build_pitch_frames.py and stuff_run.py first). The per-vantage
pitcher tables are checkpointed to cache/pl_tables/ (--force rebuilds them). Writes
cache/pitchlevel_report.txt and cache/stuff_choice_final.json (gitignored).
"""
import argparse
import json
import os
import time

import numpy as np

import build_pitch_frames as BPF
import step1_run as S1
from psmodel import context, evaluate, milb, pcohorts, statsapi, step1, stuff
from psmodel import pitchlevel as PL
from stuff_run import adoption_line

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "pitchlevel_report.txt")
FINAL = os.path.join(CACHE, "stuff_choice_final.json")
P_C_CHOICE = os.path.join(CACHE, "stuff_choice.json")
TABLE_DIR = os.path.join(CACHE, "pl_tables")
PL_GROUPS = {"whiff": ["pl_whiff"], "damage": ["pl_damage"]}
PL_KEYS = ["pl_whiff", "pl_damage"]
KIND = "ridge"                           # spec: ridge on age + the adopted pitch-level features
PL_FIRST, AAA_FIRST, LAST_FRAME = 2020, 2022, 2026
ADOPT_LAST = 2025                        # season t for adoption; outcomes run through 2026
SAVANT_FIRST = 2015
GATE = (2022, 2023)
_FRAMES = {}


def load_frame(season, sport):
    if (season, sport) not in _FRAMES:
        path = BPF.frame_path(season, sport)
        if not os.path.exists(path):
            raise SystemExit(f"missing {path} -- finish the download, then run build_pitch_frames.py")
        with np.load(path) as z:
            _FRAMES[(season, sport)] = {k: z[k] for k in z.files}
    return _FRAMES[(season, sport)]


def vantage_tables(name, last_mlb, force):
    """Pitch models trained on MLB PL_FIRST..last_mlb, then every MLB and AAA
    pitcher-season through last_mlb graded: ({(pid, s): features} MLB, same for AAA).
    Checkpointed per vantage."""
    path = os.path.join(TABLE_DIR, f"{name}.json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        print(f"[{name}] tables loaded from checkpoint", flush=True)
        return tuple({(pid, s): f for pid, s, f in saved[lvl]} for lvl in ("mlb", "aaa"))
    t0 = time.time()
    models = PL.train([load_frame(s, 1) for s in range(PL_FIRST, last_mlb + 1)])
    print(f"[{name}] pitch models trained on MLB {PL_FIRST}-{last_mlb} ({time.time() - t0:.0f}s)", flush=True)
    out = []
    for sport, first in ((1, PL_FIRST), (11, AAA_FIRST)):
        tab = {}
        for s in range(first, last_mlb + 1):
            for pid, f in PL.pitcher_features(models, load_frame(s, sport)).items():
                tab[(pid, s)] = f
        out.append(tab)
    os.makedirs(TABLE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({lvl: [[pid, s, f] for (pid, s), f in tab.items()] for lvl, tab in zip(("mlb", "aaa"), out)}, fh)
    os.replace(tmp, path)
    print(f"[{name}] graded {len(out[0])} MLB and {len(out[1])} AAA pitcher-seasons ({time.time() - t0:.0f}s)",
          flush=True)
    return tuple(out)


def upto(table, last, first=0):
    return {k: v for k, v in table.items() if first <= k[1] <= last}


def finish(L, code):
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild the checkpointed pitcher tables")
    args = ap.parse_args()
    for s in range(PL_FIRST, LAST_FRAME + 1):          # fail fast, before any training
        if not os.path.exists(BPF.frame_path(s, 1)):
            raise SystemExit(f"missing MLB {s} frames -- finish the download, then run build_pitch_frames.py")

    L = []
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB)
                 for s in range(SAVANT_FIRST, stuff.LAST_OUTCOME_SEASON + 1)}
    stats = {}
    for s, rs in by_season.items():
        for r in rs:
            if (r["player_id"], s) in stats:
                raise SystemExit(f"duplicate StatsAPI MLB pitching row for {r['player_id']} in {s}")
            stats[(r["player_id"], s)] = r
    values = stuff.season_values(by_season, den)
    threshold = stuff.useful_threshold(values)
    with open(P_C_CHOICE, encoding="utf-8") as fh:
        pc = json.load(fh)
    s_keys, s_kind = pc["score_keys"], pc["kind"]
    s_metrics = [k for k in s_keys if k != "age"]
    sv_mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    sv_aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))

    # 1. Adoption on MLB
    mlb_all, _ = vantage_tables("all", LAST_FRAME, args.force)
    built = stuff.mlb_rows(upto(mlb_all, ADOPT_LAST), values, stats, threshold, keys=PL_KEYS)
    rows = step1.complete(built, ["age"] + PL_KEYS + stuff.BOX)
    L += ["PITCH-LEVEL STUFF SCORE (P-E) -- and the pre-registered choice vs the season-level score",
          f"MLB rows: {len(rows)} pitcher-seasons ({len(built) - len(rows)} dropped for a missing value), "
          f"{len({r['player_id'] for r in rows})} pitchers, t={PL_FIRST}-{ADOPT_LAST}; mapping model: {KIND}",
          "  (pitch models trained on MLB 2020-26 here, so each row's own pitches were in training -- disclosed)", ""]
    L.append("1. Which pitch-level features earn their place (each vs age + the OTHER; rank gain in >=8/10 "
             "shuffles, mean top-50 change >= -0.04):")
    adopted = []
    for g, ks in PL_GROUPS.items():
        others = [k for h in PL_GROUPS if h != g for k in PL_GROUPS[h]]
        ok, line = adoption_line(g, evaluate.compare(rows, ["age"] + others, ks, seeds=S1.SEEDS, kind=KIND))
        L.append(line)
        if ok:
            adopted.append(g)
    p_keys = ["age"] + [k for g in adopted for k in PL_GROUPS[g]]
    p_metrics = p_keys[1:]
    L += [f"  adopted: {adopted or 'NONE'}", ""]

    both = []
    for r in rows:
        sv = sv_mlb.get((r["player_id"], r["season"])) or {}
        if (sv.get("pitches") or 0) >= stuff.MIN_PITCHES:
            both.append(dict(r, f=dict(r["f"], **{k: sv.get(k) for k in s_metrics})))
    both = step1.complete(both, s_keys + PL_KEYS)
    L.append(f"2. Context on identical MLB pitcher-seasons (n={len(both)}, report only), mean out-of-fold rho:")
    for label, keys, kind in (("box (age, K%, BB%)", ["age"] + stuff.BOX, KIND),
                              ("season-level stuff (P-C)", s_keys, s_kind),
                              ("pitch-level, both features", ["age"] + PL_KEYS, KIND)) + (
                             (("pitch-level, adopted", p_keys, KIND),) if adopted else ()):
        L.append(f"  {label:28} {S1.mean_oof_rho(both, keys, kind):.4f}")
    L.append("")

    # 2. As-of prospect gate, both scores, identical pitchers
    aaa_stats = {(r["player_id"], s): r for s in GATE for r in milb.season_rows(s, statsapi.AAA, "pitching")}
    ip_history = pcohorts.mlb_ip_history()
    base = step1.complete(stuff.aaa_rows(sv_aaa, aaa_stats, values, GATE, threshold, ip_history),
                          s_keys + stuff.BOX)
    L.append(f"3. As-of prospect gate -- AAA pitchers {GATE[0]}-{GATE[1]} (first qualifying season, not established)")
    P = {k: [] for k in ("pid", "season", "arrived", "target", "useful", "s", "p", "kpct")}
    dropped = 0
    for c in GATE:
        cohort = [r for r in base if r["season"] == c]
        s_rows = step1.complete(stuff.mlb_rows(upto(sv_mlb, c - 1, SAVANT_FIRST), values, stats, threshold), s_keys)
        s_model = evaluate.fit(s_rows, s_keys, s_kind)
        s_trans = stuff.fit_translation(upto(sv_aaa, c), upto(sv_mlb, c), s_metrics)
        line = (f"  vantage {c}: season-level mapped on {len(s_rows)} MLB rows (Savant t {SAVANT_FIRST}-{c - 1}), "
                f"offsets from {min(t['n'] for t in s_trans.values())}+ pairs")
        if adopted:
            mlb_c, aaa_c = vantage_tables(str(c), c, args.force)
            p_rows = step1.complete(stuff.mlb_rows(upto(mlb_c, c - 1), values, stats, threshold, keys=PL_KEYS), p_keys)
            p_model = evaluate.fit(p_rows, p_keys, KIND)
            p_trans = stuff.fit_translation(aaa_c, mlb_c, p_metrics)
            line += (f"; pitch-level mapped on {len(p_rows)} MLB rows (t {PL_FIRST}-{c - 1}), offsets "
                     + ", ".join(f"{k} {t['offset']:+.4f} (n={t['n']})" for k, t in p_trans.items()))
            keep = []
            for r in cohort:
                pl = aaa_c.get((r["player_id"], c))
                if pl and (pl.get("pitches") or 0) >= stuff.MIN_PITCHES and all(pl.get(k) is not None for k in p_metrics):
                    keep.append(dict(r, pf=step1.translate(dict(r["f"], **{k: pl[k] for k in p_metrics}), p_trans)))
            dropped += len(cohort) - len(keep)
            cohort = keep
            p_score = evaluate.predict(p_model, [dict(r, f=r["pf"]) for r in cohort], p_keys) if cohort else []
        else:
            p_score = [np.nan] * len(cohort)
        s_score = evaluate.predict(s_model, [dict(r, f=step1.translate(r["f"], s_trans)) for r in cohort],
                                   s_keys) if cohort else []
        L.append(line)
        for r, a, b in zip(cohort, s_score, p_score):
            for k, v in (("pid", r["player_id"]), ("season", c), ("arrived", r["arrived"]), ("target", r["target"]),
                         ("useful", r["useful"]), ("s", float(a)), ("p", float(b)), ("kpct", r["f"]["k"])):
                P[k].append(v)
    arr = [i for i, a in enumerate(P["arrived"]) if a]
    L.append(f"  identical pitchers: {len(P['pid'])} ({dropped} dropped for too few graded pitches), "
             f"{len(arr)} reached a 25+ IP MLB season, {sum(P['useful'])} reached the useful line")
    if len(arr) < 10:
        L.append("GATE: too few arrivals to test -- nothing decided")
        return finish(L, 1)
    y = [P["target"][i] for i in arr]
    pick = lambda k: np.array([P[k][i] for i in arr], dtype=float)
    res = {}
    for label, k in (("season-level (P-C)", "s"), ("pitch-level (P-E)", "p"), ("AAA K% (reference)", "kpct")):
        if k == "p" and not adopted:
            L.append(f"  {label:20} not run -- no pitch-level feature adopted")
            continue
        res[k] = step1.spearman_ci(pick(k), y)
        L.append(f"  {label:20} Spearman vs later MLB value {res[k][0]:+.3f} [{res[k][1]:+.3f}, {res[k][2]:+.3f}]")
        for c in GATE:
            idx = [j for j, i in enumerate(arr) if P["season"][i] == c]
            if len(idx) >= 10:
                rho = step1.spearman_ci(pick(k)[idx], [y[j] for j in idx])[0]
                L.append(f"    cohort {c} (report only): n={len(idx)}, rho {rho:+.3f}")
    diff = se = None
    if adopted:
        diff, se = PL.paired_rho_diff(pick("p"), pick("s"), y)
        L.append(f"  pitch-level minus season-level: {diff:+.3f}, paired player-bootstrap SE {se:.3f}")
    choice = PL.choose(res["s"][1], res["p"][1] if adopted else None, diff, se)
    L += ["", "VERDICT (pre-registered rule): " + {
        "pitch": "PITCH-LEVEL -- it replaces the season-level stuff score for P-D",
        "season": "SEASON-LEVEL -- P-C's score stays (pitch-level did not beat it by >= 1 SE with its CI above 0)",
        "none": "NONE -- neither score's as-of CI clears 0; stuff is out for pitchers until new cohorts arrive"}[choice]]

    with open(FINAL, "w", encoding="utf-8") as fh:
        json.dump({"choice": choice, "gate_cohorts": list(GATE), "threshold": threshold,
                   "n_pitchers": len(P["pid"]), "n_arrived": len(arr), "diff": diff, "se": se,
                   "season": {"score_keys": s_keys, "kind": s_kind, "rho_ci": res["s"]},
                   "pitch": {"adopted": adopted, "score_keys": p_keys, "kind": KIND,
                             "rho_ci": res.get("p"), "pitch_models_train": [PL_FIRST, "vantage"]},
                   "kpct_rho_ci": res["kpct"]}, fh, indent=2)
    return finish(L, 0)


if __name__ == "__main__":
    raise SystemExit(main())
