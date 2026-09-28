"""Pre-registered one-shot test: do FanGraphs' bat grades beat FV for fantasy value?

Spec: docs/superpowers/specs/2026-09-28-post-build-queue-design.md, part C. The
rules were written before anyone looked: one fixed formula, plan C's population,
plan C's adoption rule, run once. Do not add formulas after seeing the result.

bat = (Hit future + Game Power future) / 2, from the same Board row as FV, ties
broken by FanGraphs' order. Players missing either grade are dropped from BOTH
rankings, so both are scored on identical players.

Usage:  python toolgrade_test.py
Reads cached data and cache/fv/. No network. Writes cache/toolgrade_report.txt.
"""
import json
import os
import warnings

import numpy as np

import consensus_gate as G
from psmodel import asof, cohorts, dataset
from psmodel import consensus as C
from psmodel import walkforward as W

REPORT = os.path.join(G.CACHE, "toolgrade_report.txt")
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


def bat_score(e):
    """Mean future bat grade; + fv_score/100 breaks ties without crossing a 2.5 step."""
    return (e["hit_fut"] + e["pwr_fut"]) / 2 + C.fv_score(e) / 100


def snapshot_check(boards):
    """[(year, players on both lists, share whose FV changed, share whose Hit future changed)]."""
    out = []
    for y in sorted(boards):
        if y + 1 not in boards:
            continue
        a = {e["fg_id"]: e for e in boards[y]}
        b = {e["fg_id"]: e for e in boards[y + 1]}
        both = [k for k in a if k in b]
        if both:
            out.append((y, len(both), sum(a[k]["fv"] != b[k]["fv"] for k in both) / len(both),
                        sum(a[k]["hit_fut"] != b[k]["hit_fut"] for k in both) / len(both)))
    return out


def main():
    labels = dataset.load_labels(os.path.join(G.CACHE, "labels.csv"))
    asof.attach_ranks(labels)
    rows = cohorts.build_rows(cohorts.load_milb(), cohorts.mlb_pa_history(),
                              {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    with open(os.path.join(G.CACHE, "model3c_final.json"), encoding="utf-8") as fh:
        dec = json.load(fh)
    boards = {y: C.load_board(C.board_path(G.FV_DIR, y)) for y in range(G.FIRST_LIST, G.LAST_LIST + 1)
              if os.path.exists(C.board_path(G.FV_DIR, y))}

    L = ["TOOL-GRADE TEST (pre-registered, run once): bat grades vs FV on plan C's graded hitters",
         "bat = (Hit future + Game Power future) / 2; challenger = bat, base = FanGraphs' FV order.", "",
         "Snapshot check (tool grades must change between lists, like FV):"]
    snap = snapshot_check(boards)
    L += [f"  lists {y}->{y + 1}: {n} players on both; FV changed {fv:.0%}, Hit future changed {hit:.0%}"
          for y, n, fv, hit in snap]
    if any(hit == 0 for _, _, _, hit in snap):
        L.append("  STOP: a list pair shows no Hit-grade changes -- grades may not be per-list snapshots.")
    else:
        for t in ("rating", "soon"):
            L += ["", f"{t.upper()}"]
            res = {}
            for v in G.TESTS[t] + G.INFO[t]:
                ctx = asof.ref_curve(labels, v)
                _, test = W.frames(rows, t, v, ctx, dec[t]["keys"], unseal=v in G.INFO[t])
                test, _ = G.one_per_player(test, np.zeros(len(test)))
                m = C.match(G.people(test), boards[v + 1])
                grp = [(r, m["matched"][r["player_id"]]) for r in test if r["player_id"] in m["matched"]]
                grp = [(r, e) for r, e in grp if e["hit_fut"] is not None and e["pwr_fut"] is not None]
                h = C.head_to_head([r for r, _ in grp], [C.fv_score(e) for _, e in grp],
                                   [bat_score(e) for _, e in grp], t, ctx)
                info = v in G.INFO[t]
                L.append(G.line(f"class {v} vs list {v + 1} (n={len(grp)}"
                                f"{', INFORMATION ONLY' if info else ''})", h))
                if not info:
                    res[v] = h
            ok, wins, avail = W.adopt(res)
            L.append(f"  VERDICT ({t}): {'BAT GRADES BEAT FV' if ok else 'no -- FV stands'} "
                     f"({wins}/{avail} classes >= 1 SE)")
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
