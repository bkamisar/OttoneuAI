"""Sub-project 4: writes data/prospect_model.json for prospects.html.

Usage:  python build_shopping_list.py
Reads cache/hitter_ratings.csv (model3c_final.py) and cache/pitcher_ratings.csv
(model_p_final.py), the site's current FanGraphs board ../data/prospects.csv, and the old Board lists in cache/fv/ (earlier-list
flag only), plus 'soon' ranks from cache/fvplus_scores.csv (run build_fvplus_scores.py
first) and hitter category profiles from cache/category_scores.csv (category_run.py). No network. Rerun whenever data/prospects.csv or the ratings change, then
commit data/prospects.csv and data/prospect_model.json together.
"""
import datetime
import json
import os

from psmodel import cohorts
from psmodel import consensus as C
from psmodel import shopping as S

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
FV_DIR = os.path.join(CACHE, "fv")
DATA = os.path.join(os.path.dirname(HERE), "data")
RATINGS = os.path.join(CACHE, "hitter_ratings.csv")
P_RATINGS = os.path.join(CACHE, "pitcher_ratings.csv")
BOARD = os.path.join(DATA, "prospects.csv")
OUT = os.path.join(DATA, "prospect_model.json")
FVP = os.path.join(CACHE, "fvplus_scores.csv")
CATS = os.path.join(CACHE, "category_scores.csv")
SEASON = cohorts.CURRENT_SEASON


def main():
    ratings = S.load_ratings(RATINGS)
    board = S.load_current_board(BOARD)
    history = {y: C.load_board(C.board_path(FV_DIR, y)) for y in range(2017, SEASON + 1)
               if os.path.exists(C.board_path(FV_DIR, y))}
    graded, ungraded, unreadable = S.build(ratings, board, history)
    counts = {"board_hitters": len(board), "graded_with_model": len(graded),
              "board_without_model": len(board) - len(graded), "ungraded": len(ungraded),
              "unreadable": len(unreadable)}
    p_ratings = S.load_pitcher_ratings(P_RATINGS)
    p_board = S.load_current_board(BOARD, pitchers=True)
    p_history = {y: C.load_board(C.board_path(FV_DIR, y, "pitchers")) for y in range(2017, SEASON + 1)
                 if os.path.exists(C.board_path(FV_DIR, y, "pitchers"))}
    p_graded, p_ungraded, p_unreadable = S.build(p_ratings, p_board, p_history, pitchers=True)
    p_counts = {"board_pitchers": len(p_board), "graded_with_model": len(p_graded),
                "board_without_model": len(p_board) - len(p_graded), "ungraded": len(p_ungraded),
                "unreadable": len(p_unreadable)}
    fvp = S.load_fvplus(FVP)
    cats = S.load_categories(CATS)
    out = {"generated": datetime.date.today().isoformat(), "season": SEASON, "counts": counts,
           "graded": graded, "ungraded": ungraded, "unreadable_keys": unreadable,
           "pitchers": {"counts": p_counts, "graded": p_graded, "ungraded": p_ungraded,
                        "unreadable_keys": p_unreadable},
           "fvplus": fvp, "categories": cats}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(json.dumps(counts))
    print(f"Soon reads: {len(fvp['H'])} hitters, {len(fvp['P'])} pitchers"
          + ("" if fvp["H"] else "  (cache/fvplus_scores.csv missing -- run build_fvplus_scores.py)"))
    print(f"Hitter category profiles: {len(cats['by_key'])} board hitters, {len(cats['by_id'])} in all"
          + ("" if cats["by_id"] else "  (cache/category_scores.csv missing -- run category_run.py)"))
    print("graded, first 10 by key:\n  " + "\n  ".join(
        f"{g['key']}  ~{g['odds']}%  {g['take']}" for g in graded[:10]))
    print("ungraded, top 10 by model:\n  " + "\n  ".join(
        f"{u['name']} ({u['level']}, {u['age']}) {u['rating_pct']:.0%}  ~{u['odds']}%  {u['take']}"
        for u in ungraded[:10]))
    print(json.dumps(p_counts))
    print("pitchers, ungraded top 10 by model:\n  " + "\n  ".join(
        f"{u['name']} ({u['level']}, {u['age']}, {u['role']}) {u['rating_pct']:.0%}  top {u['tier'] or '>25'}%  {u['take']}"
        for u in p_ungraded[:10]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
