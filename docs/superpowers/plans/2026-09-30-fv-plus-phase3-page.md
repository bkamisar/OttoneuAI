# FV+ Phase 3: FV+ Soon on the Shopping List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score the site's current board with the adopted FV+ soon models and show them on `prospects.html`:
- a "Closest to helping" lens for hitters AND pitchers, sorted by FV+ soon;
- an "FV+ soon" column.

This is spec `docs/superpowers/specs/2026-09-30-fv-plus-design.md`, "Phase 3".

**Architecture:**
- `build_fvplus_scores.py` reuses `fvplus_run.Data`, refits FV+ soon on every class with soon answers, and scores current-board players from their 2026 rows. It writes `cache/fvplus_scores.csv` and always runs fresh.
- `build_shopping_list.py` adds a `fvplus` block (key -> rank, tier) to `data/prospect_model.json`.
- The hitters' old 50/50 `ready_rank` is removed.
- The page reads the block.

**Tech Stack:** Python 3.14 (numpy, sklearn), vanilla JS. Executed inline on Opus.

**Display choice (a small refinement of the spec, recorded here):**
- The column shows the rank, `#12`, plus `· Top 5%` / `· Top 10%` / `· Top 25%` when in those tiers.
- A bare tier would print "—" for most players, which reads as "no read".
- Still no percentages.

---

### Task 1: Board grades, the FV+ loader, and removing the blend rank (shopping.py)

**Files:**
- Modify: `prospects-model/psmodel/shopping.py`
- Modify: `prospects-model/tests/test_shopping.py`

- [ ] **Step 1: Tests first.**

  In `TestBoardFile.test_load_current_board`:
  - extend `header` with `"Hit_Fut", "Game_Fut", "Raw_Fut", "Spd_Fut", "CMD_Fut"`;
  - give the Ann Able rows `"55", "45", "60", "50", ""`;
  - add these assertions:

  ```python
        self.assertEqual((e["hit_fut"], e["pwr_fut"], e["raw_pwr_fut"], e["spd_fut"], e["cmd_fut"]),
                         (55, 45, 60, 50, None))
        self.assertEqual((e["org"], e["pos"]), ("SEA", "SS"))
  ```

  Replace the `ready_rank` assertion in `TestBuild.test_build` with:

  ```python
        self.assertEqual([(g["key"], g["odds"]) for g in graded],
                         [("Ann Able|SEA", 60), ("Bo Baker|NYY", 40), ("Cy Cole|BOS", 10)])
        self.assertTrue(all("ready_rank" not in g for g in graded))
  ```

  and delete the `# fv pct ... ready ...` comment line above it. Then add:

  ```python
class TestFvplusLoader(unittest.TestCase):
    def test_load_fvplus(self):
        rows = [["key", "type", "player_id", "rank", "tier"],
                ["Ann Able|SEA", "H", "1", "2", "5"], ["Pat Pitch|SEA", "P", "9", "1", "0"]]
        with tempfile.TemporaryDirectory() as d:
            got = S.load_fvplus(write_csv(d, "fvplus_scores.csv", rows))
            self.assertEqual(S.load_fvplus(os.path.join(d, "absent.csv")), {"H": {}, "P": {}})
        self.assertEqual(got, {"H": {"Ann Able|SEA": {"rank": 2, "tier": 5}},
                               "P": {"Pat Pitch|SEA": {"rank": 1, "tier": 0}}})
  ```

- [ ] **Step 2:** `python -m pytest tests/test_shopping.py -q`. Expected: failures (no grades, `ready_rank` present, no `load_fvplus`).

- [ ] **Step 3: Implement in `shopping.py`.**
  - Module docstring, second paragraph: replace "the average of the FV and model percentiles for "closest to helping"" with "FV+ soon (build_fvplus_scores.py) for "closest to helping"".
  - Add `import os`.
  - After `NEVER_LISTED`, add:

    ```python
    GRADE_COLS = {"hit_fut": "Hit_Fut", "pwr_fut": "Game_Fut", "raw_pwr_fut": "Raw_Fut", "spd_fut": "Spd_Fut",
                  "fb_fut": "FB_Fut", "sl_fut": "SL_Fut", "cb_fut": "CB_Fut", "ch_fut": "CH_Fut", "cmd_fut": "CMD_Fut"}
    ```

  - In `load_current_board`, change the appended dict to also carry grades, org and first position. They stay in memory only and are never written out:

    ```python
            e = {"fg_id": key, "name": name, "key": C.norm_name(name), "age": C._num(_cell(r, idx, "Age")),
                 "fv": fv, "top100": C._rank(_cell(r, idx, "Top 100")),
                 "org_rk": C._rank(_cell(r, idx, "Org Rk")),
                 "org": _cell(r, idx, "Org"), "pos": _cell(r, idx, "Pos").split("/")[0].strip()}
            e.update({k: C.parse_fv(_cell(r, idx, h)) for k, h in GRADE_COLS.items()})
            out.append(e)
    ```

  - In `build()`, delete the `rank = ...` lines. The hitter branch becomes:

    ```python
        else:
            graded = sorted(({"key": e["fg_id"], "player_id": r["player_id"], "odds": odds(r["soon"]),
                              "take": take(s - f, t - f)}
                             for r, e, f, s, t in zip(rs, es, fv_p, soon_p, rat_p)),
                            key=lambda g: g["key"])
    ```

  - Change the docstring's `graded:` sentence to "graded: board players with a model read, sorted by key."
  - Remove the `pitchers=True: no closest-to-helping rank ...` wording about the rank. Keep the tier/role sentence.
  - Add:

    ```python
    def load_fvplus(path):
        """{'H': {key: {'rank', 'tier'}}, 'P': {...}} from cache/fvplus_scores.csv; empty when absent."""
        out = {"H": {}, "P": {}}
        if not os.path.exists(path):
            return out
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                out[r["type"]][r["key"]] = {"rank": int(r["rank"]), "tier": int(r["tier"])}
        return out
    ```

- [ ] **Step 4:** `python -m pytest tests/test_shopping.py -q`. Expected: all pass.
- [ ] **Step 5: Commit:** `feat(fv-plus): current-board grades for FV+, FV+ score loader; drop the hitters' 50/50 ready rank`

---

### Task 2: Rank tiers and the production scorer

**Files:**
- Modify: `prospects-model/psmodel/fvplus.py`
- Modify: `prospects-model/tests/test_fvplus.py`
- Modify: `prospects-model/fetch_standings.py` (`SEASONS` through 2026)
- Create: `prospects-model/build_fvplus_scores.py`

- [ ] **Step 1: Add the test** (in `TestStatcastAndMap`, or a new class):

```python
    def test_rank_tiers(self):
        scores = [0.1 * i for i in range(20)]            # 20 players, best last
        ranks, tiers = F.rank_tiers(scores)
        self.assertEqual(ranks[-1], 1)
        self.assertEqual(ranks[0], 20)
        self.assertEqual(tiers[-1], 5)                   # top 5% of 20 = the best one
        self.assertEqual(tiers[-2], 10)
        self.assertEqual(sum(1 for t in tiers if t), 5)  # top 25%
```

- [ ] **Step 2:** `python -m pytest tests/test_fvplus.py -q`. Expected: 1 failure.

- [ ] **Step 3: Add to `fvplus.py`:**

```python
def rank_tiers(scores):
    """(rank 1 = best, tier 5/10/25 for the top 5%/10%/25% else 0) for a list of scores."""
    s = np.asarray(scores, dtype=float)
    rank = np.empty(len(s), dtype=int)
    rank[np.argsort(-s, kind="stable")] = np.arange(1, len(s) + 1)
    tiers = [5 if p > 0.95 else 10 if p > 0.90 else 25 if p > 0.75 else 0 for p in C.pct(s)]
    return [int(r) for r in rank], tiers
```

- [ ] **Step 4:** Run the tests; expected pass.
- [ ] **Step 5:** In `fetch_standings.py`, set `SEASONS = [s for s in range(2016, 2027) if s != 2020]`. Run `python fetch_standings.py`. Expected: a 2026 line (one new request; the regular season ended before today, 2026-09-30) and `standings OK`.
- [ ] **Step 6: Write `build_fvplus_scores.py`:**

```python
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
```

- [ ] **Step 7: Run** `python build_fvplus_scores.py`. Sanity-check:
  - the scored counts should be close to the board-with-model counts (426 hitters / 447 pitchers);
  - the top 15 should be near-ready players: high levels, reasonable FV;
  - no crash on an unknown org.
- [ ] **Step 8: Commit:** `feat(fv-plus): score the current board with the adopted FV+ soon models`

---

### Task 3: Shopping-list JSON, audit, chain

**Files:**
- Modify: `prospects-model/build_shopping_list.py`
- Modify: `prospects-model/audit_pipeline.py:217-218`
- Modify: `prospects-model/rerun_chain.py` (`STEPS`)

- [ ] **Step 1: `build_shopping_list.py`.**
  - Add `FVP = os.path.join(CACHE, "fvplus_scores.csv")`.
  - In `main()`, after the pitcher build: `fvp = S.load_fvplus(FVP)`.
  - Add `"fvplus": fvp` to `out`.
  - Replace the "closest to helping, top 10" print with:

    ```python
    print(f"FV+ soon reads: {len(fvp['H'])} hitters, {len(fvp['P'])} pitchers"
          + ("" if fvp["H"] else "  (cache/fvplus_scores.csv missing -- run build_fvplus_scores.py)"))
    print("graded, first 10 by key:\n  " + "\n  ".join(f"{g['key']}  ~{g['odds']}%  {g['take']}" for g in graded[:10]))
    ```

  - In the docstring, mention running `build_fvplus_scores.py` first.
- [ ] **Step 2: `audit_pipeline.py`.** Replace the "ready ranks run 1..n" check with:

```python
    for typ, pitchers in (("H", False), ("P", True)):
        fv = (pm.get("fvplus") or {}).get(typ, {})
        keys = {e["fg_id"] for e in S.load_current_board(os.path.join(DATA, "prospects.csv"), pitchers=pitchers)}
        a.check(f"shopping list: FV+ {typ} ranks run 1..n over board keys",
                sorted(v["rank"] for v in fv.values()) == list(range(1, len(fv) + 1)) and set(fv) <= keys,
                f"{len(fv)} reads")
```

- [ ] **Step 3: `rerun_chain.py`.** Insert `("fvplus scores", ["build_fvplus_scores.py"]),` before `("shopping list", ...)`.
- [ ] **Step 4: Run** `python build_shopping_list.py`, then `python audit_pipeline.py`. Expected: 0 FAILs. Then `python -m pytest -q`: all pass.
- [ ] **Step 5: Commit** (includes `data/prospect_model.json`): `feat(fv-plus): FV+ soon block in the shopping-list data; audit and chain updated`

---

### Task 4: The page

**Files:** Modify `prospects.html`.

- [ ] **Step 1: Header.** After the `thOdds` `<th>`, add:

```html
            <th data-col="fvp" id="thFvp" title="FV+ soon: FanGraphs FV adjusted for this 4x4 league and for how close a player is. Rank among board players of the same type (1 = most likely to help within 2 years). Not a percentage.">FV+ soon</th>
```

- [ ] **Step 2: Script.**
  - `var lens` comment: `'ready' = FV+ soon`.
  - Add `var fvpByKey = { H: {}, P: {} };` beside `modelInfo`.
  - `setLens`: replace `if (l === 'ready') { setType('H'); ...` with:

    ```js
      if (l === 'ready') { if (typeFilter !== 'P') setType('H'); sortCol = 'ready'; sortDir = 1; }
    ```

  - Add a formatter after `fmtRead`:

    ```js
    function fmtFvp(f) {
      if (!f) return '—';
      return '#' + f.rank + (f.tier ? ' · Top ' + f.tier + '%' : '');
    }
    ```

  - `sortValue`:

    ```js
        case 'ready':   return row.fvp ? row.fvp.rank : 1e9;
        case 'fvp':     return row.fvp ? -row.fvp.rank : -1e9;
    ```

  - `render` filter: `if (lens === 'ready' && !row_fvp)`, i.e. replace the `ready_rank` line with `if (lens === 'ready' && !r.fvp) return false;`.
  - Notes: move the `lens === 'ready'` branch ahead of the `typeFilter === 'P'` branch, and make it:

    ```js
      } else if (lens === 'ready') {
        var noRead = allRows.filter(function(r) { return inferType(r.prospect.pos) === typeFilter && !r.fvp; }).length;
        note = 'Ranked by FV+ soon: FanGraphs\' FV adjusted for this 4x4 league and for how close a player is ' +
               '(level, age, parent club\'s record; walks, game power and position for hitters; ground balls for ' +
               'pitchers). It beat FV alone in 4 of 4 test years (2021–24) for hitters and pitchers; the 2025 ' +
               'class confirms it after 2027. Outfielders count as non-premium unless the preseason list shows CF. ' +
               noRead + ' board ' + (typeFilter === 'P' ? 'pitchers' : 'hitters') + ' have no FV+ read.';
    ```

  - Row cells: after the `fmtRead` cell, add `tr.appendChild(td(row.ungraded ? '—' : fmtFvp(row.fvp), row.fvp ? '' : 'dim'));`
  - Type buttons: `if (lens === 'ready' && t !== 'H' && t !== 'P') {` (was `t !== 'H'`).
  - Model fetch: after `modelInfo = {...}`, add `fvpByKey = mj.fvplus || { H: {}, P: {} };`.
  - `allRows` map: add `fvp: (isP ? fvpByKey.P : fvpByKey.H)[pr.rawName + '|' + pr.org] || null,`.
- [ ] **Step 3: Verify in the browser** (preview `static-node`, port 8010).
  - Best lens default = FV order.
  - Closest to helping on H: sorted #1, #2, #3..., the note is shown, and the row count equals the FV+ reads.
  - Clicking P keeps the ready lens with pitcher ranks.
  - The All type resets to best.
  - The FV+ column sorts; U/UP show "—".
  - No console errors.
  - Take a screenshot.
- [ ] **Step 4: Commit:** `feat(fv-plus): shopping list -- FV+ soon column and a closest-to-helping lens for hitters and pitchers`

---

### Task 5: Record

- [ ] Add a "Phase 3 result" line to the spec: the counts, the top-5 sanity check, and the display refinement.
- [ ] Update memory, including the refresh workflow (`build_fvplus_scores.py` before `build_shopping_list.py`).
- [ ] Commit. Remind the user to push.
