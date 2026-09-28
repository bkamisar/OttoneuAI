# 3c Pipeline Plumbing Audit: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check, with scripted checks over the real data, that the 3c hitter pipeline computes what we think it does.

**Architecture:** One read-only script, `prospects-model/audit_pipeline.py`. It loads the same inputs the model runners load, runs six sections of checks, and writes `cache/audit_report.txt`. It fixes nothing: failures go to Opus.

**Tech Stack:** Python 3 stdlib + numpy; existing `psmodel` modules.

**Spec:** `docs/superpowers/specs/2026-09-28-post-build-queue-design.md`, part A.

---

## Ground rules

- **Order:** run AFTER the shopping-list plan (section 5 checks its output).
- **Where to run:** from `prospects-model/`. Before this plan: **200 pass, 3 skipped**.
- **No network.** No commits of anything under `cache/`.
- **Commits:** commit locally. **Never push, fetch or pull.**
- **A FAIL is information, not an instruction.**
  - Do not "fix" the audit to make it pass, and do not change model code on a cheaper model.
  - Stop after the run and hand to Opus.
  - A FAIL may be the check's own mistake. Opus decides which it is.

---

### Task 1: Write the audit script

**Files:**
- Create: `prospects-model/audit_pipeline.py`

- [ ] **Step 1: Create the file**

```python
"""Plumbing audit of the 3c hitter pipeline: does it compute what we think?

Scripted checks over the real cached data. Each check prints PASS or FAIL with
detail; nothing is fixed here. Every FAIL goes to Opus. A real bug gets fixed and
the pipeline rerun (model3c_base.py -> model3c_final.py -> consensus_gate.py ->
build_shopping_list.py): fixing a bug is legitimate, unlike re-mining seen seasons
for a better-looking model.

Usage:  python audit_pipeline.py
Reads only cached data. Writes cache/audit_report.txt (gitignored).
"""
import csv
import json
import os
import random
import statistics
import warnings

from psmodel import asof, cohorts, dataset, milb, statsapi
from psmodel import features as F
from psmodel import walkforward as W

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
DATA = os.path.join(os.path.dirname(HERE), "data")
REPORT = os.path.join(CACHE, "audit_report.txt")
SAMPLE = 60
TOL = 1e-6
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


class Audit:
    def __init__(self):
        self.lines, self.fails = [], 0

    def section(self, title):
        self.lines += ["", title]

    def check(self, name, ok, detail=""):
        self.lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
        self.fails += 0 if ok else 1

    def info(self, text):
        self.lines.append(f"         {text}")


def continuous_keys():
    return [k for g in cohorts.GROUPS.values() for k in g if k not in cohorts.BINARY]


def audit_raw(a, raw):
    a.section("1. Raw minor-league rows (cohorts.load_milb)")
    a.check("no 2020 rows", all(r["season"] != 2020 for r in raw))
    a.check("levels are 11-14 only", {r["sport_id"] for r in raw} <= set(cohorts.LEVELS))
    keys = [(r["player_id"], r["season"], r["sport_id"]) for r in raw]
    a.check("one row per player-season-level", len(keys) == len(set(keys)),
            f"{len(keys) - len(set(keys))} duplicates")
    a.check("no Mexican League rows", not any(r.get("league") in milb.MEX_LEAGUES for r in raw))
    bad = [r for r in raw if not (r["ab"] <= r["pa"] and r["h"] <= r["ab"] and r["hr"] <= r["h"]
                                  and r["so"] <= r["pa"] and r["bb"] <= r["pa"])]
    a.check("counting stats consistent (AB<=PA, H<=AB, HR<=H, SO/BB<=PA)", not bad, f"{len(bad)} rows")
    sw = [r for r in raw if r.get("swings") is not None]
    bad = [r for r in sw if not (r["whiffs"] <= r["swings"] <= r["np"])]
    a.check("swing data consistent (whiffs <= swings <= pitches)", not bad,
            f"{len(bad)} of {len(sw)} rows" + (f", e.g. {bad[0]['name']} {bad[0]['season']}" if bad else ""))
    zero = [r for r in sw if r["swings"] >= 100 and r["whiffs"] == 0]
    a.check("no zero-whiff rows with 100+ swings (a sign of missing advanced data)", not zero,
            f"{len(zero)} rows")
    for s in sorted({r["season"] for r in raw}):
        rs = [r for r in raw if r["season"] == s and r["pa"] >= cohorts.MIN_PA]
        cov = sum(1 for r in rs if r.get("swings")) / max(len(rs), 1)
        a.info(f"{s}: {len(rs)} rows with 150+ PA, swing data on {cov:.0%}")


def audit_rows(a, raw, rows, pa_hist):
    a.section("2. Model rows (cohorts.build_rows)")
    raw_by = {(r["player_id"], r["season"], r["sport_id"]): r for r in raw}
    src = [raw_by.get((r["player_id"], r["season"], r["sport_id"])) for r in rows]
    a.check("every model row traces to one raw row", all(s is not None for s in src))
    a.check("every model row has 150+ PA at the level", all(s["pa"] >= cohorts.MIN_PA for s in src if s))
    est = [r for r in rows
           if cohorts.prior_mlb_pa(pa_hist, r["player_id"], r["season"]) >= cohorts.ESTABLISHED_PA]
    a.check("no established MLB hitters (300+ prior MLB PA)", not est, f"{len(est)} rows")
    keys = [(r["player_id"], r["season"], r["sport_id"]) for r in rows]
    a.check("one model row per player-season-level", len(keys) == len(set(keys)))
    a.check("level flags match the level", all(
        r["f"]["is_aaa"] == (1.0 if r["sport_id"] == 11 else 0.0)
        and r["f"]["is_aa"] == (1.0 if r["sport_id"] == 12 else 0.0)
        and r["f"]["is_higha"] == (1.0 if r["sport_id"] == 13 else 0.0) for r in rows))
    a.check("2021's previous season is 2019", cohorts.previous_season(2021) == 2019)
    seen = {}
    for r in raw:
        seen.setdefault((r["player_id"], r["season"]), set()).add(r["sport_id"])
    bad_rep = [r for r in rows if r["f"]["repeat_level"] != (
        1.0 if r["sport_id"] in seen.get((r["player_id"], cohorts.previous_season(r["season"])), ()) else 0.0)]
    bad_multi = [r for r in rows if r["f"]["multi_level"] != (
        1.0 if len(seen[(r["player_id"], r["season"])]) > 1 else 0.0)]
    a.check("repeat-level and multi-level flags recompute", not bad_rep and not bad_multi,
            f"{len(bad_rep)} / {len(bad_multi)} rows")

    groups = {}
    for r, s in zip(rows, src):
        if s is not None:
            groups.setdefault((r["sport_id"], r["season"]), []).append((r, s))
    worst, where = 0.0, ""
    for g, members in groups.items():
        raw_f = [F.hitter_features(s) for _, s in members]
        for k in continuous_keys():
            vals = [f[k] for f in raw_f if f[k] is not None]
            mu = statistics.fmean(vals) if vals else 0.0
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            for (r, _), f in zip(members, raw_f):
                want = None if f[k] is None else ((f[k] - mu) / sd if sd else 0.0)
                got = r["f"].get(k)
                diff = float("inf") if (want is None) != (got is None) else (
                    0.0 if want is None else abs(want - got))
                if diff > worst:
                    worst, where = diff, f"{k} in level {g[0]} {g[1]} ({r['name']})"
    a.check("every feature = its raw stat z-scored within level-season (all rows re-derived)",
            worst < TOL, f"max diff {worst:.2e}" + (f" at {where}" if worst >= TOL else ""))


def audit_labels(a, labels):
    a.section("3. MLB labels (labels.csv)")
    dup = sum(len(v) - len({r["season"] for r in v}) for v in labels.values())
    a.check("one label per player-type-season", dup == 0, f"{dup} duplicates")
    hitters = [(pid, r) for (pid, typ), recs in labels.items() if typ == "H" for r in recs]
    by = {}
    for pid, r in hitters:
        by.setdefault(r["season"], []).append(r)
    bad = []
    for s, recs in by.items():
        ordered = sorted(recs, key=lambda r: r["rank"])
        if ([r["rank"] for r in ordered] != list(range(1, len(recs) + 1))
                or any(x["value"] < y["value"] for x, y in zip(ordered, ordered[1:]))):
            bad.append(s)
    a.check("hitter ranks run 1..n per season, best value first", not bad, f"bad seasons {bad}")
    for v in (2019, 2022, cohorts.CURRENT_SEASON):
        cut = {k: [r for r in recs if r["season"] <= v] for k, recs in labels.items()}
        a.check(f"rank-value curve at {v} uses no later season", asof.ref_curve(labels, v) == asof.ref_curve(cut, v))
    no2020 = {k: [r for r in recs if r["season"] != 2020] for k, recs in labels.items()}
    a.check("2020 is left out of the rank-value curve", asof.ref_curve(labels, 2022) == asof.ref_curve(no2020, 2022))

    sample = random.Random(0).sample(hitters, SAMPLE)
    pa_by = {}
    for s in {r["season"] for _, r in sample}:
        for row in statsapi.season_stats(s, "hitting", statsapi.MLB):
            pa_by[(row["player_id"], s)] = pa_by.get((row["player_id"], s), 0) + row["pa"]
    mism = [(pid, r["season"], r["pa"], pa_by.get((pid, r["season"]))) for pid, r in sample
            if pa_by.get((pid, r["season"])) != r["pa"]]
    a.check(f"label PA matches StatsAPI MLB PA ({SAMPLE} random hitter-seasons)", not mism,
            f"{len(mism)} mismatches, e.g. {mism[:3]}")
    for s in (2019, 2023, cohorts.CURRENT_SEASON):
        names = {row["player_id"]: row["name"] for row in statsapi.season_stats(s, "hitting", statsapi.MLB)}
        top = sorted((r["rank"], pid) for pid, r in hitters if r["season"] == s)[:5]
        a.info(f"{s} top 5 hitter seasons (eyeball): " + ", ".join(names.get(pid, str(pid)) for _, pid in top))


def audit_asof(a, rows, labels, dec):
    a.section("4. As-of discipline (walkforward.frames)")
    cases = ([("rating", v, False) for v in W.RATING_VANTAGES]
             + [("soon", v, False) for v in W.SOON_VANTAGES] + [("soon", 2024, True)])
    for t, v, unseal in cases:
        ctx = asof.ref_curve(labels, v)
        known = asof.rating_known if t == "rating" else asof.soon_known
        train, test = W.frames(rows, t, v, ctx, dec[t]["keys"], unseal=unseal)
        leak = [r for r in train
                if not known(r["season"], v)
                or W._y(dict(r, mlb=[m for m in r["mlb"] if m["season"] <= v]), t, ctx) != r["y"]]
        overlap = {r["player_id"] for r in train} & {r["player_id"] for r in test}
        a.check(f"{t} {v}: training answers use only seasons <= {v}; no test player in training",
                not leak and not overlap,
                f"{len(train)} train rows, {len(leak)} leaking, {len(overlap)} overlapping")
    v = cohorts.CURRENT_SEASON
    for t in ("rating", "soon"):
        known = asof.rating_known if t == "rating" else asof.soon_known
        train, _ = W.frames(rows, t, v, asof.ref_curve(labels, v), dec[t]["keys"], unseal=True, isolate=False)
        a.check(f"production {t}: trains only on cohorts whose answers are known by {v}",
                all(known(r["season"], v) for r in train), f"{len(train)} rows")
    try:
        W.frames(rows, "soon", 2024, asof.ref_curve(labels, 2024), dec["soon"]["keys"])
        sealed = False
    except ValueError:
        sealed = True
    a.check("2024 stays sealed without unseal=True", sealed)


def audit_outputs(a, rows, pa_hist):
    a.section("5. Outputs")
    with open(os.path.join(CACHE, "hitter_ratings.csv"), encoding="utf-8") as fh:
        rat = list(csv.DictReader(fh))
    ids = [int(r["player_id"]) for r in rat]
    a.check("hitter_ratings.csv: one row per player", len(ids) == len(set(ids)), f"{len(rat)} rows")
    srt = sorted(rat, key=lambda r: -float(r["rating_sgp"]))
    a.check("rating percentile falls as the rating falls",
            all(float(x["rating_percentile"]) >= float(y["rating_percentile"]) for x, y in zip(srt, srt[1:])))
    a.check("2-year odds are probabilities", all(0.0 <= float(r["p_useful_within_2"]) <= 1.0 for r in rat))
    now = {r["player_id"] for r in rows if r["season"] == cohorts.CURRENT_SEASON}
    a.check(f"every rated hitter has a {cohorts.CURRENT_SEASON} model row", set(ids) <= now,
            f"{len(set(ids) - now)} without")
    est = [i for i in ids if cohorts.prior_mlb_pa(pa_hist, i, cohorts.CURRENT_SEASON) >= cohorts.ESTABLISHED_PA]
    a.check("no established MLB hitters rated", not est, f"{len(est)}")

    path = os.path.join(DATA, "prospect_model.json")
    if not os.path.exists(path):
        a.info("data/prospect_model.json not built yet -- shopping-list checks skipped")
        return
    from psmodel import shopping as S
    with open(path, encoding="utf-8") as fh:
        pm = json.load(fh)
    board = {e["fg_id"] for e in S.load_current_board(os.path.join(DATA, "prospects.csv"))}
    gk = [g["key"] for g in pm["graded"]]
    a.check("shopping list: every graded key is a board hitter, once", len(gk) == len(set(gk)) and set(gk) <= board)
    a.check("shopping list: ready ranks run 1..n",
            sorted(g["ready_rank"] for g in pm["graded"]) == list(range(1, len(gk) + 1)))
    gid = {g["player_id"] for g in pm["graded"]}
    uid = {u["player_id"] for u in pm["ungraded"]}
    a.check("shopping list: graded and ungraded are disjoint and cover every rated hitter",
            not (gid & uid) and (gid | uid) == set(ids))


def audit_tests(a):
    a.section("6. Test coverage (information)")
    mods = sorted(f[:-3] for f in os.listdir(os.path.join(HERE, "psmodel"))
                  if f.endswith(".py") and f != "__init__.py")
    tests = set(os.listdir(os.path.join(HERE, "tests")))
    missing = [m for m in mods if f"test_{m}.py" not in tests]
    a.info("psmodel modules without a test file: " + (", ".join(missing) or "none"))


def main():
    a = Audit()
    labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))
    asof.attach_ranks(labels)
    pa_hist = cohorts.mlb_pa_history()
    raw = cohorts.load_milb()
    rows = cohorts.build_rows(raw, pa_hist, {pid: r for (pid, typ), r in labels.items() if typ == "H"})
    with open(os.path.join(CACHE, "model3c_final.json"), encoding="utf-8") as fh:
        dec = json.load(fh)
    audit_raw(a, raw)
    audit_rows(a, raw, rows, pa_hist)
    audit_labels(a, labels)
    audit_asof(a, rows, labels, dec)
    audit_outputs(a, rows, pa_hist)
    audit_tests(a)
    text = "\n".join([f"3c PIPELINE PLUMBING AUDIT: {a.fails} FAIL(s)"] + a.lines)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Static check**

Run: `python -c "import audit_pipeline"`. Expected: no output, no error.

- [ ] **Step 3: Commit**

```bash
git ls-files cache
git add audit_pipeline.py
git commit -m "feat(audit): scripted plumbing audit of the 3c hitter pipeline"
```

### Task 2: Run it and hand to Opus

- [ ] **Step 1: Run**

Run: `python audit_pipeline.py`. It takes a few minutes; it builds the same rows the model does.

- [ ] **Step 2: If it crashes,** fix only the audit script's own mechanics (a wrong key name or a typo), never the checks' logic or thresholds. Rerun, and commit the fix as `fix(audit): ...`.

- [ ] **Step 3: Stop and hand to Opus.** Tell the user the FAIL count and ask them to switch to Opus to review `cache/audit_report.txt`. Don't change model code, and don't rerun the model chain on a cheaper model.

Opus then decides, for each FAIL, whether it's a real bug or a wrong check:
- **Real bug:** fix it with a test, then rerun `model3c_base.py` → `model3c_final.py` → `consensus_gate.py` → `build_shopping_list.py`, and record what changed in the 3c spec.
- **Wrong check:** fix the audit.
