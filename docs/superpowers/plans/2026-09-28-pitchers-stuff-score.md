# Pitchers Plan P-C: The Stuff Score — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **GATE:** start only after P-B's parity gate PASSED and `build_pitch_tracking.py` wrote both tables (`cache/pitch_definitions.json` has `"passed": true`).

**Goal:**
- Learn on MLB pitchers (Savant 2015–2025, with outcomes through 2026) what pitch tracking is worth.
- Translate AAA readings onto the MLB scale.
- Check whether the resulting stuff score ranks real AAA prospects' later MLB value above chance.

This is the pitcher counterpart of hitters' step 1.

**Architecture:**
- `psmodel/stuff.py` holds the pure pieces: the fixed-workload target, the useful line, the rows, the outcomes and the AAA→MLB offsets. It reuses `step1`'s table loader, `complete`, `translate` and `spearman_ci`.
- `stuff_run.py` mirrors `step1_run.py` and reuses its helpers (`mean_oof_rho`, `adoption_line`, `SEEDS`).

**Spec:** `docs/superpowers/specs/2026-09-28-pitchers-design.md`, "Stuff layer design".

---

## Ground rules

- **Where to run:** from `prospects-model/`. Before this plan: **219 pass, 3 skipped**. P-B's review added the knuckleball test.
- **No network.** Every input is cached: MLB / AAA pitching stats, the P-B tables and `../data/standings.csv`.
- **`cache/` is never committed.**
- **Commits:** commit locally after each task. **Never push, fetch or pull.**
- **The gate verdict is final for this run.** Don't change groups, thresholds or the gate after seeing results. Hand to Opus.

---

### Task 0: Preflight

- [ ] Run `python -m unittest discover -s tests`. Expected: 219 pass, 3 skipped.
- [ ] Run `python -c "import json; print(json.load(open('cache/pitch_definitions.json'))['passed'])"`. Expected: `True`. Also run `ls cache/aaa_pitch_tracking.csv cache/mlb_pitch_tracking.csv ../data/standings.csv`.

### Task 1: The fixed-workload target (`psmodel/stuff.py`, part 1)

**Files:** Create `psmodel/stuff.py`; Test `tests/test_stuff.py`.

- [ ] **Step 1: Failing tests.** Create `tests/test_stuff.py`:

```python
import unittest

from psmodel import labels, stuff

REPL = {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711}
DEN = {"SO": 41.3, "ERA": 0.2184, "WHIP": 0.0312, "HR9": 0.0975}


def stat(pid=1, ip=60.0, so=70, bb=20, age=25):
    return {"player_id": pid, "sport_id": 1, "age": age, "ip": ip, "so": so, "bb": bb, "bf": int(ip * 4.2),
            "hr9": 1.0, "era": 3.5, "whip": 1.2, "np": int(ip * 16), "strikes": int(ip * 10)}


class TestTarget(unittest.TestCase):
    def test_value_is_the_rate_line_at_100_ip(self):
        want = labels.pitcher_sgp({"ip": 100.0, "so": 120.0, "era": 3.0, "whip": 1.1, "hr9": 1.0}, REPL, DEN, 1500.0)
        for ip in (50.0, 150.0):                  # same rates, any workload -> same value
            row = {"ip": ip, "so": 1.2 * ip, "era": 3.0, "whip": 1.1, "hr9": 1.0}
            self.assertAlmostEqual(stuff.value_at_workload(row, REPL, DEN, 1500.0), want)
        self.assertIsNone(stuff.value_at_workload({"ip": 24.0, "so": 30, "era": 3.0, "whip": 1.1, "hr9": 1.0},
                                                  REPL, DEN, 1500.0))

    def test_useful_line_is_the_median_120th_best(self):
        values = {i: {2020: (float(i), 50.0), 2021: (float(i) + 2, 50.0)} for i in range(1, 121)}
        self.assertEqual(stuff.useful_threshold(values), 2.0)          # 120th best: 1.0 and 3.0

    def test_season_values_skip_small_workloads(self):
        rows = [dict(stat(i, ip=100.0 + i), era=4.0, whip=1.3, hr9=1.2) for i in range(250)]
        rows.append(stat(999, ip=10.0))
        vals = stuff.season_values({2021: rows}, dict(DEN, HR=4.0, R=12.0, OBP=0.008, SLG=0.012))
        self.assertEqual(vals[0][2021][1], 100.0)
        self.assertNotIn(999, vals)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** Run `python -m unittest tests.test_stuff -v`. Expected: ERROR (`cannot import name 'stuff'`).

- [ ] **Step 3: Implement.** Create `psmodel/stuff.py`:

```python
"""Pitcher stuff score (P-C): what pitch tracking is worth, learned on MLB and
translated to AAA -- the pitcher counterpart of step1.py.

Target: the NEXT MLB season's line valued at a fixed WORKLOAD with the site's
SGP formula (labels.pitcher_sgp) -- strikeouts scaled to the workload, ERA / WHIP
/ HR9 as they were, replacement per season as in build_labels. Starters and
relievers are judged on the same scale; how many innings they get is the base
model's job (its role features).
Spec: docs/superpowers/specs/2026-09-28-pitchers-design.md, "Stuff layer design".
"""
import random

import numpy as np

from . import context, labels, pcohorts
from . import features as F

GROUPS = {
    "velocity": ["fb_speed"],
    "fastball_shape": ["fb_spin", "fb_ivb", "fb_hb"],
    "breaking": ["breaking_speed", "breaking_spin"],
    "whiff": ["whiff_percent"],
}
BOX = ["k", "bb"]
WORKLOAD = 100.0         # innings every pitcher's rate line is valued at
MIN_IP_NEXT = 25.0       # targets.MIN_IP, applied to the outcome season
MIN_PITCHES = 300        # tracked pitches in season t for a row's metrics to count
MIN_PITCH_PAIR = 150     # pitches at EACH level for a same-season translation pair
USEFUL_RANK = 120        # 12 teams x ~10 arms
LAST_OUTCOME_SEASON = 2026


def stuff_keys(groups=None):
    return [k for g in (GROUPS if groups is None else groups) for k in GROUPS[g]]


def value_at_workload(row, repl, den, avg_ip):
    """Site SGP of a pitcher's rate line over WORKLOAD innings; None under MIN_IP_NEXT."""
    ip = row.get("ip") or 0.0
    if ip < MIN_IP_NEXT:
        return None
    line = {"ip": WORKLOAD, "so": row["so"] * WORKLOAD / ip,
            "era": row["era"], "whip": row["whip"], "hr9": row["hr9"]}
    return labels.pitcher_sgp(line, repl, den, avg_ip)


def season_values(stats_by_season, den):
    """{player_id: {season: (value at WORKLOAD, ip)}} from StatsAPI MLB pitching rows."""
    _, avg_ip = context.league_averages()
    out = {}
    for s, rows in stats_by_season.items():
        repl = context.pitcher_replacement(rows, context.season_fraction(s))
        for r in rows:
            v = value_at_workload(r, repl, den, avg_ip)
            if v is not None:
                out.setdefault(r["player_id"], {})[s] = (v, r["ip"])
    return out


def useful_threshold(values):
    """Median across seasons of the USEFUL_RANK-th best value at WORKLOAD."""
    by = {}
    for seasons in values.values():
        for s, (v, _) in seasons.items():
            by.setdefault(s, []).append(v)
    return float(np.median([sorted(vs, reverse=True)[USEFUL_RANK - 1]
                            for vs in by.values() if len(vs) >= USEFUL_RANK]))
```

(`random`, `pcohorts` and `F` are used in Task 2; leave the imports in.)

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **222 pass**, 3 skipped.
- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/stuff.py tests/test_stuff.py
git commit -m "feat(pitchers): stuff-score target -- next-season line valued at 100 IP with the site's SGP"
```

### Task 2: Rows, outcomes and offsets (`psmodel/stuff.py`, part 2)

- [ ] **Step 1: Failing tests.** Add above `if __name__ == "__main__":` in `tests/test_stuff.py`:

```python
FULL = {"pitches": 400, "fb_speed": 95.0, "fb_spin": 2300.0, "fb_ivb": 16.0, "fb_hb": 8.0,
        "breaking_speed": 85.0, "breaking_spin": 2500.0, "whiff_percent": 28.0}


class TestRows(unittest.TestCase):
    def test_mlb_rows_need_tracked_volume_and_a_valued_next_season(self):
        table = {(1, 2020): FULL, (2, 2020): dict(FULL, pitches=200), (3, 2020): FULL}
        values = {1: {2021: (1.5, 60.0)}, 2: {2021: (1.0, 60.0)}}
        stats = {(p, 2020): stat(p) for p in (1, 2, 3)}
        rows = stuff.mlb_rows(table, values, stats, threshold=1.0)
        self.assertEqual([(r["player_id"], r["target"], r["weight"], r["useful"]) for r in rows],
                         [(1, 1.5, 60.0, True)])
        self.assertEqual((rows[0]["f"]["fb_speed"], rows[0]["f"]["age"]), (95.0, 25))
        self.assertAlmostEqual(rows[0]["f"]["k"], 70 / 252)

    def test_later_outcome_is_the_best_valued_season_after(self):
        values = {1: {2020: (9.0, 90.0), 2021: (0.5, 30.0), 2023: (1.2, 80.0), 2027: (5.0, 100.0)}}
        self.assertEqual(stuff.later_outcome(values, 1, 2020), (True, 1.2))
        self.assertEqual(stuff.later_outcome(values, 2, 2020), (False, None))

    def test_aaa_rows_first_qualifying_season_prospects_only(self):
        table = {(1, 2022): FULL, (1, 2023): FULL, (2, 2022): dict(FULL, pitches=100), (3, 2023): FULL}
        stats = {k: stat(k[0]) for k in table}
        rows = stuff.aaa_rows(table, stats, {1: {2024: (2.0, 70.0)}}, (2022, 2023), 1.0, {3: {2021: 150.0}})
        self.assertEqual([(r["player_id"], r["season"], r["arrived"], r["target"], r["useful"]) for r in rows],
                         [(1, 2022, True, 2.0, True)])

    def test_translation_is_a_pitch_weighted_same_season_offset(self):
        aaa = {(1, 2023): {"pitches": 200, "fb_speed": 94.0}, (2, 2023): {"pitches": 400, "fb_speed": 92.0},
               (3, 2023): {"pitches": 100, "fb_speed": 90.0}}
        mlb = {(1, 2023): {"pitches": 300, "fb_speed": 95.0}, (2, 2023): {"pitches": 200, "fb_speed": 93.5},
               (3, 2023): {"pitches": 500, "fb_speed": 99.0}}
        t = stuff.fit_translation(aaa, mlb, ["fb_speed"])["fb_speed"]
        self.assertEqual(t["n"], 2)
        self.assertAlmostEqual(t["offset"], 1.25)
```

- [ ] **Step 2:** Run `python -m unittest tests.test_stuff -v`. Expected: the 4 new tests ERROR (`no attribute 'mlb_rows'` and similar).

- [ ] **Step 3: Implement.** Append to `psmodel/stuff.py`:

```python
def _features(metrics_row, stat_row):
    f = {k: metrics_row.get(k) for k in stuff_keys()}
    box = F.pitcher_features(stat_row)
    f.update({k: box[k] for k in BOX})
    f["age"] = stat_row.get("age")
    return f


def mlb_rows(table, values, stats, threshold):
    """One row per MLB pitcher with >= MIN_PITCHES tracked pitches in t and a valued
    season (25+ IP) in t+1. stats: {(player_id, season): StatsAPI pitcher row}."""
    rows = []
    for (pid, t), m in table.items():
        if (m.get("pitches") or 0) < MIN_PITCHES:
            continue
        nxt = values.get(pid, {}).get(t + 1)
        st = stats.get((pid, t))
        if nxt is None or st is None:
            continue
        rows.append({"player_id": pid, "season": t, "f": _features(m, st), "target": nxt[0],
                     "weight": float(nxt[1]), "useful": nxt[0] >= threshold})
    return rows


def later_outcome(values, pid, season):
    """(arrived, best value at WORKLOAD) over MLB seasons after `season` with 25+ IP."""
    vals = [v for s, (v, _) in values.get(pid, {}).items() if season < s <= LAST_OUTCOME_SEASON]
    return bool(vals), (max(vals) if vals else None)


def aaa_rows(table, stats, values, cohort_seasons, threshold, ip_history):
    """AAA pitcher-seasons with >= MIN_PITCHES tracked pitches in the cohort seasons,
    for pitchers not yet established in MLB, each pitcher's FIRST qualifying
    season only so nobody counts twice in the gate."""
    seen, rows = set(), []
    for pid, s in sorted(table, key=lambda k: (k[1], k[0])):
        m = table[(pid, s)]
        st = stats.get((pid, s))
        if (s not in cohort_seasons or pid in seen or (m.get("pitches") or 0) < MIN_PITCHES or st is None
                or pcohorts.prior_mlb_ip(ip_history, pid, s) >= pcohorts.ESTABLISHED_IP):
            continue
        seen.add(pid)
        arrived, best = later_outcome(values, pid, s)
        rows.append({"player_id": pid, "season": s, "f": _features(m, st), "arrived": arrived,
                     "target": best, "useful": best is not None and best >= threshold})
    return rows


def fit_translation(aaa, mlb, keys, min_pitches=MIN_PITCH_PAIR, n_boot=1000, seed=0):
    """Per-metric AAA->MLB flat offset from pitchers who threw at both levels in the
    SAME season, weighted by the smaller pitch count. The slope is reported, not
    applied (errors-in-variables; see step1.fit_translation)."""
    pairs = [p for p in aaa if p in mlb
             and (aaa[p].get("pitches") or 0) >= min_pitches and (mlb[p].get("pitches") or 0) >= min_pitches]
    rng = random.Random(seed)
    out = {}
    for k in keys:
        pts = [(aaa[p][k], mlb[p][k], min(aaa[p]["pitches"], mlb[p]["pitches"])) for p in pairs
               if aaa[p].get(k) is not None and mlb[p].get(k) is not None]
        if not pts:
            out[k] = {"n": 0, "offset": None, "lo": None, "hi": None, "slope": None}
            continue
        a, b, w = (np.array(col, dtype=float) for col in zip(*pts))
        d = b - a
        boots = []
        for _ in range(n_boot):
            i = [rng.randrange(len(d)) for _ in range(len(d))]
            boots.append(float(np.average(d[i], weights=w[i])))
        slope = float(np.polyfit(a, b, 1, w=np.sqrt(w))[0]) if len(pts) >= 3 and np.ptp(a) > 0 else None
        out[k] = {"n": len(pts), "offset": float(np.average(d, weights=w)),
                  "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5)), "slope": slope}
    return out
```

- [ ] **Step 4:** Run `python -m unittest discover -s tests`. Expected: **226 pass**, 3 skipped.
- [ ] **Step 5: Commit**
```bash
git ls-files cache
git add psmodel/stuff.py tests/test_stuff.py
git commit -m "feat(pitchers): stuff-score rows, later outcomes and same-season AAA->MLB offsets"
```

### Task 3: The runner, run it, hand to Opus

**Files:** Create `stuff_run.py`.

- [ ] **Step 1: Create the file:**

```python
"""Pitchers P-C: the stuff score -- what pitch tracking is worth, learned on MLB
(Savant, seasons t = 2015-2025, outcomes through 2026), translated to AAA, and
checked on real prospects. The pitcher counterpart of step1_run.py.

Usage:  python stuff_run.py
Reads only cached data (build_pitch_tracking.py first). Writes cache/stuff_report.txt,
cache/aaa_pitch_translation.csv and cache/stuff_choice.json (gitignored).
"""
import csv
import json
import os
import statistics

import numpy as np

import step1_run as S1
from psmodel import context, evaluate, interactions, milb, pcohorts, statsapi, step1, stuff

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STANDINGS = os.path.join(os.path.dirname(HERE), "data", "standings.csv")
REPORT = os.path.join(CACHE, "stuff_report.txt")
TRANSLATION = os.path.join(CACHE, "aaa_pitch_translation.csv")
CHOICE = os.path.join(CACHE, "stuff_choice.json")
MLB_FIRST, MLB_LAST = 2015, 2025        # season t; outcomes run through 2026
GATE_COHORTS, LATE_COHORT = (2022, 2023), (2024,)


def finish(L, code):
    text = "\n".join(L)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return code


def main():
    L = []
    den = context.load_league_denominators(STANDINGS)
    by_season = {s: statsapi.season_stats(s, "pitching", statsapi.MLB)
                 for s in range(MLB_FIRST, stuff.LAST_OUTCOME_SEASON + 1)}
    stats = {}
    for s, rs in by_season.items():
        for r in rs:
            if (r["player_id"], s) in stats:
                raise SystemExit(f"duplicate StatsAPI MLB pitching row for {r['player_id']} in {s}")
            stats[(r["player_id"], s)] = r
    values = stuff.season_values(by_season, den)
    threshold = stuff.useful_threshold(values)
    mlb = step1.load_table(os.path.join(CACHE, "mlb_pitch_tracking.csv"))
    aaa = step1.load_table(os.path.join(CACHE, "aaa_pitch_tracking.csv"))

    all_keys = ["age"] + stuff.stuff_keys()
    box_base = ["age"] + stuff.BOX
    built = stuff.mlb_rows({k: v for k, v in mlb.items() if MLB_FIRST <= k[1] <= MLB_LAST}, values, stats, threshold)
    rows = step1.complete(built, all_keys + stuff.BOX)
    L += ["STUFF SCORE (P-C) -- what pitch tracking is worth (learned on MLB)",
          f"rows: {len(rows)} pitcher-seasons ({len(built) - len(rows)} dropped for a missing metric), "
          f"{len({r['player_id'] for r in rows})} pitchers, seasons t={MLB_FIRST}-{MLB_LAST}",
          f"target: next season's line valued at {stuff.WORKLOAD:g} IP (25+ IP next season); useful = >= "
          f"{threshold:.3f}, the typical {stuff.USEFUL_RANK}th-best ({sum(r['useful'] for r in rows)} useful rows)", ""]

    kind_rho = {kind: S1.mean_oof_rho(rows, all_keys, kind) for kind in evaluate.KINDS}
    kind = max(kind_rho, key=kind_rho.get)
    L += ["1. Model: " + ", ".join(f"{k} rho {v:.4f}" for k, v in kind_rho.items()) + f"  -> using {kind}", ""]

    L.append("2. Which groups earn their place (each vs age + all OTHER groups, 8/10 rule):")
    adopted = []
    for g in stuff.GROUPS:
        others = [k for h in stuff.GROUPS if h != g for k in stuff.GROUPS[h]]
        ok, line = S1.adoption_line(g, evaluate.compare(rows, ["age"] + others, stuff.GROUPS[g],
                                                        seeds=S1.SEEDS, kind=kind))
        L.append(line)
        if ok:
            adopted.append(g)
    final_keys = ["age"] + stuff.stuff_keys(adopted)
    L += [f"  adopted groups: {adopted or 'NONE'}", ""]
    if not adopted:
        L.append("GATE: FAIL -- no stuff group earns its place on MLB; the stuff layer stops here")
        return finish(L, 1)

    ok, line = S1.adoption_line("stuff on top of box", evaluate.compare(
        rows, box_base, stuff.stuff_keys(adopted), seeds=S1.SEEDS, kind=kind))
    L += ["3. Stuff vs box score (report only):",
          f"  box (age, K%, BB%) alone   rho {S1.mean_oof_rho(rows, box_base, kind):.4f}",
          f"  stuff + age alone          rho {S1.mean_oof_rho(rows, final_keys, kind):.4f}", line, ""]

    L.append("4. Robustness (adopted stuff vs age alone):")
    for name, keep in (("Hawk-Eye era only (t >= 2020)", lambda r: r["season"] >= 2020),
                       ("without 2020", lambda r: r["season"] not in (2019, 2020))):
        sub = [r for r in rows if keep(r)]
        L.append(S1.adoption_line(name, evaluate.compare(sub, ["age"], stuff.stuff_keys(adopted),
                                                         seeds=S1.SEEDS, kind=kind))[1])
    L.append("")

    L.append("5. Strongest interactions (gbm, unnormalized H in SGP; finding = top-10 in >=8/10 runs):")
    counts, strength = {}, {}
    for s in range(S1.SEEDS):
        folds = evaluate.assign_folds(rows, 5, s)
        train = [r for r, f in zip(rows, folds) if f != 0]
        m = evaluate.fit(train, final_keys, "gbm")
        idx = np.random.default_rng(s).choice(len(train), size=min(100, len(train)), replace=False)
        X = np.array([[train[i]["f"][k] for k in final_keys] for i in idx], dtype=float)
        for h, a, b in interactions.top_pairs(m, X, final_keys, n=10):
            counts[(a, b)] = counts.get((a, b), 0) + 1
            strength.setdefault((a, b), []).append(h)
    for (a, b), c in sorted(counts.items(), key=lambda t: (-t[1], -statistics.fmean(strength[t[0]])))[:10]:
        L.append(f"  {a} x {b}: strength {statistics.fmean(strength[(a, b)]):.3f}, top-10 in {c}/10 "
                 f"-> {'finding' if c >= 8 else 'hypothesis'}")
    L.append("")

    tkeys = stuff.stuff_keys()
    translation = stuff.fit_translation(aaa, mlb, tkeys)
    with open(TRANSLATION, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "n", "offset", "lo", "hi", "slope_reported_not_applied"])
        for k in tkeys:
            t = translation[k]
            w.writerow([k, t["n"], t["offset"], t["lo"], t["hi"], t["slope"]])
    L.append(f"6. AAA -> MLB translation (same-season two-level pitchers, >={stuff.MIN_PITCH_PAIR} pitches at each level):")
    for k in tkeys:
        t = translation[k]
        L.append(f"  {k:16} n={t['n']:3d}  " + (
            f"offset {t['offset']:+.3f} [{t['lo']:+.3f}, {t['hi']:+.3f}]  slope {t['slope'] or float('nan'):.2f}"
            if t["offset"] is not None else "no pairs"))
    L.append("")

    model, box_model = evaluate.fit(rows, final_keys, kind), evaluate.fit(rows, box_base, kind)
    with open(CHOICE, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "adopted": adopted, "score_keys": final_keys, "threshold": threshold,
                   "workload": stuff.WORKLOAD, "mlb_seasons": [MLB_FIRST, MLB_LAST]}, fh, indent=2)

    aaa_stats = {(r["player_id"], s): r for s in GATE_COHORTS + LATE_COHORT
                 for r in milb.season_rows(s, statsapi.AAA, "pitching")}
    ip_history = pcohorts.mlb_ip_history()
    gate_pass = False
    L.append(f"7. Prospect check -- AAA pitchers (not established, first qualifying season) scored on {final_keys}")
    for name, cohorts, gates in (("2022-23 (GATE)", GATE_COHORTS, True), ("2024 (report only)", LATE_COHORT, False)):
        pr = step1.complete(stuff.aaa_rows(aaa, aaa_stats, values, cohorts, threshold, ip_history),
                            final_keys + box_base)
        arr = [i for i, r in enumerate(pr) if r["arrived"]]
        L.append(f"  {name}: {len(pr)} AAA pitchers, {len(arr)} reached a 25+ IP MLB season, "
                 f"{sum(r['useful'] for r in pr)} reached the useful line")
        if len(arr) < 10:
            L.append("    too few arrivals to test")
            continue
        for r in pr:
            r["f"] = step1.translate(r["f"], translation)
        score = evaluate.predict(model, pr, final_keys)
        box = evaluate.predict(box_model, pr, box_base)
        kpct = np.array([r["f"]["k"] for r in pr])
        outcome = [pr[i]["target"] for i in arr]
        for label, sc in (("stuff score", score), ("box-score model", box), ("AAA K%", kpct)):
            rho, lo, hi = step1.spearman_ci(sc[arr], outcome)
            L.append(f"    {label:16} Spearman vs later MLB value {rho:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            if gates and label == "stuff score":
                gate_pass = lo > 0
        order = np.argsort(-score)
        for q, chunk in enumerate(np.array_split(order, 5), 1):
            L.append(f"    score quintile {q}: arrived {np.mean([pr[i]['arrived'] for i in chunk]):.2f}, "
                     f"useful {np.mean([pr[i]['useful'] for i in chunk]):.2f}")
    L += ["", "GATE: " + ("PASS -- the stuff score ranks later MLB value above chance; the pitcher final plan "
                          "may test it as a layer" if gate_pass else
                          "FAIL -- stop; the stuff layer is not handed to the pitcher model")]
    return finish(L, 0 if gate_pass else 1)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2:** Run `python -c "import stuff_run"` (no error). Commit:
```bash
git ls-files cache
git add stuff_run.py
git commit -m "feat(pitchers): stuff-score runner -- MLB learning, AAA translation, prospect gate"
```

- [ ] **Step 3: Run** `python stuff_run.py`. It takes several minutes (10 seeds × several comparisons).
  Sanity checks (report, don't patch):
  - Rows: several thousand MLB pitcher-seasons, with few dropped for missing metrics. If many were dropped, report which metric is missing.
  - The useful line is positive.
  - The velocity group is almost certainly adopted. If it isn't, report that as surprising.
  - The gate cohort has 50+ arrivals.

- [ ] **Step 4:** Run `git status --short; git ls-files cache`. Expected: no `cache/` paths.

- [ ] **Step 5: Hand to Opus.** Tell the user the GATE line and the adopted groups, and ask them to switch to Opus. Opus reviews:
  - adoption;
  - stuff vs box;
  - the Hawk-Eye-only robustness check;
  - the translation offsets.

  Opus then records a "P-C result" in the pitcher spec and designs the pitcher final plan: the layer test, the sealed 2024 check with the pre-registered tree-vs-logit comparison, and ratings.
