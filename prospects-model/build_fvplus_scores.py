"""FV+ soon for the site's current board (spec 2026-09-30-fv-plus-design.md, Phase 3).

Refits the adopted FV+ soon models (hitters, pitchers) on every class with soon
answers and scores the board's graded players from their 2026 minor-league rows.
The site board codes every outfielder "OF": a player's position comes from the
2026 preseason list when his name is on it once, else "OF" counts as not premium.
Always runs fresh (the board changes). No network (run fetch_standings.py first).

Usage:  python build_fvplus_scores.py   -> cache/fvplus_scores.csv (gitignored)
"""
import csv
import os

import consensus_gate as CG
import fvplus_run as R
from psmodel import asof, mlbteams
from psmodel import consensus as C
from psmodel import fvplus as F
from psmodel import shopping as S
from psmodel import walkforward as W

OUT = os.path.join(R.CACHE, "fvplus_scores.csv")
BOARD = os.path.join(os.path.dirname(R.HERE), "data", "prospects.csv")
RATINGS = {"H": "hitter_ratings.csv", "P": "pitcher_ratings.csv"}


def main():
    d = R.Data()
    win = mlbteams.win_pct(R.NOW)
    out = []
    for typ in ("H", "P"):
        m = (typ, "soon")
        train = [dict(p, y=W._y(p["row"], "soon", None)) for c, ps in d.classes[m].items()
                 if asof.soon_known(c, R.NOW) for p in ps]
        cols = ["fv"] + F.keys(typ, "soon")
        model, fill = F.fit(train, cols, "soon")
        board = S.load_current_board(BOARD, pitchers=typ == "P")
        pre = {}
        for e in d.boards[typ].get(R.NOW, []):
            pre.setdefault(e["key"], []).append(e["pos"])
        fixed = 0
        for e in board:
            if e["pos"] == "OF" and len(pre.get(e["key"], [])) == 1:
                e["pos"], fixed = pre[e["key"]][0], fixed + 1
        best = {}
        for r in d.rows[typ]:
            if r["season"] == R.NOW and (r["player_id"] not in best
                                         or r["sport_id"] < best[r["player_id"]]["sport_id"]):
                best[r["player_id"]] = r
        rows = list(best.values())
        matched = C.match(CG.people(rows), board)["matched"]
        with open(os.path.join(R.CACHE, RATINGS[typ]), encoding="utf-8", newline="") as fh:
            sm = {int(q["player_id"]): float(q["p_useful_within_2"]) for q in csv.DictReader(fh)}
        med = F.medians(board, typ)
        players = []
        for r in rows:
            e = matched.get(r["player_id"])
            if e is None:
                continue
            gb = d.gb.get((r["player_id"], R.NOW, r["sport_id"])) if typ == "P" else None
            x = F.features(typ, e, r, med, win[mlbteams.team_of(e["org"])[0]], gb)
            players.append({"key": e["fg_id"], "player_id": r["player_id"], "name": r["name"], "x": x,
                            "sm_raw": sm.get(r["player_id"])})
        scored = [p for p in players if p["sm_raw"] is not None]
        for p, q in zip(scored, C.pct([p["sm_raw"] for p in scored])):
            p["x"]["sm"] = float(q)
        ranks, tiers = F.rank_tiers(F.predict(model, fill, players, cols, "soon"))
        out += [{"key": p["key"], "type": typ, "player_id": p["player_id"], "rank": k, "tier": t}
                for p, k, t in zip(players, ranks, tiers)]
        top = sorted(zip(players, ranks), key=lambda z: z[1])[:15]
        print(f"{typ}: trained on {len(train)} players ({sum(p['y'] for p in train):.0f} successes); "
              f"scored {len(players)} of {len(board)} board players; {fixed} 'OF' positions from the preseason list")
        print("  top 15: " + "; ".join(p["key"] for p, _ in top))
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["key", "type", "player_id", "rank", "tier"])
        w.writeheader()
        w.writerows(out)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
