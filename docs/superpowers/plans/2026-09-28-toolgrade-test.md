# Tool-Grade Test (Pre-Registered): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the one pre-registered comparison: do FanGraphs' bat grades (Hit future + Game Power future) rank graded hitters better than FV for this league's fantasy value?

**Architecture:**
- `consensus.load_board` also parses the two future tool grades.
- `toolgrade_test.py` reuses plan C's population and helpers (`consensus_gate.py`: `one_per_player`, `people`, `line`, `TESTS`, `INFO`) and plan C's adoption rule.
- No model fit is needed: both rankings are FanGraphs' own.

**Tech Stack:** Python 3; numpy; existing `psmodel` modules; `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-28-post-build-queue-design.md`, part C. **The rules there are fixed. Don't add formulas, weightings or extra comparisons, before or after the run.**

---

## Ground rules

- **Order:** run after the pipeline audit, and after any bug fix it triggered.
- **Where to run:** from `prospects-model/`. Tests: `python -m unittest discover -s tests`. Note the count before starting; this plan adds 1 test.
- **No network.** FanGraphs data stays in the gitignored `cache/fv/`, never committed.
- **Commits:** commit locally. **Never push, fetch or pull.**

---

### Task 1: Parse the future tool grades

**Files:**
- Modify: `prospects-model/psmodel/consensus.py` (`load_board`, plus a new `_future` helper)
- Test: `prospects-model/tests/test_consensus.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_consensus.py`, inside `class TestBoard` (after `test_fv_order`):

```python
    def test_load_board_parses_future_bat_grades(self):
        r = dict.fromkeys(HEADER, "")
        r.update({"Name": "Bat Guy", "Age": "21", "FV": "50", "playerId": "sa9",
                  "Hit": "30 / 55", "Game Pwr": "20 / 45+"})
        blank = dict(r, Name="No Tools", playerId="sa10", Hit="", **{"Game Pwr": ""})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=HEADER)
                w.writeheader()
                w.writerows([r, blank])
            board = C.load_board(path)
        self.assertEqual((board[0]["hit_fut"], board[0]["pwr_fut"]), (55.0, 47.5))
        self.assertEqual((board[1]["hit_fut"], board[1]["pwr_fut"]), (None, None))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_consensus -v`. Expected: the new test fails with `KeyError: 'hit_fut'`.

- [ ] **Step 3: Implement**

In `psmodel/consensus.py`, add below `_num`:

```python
def _future(text):
    """A 'present / future' tool grade ('30 / 55') -> the future grade; blank -> None."""
    return parse_fv((text or "").split("/")[-1])
```

In `load_board`, replace

```python
                        "top100": _rank(r.get("Top 100")), "org_rk": _rank(r.get("Org Rk"))})
```
with
```python
                        "top100": _rank(r.get("Top 100")), "org_rk": _rank(r.get("Org Rk")),
                        "hit_fut": _future(r.get("Hit")), "pwr_fut": _future(r.get("Game Pwr"))})
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_consensus -v` (all OK), then `python -m unittest discover -s tests`. Expected: all pass (the earlier count + 1), 3 skipped.

- [ ] **Step 5: Commit**

```bash
git ls-files cache
git add psmodel/consensus.py tests/test_consensus.py
git commit -m "feat(3c-C): parse future Hit and Game Power grades from Board exports"
```

### Task 2: The runner

**Files:**
- Create: `prospects-model/toolgrade_test.py`

- [ ] **Step 1: Create the file**

```python
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
```

- [ ] **Step 2: Static check.** Run `python -c "import toolgrade_test"`. Expected: no error.

- [ ] **Step 3: Commit**

```bash
git ls-files cache
git add toolgrade_test.py
git commit -m "feat(3c-C): pre-registered tool-grade test runner (bat grades vs FV)"
```

### Task 3: Run once, then hand to Opus

- [ ] **Step 1:** Run `python toolgrade_test.py`, **once**.
  - If it crashes, fix only mechanics (a key name or a typo) and rerun.
  - Never change the formula, population, classes or rule.

  Expected: the snapshot lines, then a RATING block and a SOON block with one line per class and a VERDICT each.

- [ ] **Step 2:** Run `git status --short; git ls-files cache`. Expected: no `cache/` paths.

- [ ] **Step 3: Hand to Opus.** Tell the user both verdicts and ask them to switch to Opus. Opus records the result in the post-build-queue spec and applies the consequence set in advance:
  - **Rating passes:** an optional, provisional "Bat grade" sort in the shopping list's Best prospects lens, which is its own small plan.
  - **Soon passes:** nothing now.
  - **Neither passes:** closed.
