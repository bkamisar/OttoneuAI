"""'Soon' ranks for the site's current board: FanGraphs FV + level + age.

The red-team check (spec 2026-10-09-category-score-design.md, "Red-team result")
found the adopted FV+ soon model reduces to FV + level + age; for pitchers the
simpler model was better. This refits that simpler logit on every class with
soon answers and scores the board's graded players from their 2026 rows.
Always runs fresh (the board changes). No network.

Usage:  python build_fvplus_scores.py   -> cache/fvplus_scores.csv (gitignored)
"""
import csv
import os

import consensus_gate as CG
import fvplus_run as R
from psmodel import asof
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import shopping as S
from psmodel import walkforward as W

OUT = os.path.join(R.CACHE, "fvplus_scores.csv")
BOARD = os.path.join(os.path.dirname(R.HERE), "data", "prospects.csv")
COLS = ["fv", "is_aaa", "is_aa", "is_higha", "age_raw"]


def x_of(fv, row):
    f = row["f"]
    return {"fv": fv, "is_aaa": f.get("is_aaa"), "is_aa": f.get("is_aa"), "is_higha": f.get("is_higha"),
            "age_raw": row.get("age_raw")}


def main():
    d = R.Data()
    out = []
    for typ in ("H", "P"):
        train = [{"player_id": p["player_id"], "x": x_of(p["x"]["fv"], p["row"]), "y": W._y(p["row"], "soon", None)}
                 for c, ps in d.classes[(typ, "soon")].items() if asof.soon_known(c, R.NOW) for p in ps]
        model, fill = F.fit(train, COLS, "soon")
        board = S.load_current_board(BOARD, pitchers=typ == "P")
        best = {}
        for r in d.rows[typ]:
            if r["season"] == R.NOW and (r["player_id"] not in best
                                         or r["sport_id"] < best[r["player_id"]]["sport_id"]):
                best[r["player_id"]] = r
        rows = list(best.values())
        matched = C.match(CG.people(rows), board)["matched"]
        players = [{"key": matched[r["player_id"]]["fg_id"], "player_id": r["player_id"],
                    "x": x_of(C.fv_score(matched[r["player_id"]]), r)} for r in rows if r["player_id"] in matched]
        ranks, tiers = F.rank_tiers(F.predict(model, fill, players, COLS, "soon"))
        out += [{"key": p["key"], "type": typ, "player_id": p["player_id"], "rank": k, "tier": t}
                for p, k, t in zip(players, ranks, tiers)]
        top = sorted(zip(players, ranks), key=lambda z: z[1])[:15]
        print(f"{typ}: trained on {len(train)} players ({sum(p['y'] for p in train):.0f} successes); "
              f"scored {len(players)} of {len(board)} board players")
        print("  top 15: " + "; ".join(p["key"] for p, _ in top))
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["key", "type", "player_id", "rank", "tier"])
        w.writeheader()
        w.writerows(out)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
