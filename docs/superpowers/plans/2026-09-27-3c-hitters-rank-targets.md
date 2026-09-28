# 3c-hitters: Rank-Based Targets + Rerun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both 3c targets mean the same thing in every MLB season, then re-run plan A's decisions and plan B's final run.
- **Soon:** a top-144 season within 2 years.
- **Rating:** the best season within 4 years, valued at the typical SGP of its rank.

**Architecture:**
- `asof.py`: ranks each MLB hitter-season within its year and builds an as-of "typical value by rank" curve. The fixed SGP bar is gone.
- `walkforward.py`: its `bar` argument becomes `ctx`, which is the curve for the rating and unused for "soon".
- The two drivers change in a few lines.
- The sealed-2024 decisions stay **frozen**: they were made once, under the first labels.

**Tech Stack:** unchanged. No network.

**Spec:** `docs/superpowers/specs/2026-09-27-3c-hitters-design.md` — Part 1 "Targets — REVISED" and "Plan B result".

---

## Context the implementer needs

- Run from `prospects-model/`. Tests: `python -m unittest discover -s tests` (**171 pass, 3 skipped** before this plan).
- **Why:** the SGP spread between stars and replacement swings by season. The 144th-best hitter was worth 0.93 SGP in 2013, 0.16 in 2014 and 0.23 in 2026. So a fixed bar made "starter-quality" mean 82 hitters in 2026 and 195 in 2013. Ranks don't drift.
- **Rank and value records:** `dataset.load_labels` returns `{(player_id, type): [{season, value, pa, ip}]}`. `cohorts.build_rows` puts each player's hitter list into `row["mlb"]`; these are the *same dict objects*, so `asof.attach_ranks(labels)` must run right after `load_labels` and before the targets are used.
- **Frozen decisions (do not re-decide):** the soon contact+approach pair (kept) and tracking-for-soon (not used). Whatever the rerun of plan A adopts for "soon" is used as-is.
- Commits are local only; end each message with `Co-Authored-By: <current model> <noreply@anthropic.com>`.

---

### Task 1: Rank-based targets

**Files:** Replace `psmodel/asof.py` and `tests/test_asof.py`

- [ ] **Step 1: Failing tests.** Replace `tests/test_asof.py` with:

```python
import unittest

from psmodel import asof


def s(season, value, pa=500, rank=None):
    d = {"season": season, "value": value, "pa": pa, "ip": 0.0}
    if rank is not None:
        d["rank"] = rank
    return d


CURVE = [5.0, 4.0, 3.0, 2.0, 1.0, 0.5, -0.5]


class TestRanks(unittest.TestCase):
    def test_attach_ranks_orders_each_season_and_skips_pitchers(self):
        labels = {(1, "H"): [s(2020, 1.0)], (2, "H"): [s(2020, 3.0)], (3, "H"): [s(2020, 2.0)],
                  (1, "P"): [s(2020, 9.0)]}
        asof.attach_ranks(labels)
        self.assertEqual([labels[(p, "H")][0]["rank"] for p in (1, 2, 3)], [3, 1, 2])
        self.assertNotIn("rank", labels[(1, "P")][0])

    def test_ref_curve_is_the_median_by_rank_through_the_vantage(self):
        labels = {(i, "H"): [s(2013, float(10 - i)), s(2014, float(20 - 2 * i)), s(2020, 99.0), s(2016, 99.0)]
                  for i in range(3)}
        self.assertEqual(asof.ref_curve(labels, 2014), [15.0, 13.5, 12.0])   # 2020 and 2016 excluded


class TestTargets(unittest.TestCase):
    def test_rating_values_the_best_eligible_rank_in_the_window(self):
        mlb = [s(2019, 0, rank=4), s(2020, 0, pa=300, rank=2), s(2021, 0, pa=50, rank=1), s(2023, 0, rank=1)]
        self.assertEqual(asof.rating_target(mlb, 2018, CURVE), 4.0)   # rank 2; 2021 too few PA, 2023 outside
        self.assertEqual(asof.rating_target(mlb, 2019, CURVE), 5.0)   # 2023 rank 1 (window 2020-2023)

    def test_rating_floor_empty_and_deep_ranks(self):
        self.assertEqual(asof.rating_target([s(2019, 0, rank=7)], 2018, CURVE), 0.0)     # -0.5 floored
        self.assertEqual(asof.rating_target([s(2019, 0, rank=900)], 2018, CURVE), 0.0)   # past the curve
        self.assertEqual(asof.rating_target([], 2018, CURVE), 0.0)
        self.assertEqual(asof.useful_value([1.0] * 200), 1.0)

    def test_soon_is_a_top_144_season_within_two(self):
        self.assertTrue(asof.soon_target([s(2020, 0, rank=144)], 2018))
        self.assertFalse(asof.soon_target([s(2020, 0, rank=145)], 2018))
        self.assertFalse(asof.soon_target([s(2021, 0, rank=1)], 2018))      # outside the window

    def test_known_by_vantage(self):
        self.assertTrue(asof.rating_known(2018, 2022))
        self.assertFalse(asof.rating_known(2019, 2022))
        self.assertTrue(asof.soon_known(2021, 2023))
        self.assertFalse(asof.soon_known(2022, 2023))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run** `python -m unittest tests.test_asof` → FAIL (`AttributeError: … 'attach_ranks'`).

- [ ] **Step 3: Implement.** Replace `psmodel/asof.py` with:

```python
"""As-of targets: what a hitter produced after a snapshot season, and when that
answer became known. A backtest at vantage V may train only on cohorts whose
answer was known by V -- the NFLU rule.

Targets are RANK-based within each MLB season (plan B review): the SGP spread
between stars and replacement swings from year to year (the 144th-best hitter was
worth 0.93 SGP in 2013, 0.16 in 2014, 0.23 in 2026), so a fixed SGP bar made
"starter-quality" mean different things in different years.
"""
import numpy as np

from . import targets

RATING_YEARS = 4
SOON_YEARS = 2
FIRST_LABEL = 2013
STARTERS = 144          # 12 teams x 12 lineup slots


def attach_ranks(labels):
    """Adds 'rank' (1 = best that year, by total SGP) to every hitter-season, in place."""
    by = {}
    for (pid, typ), rows in labels.items():
        if typ == "H":
            for r in rows:
                by.setdefault(r["season"], []).append(r)
    for recs in by.values():
        for i, r in enumerate(sorted(recs, key=lambda r: -r["value"]), 1):
            r["rank"] = i
    return labels


def ref_curve(labels, v):
    """Typical SGP of the season ranked r (index r-1): the median across seasons
    FIRST_LABEL..v, 2020 excluded. Ranks are valued on this common scale."""
    by = {}
    for (pid, typ), rows in labels.items():
        if typ == "H":
            for r in rows:
                if FIRST_LABEL <= r["season"] <= v and r["season"] != 2020:
                    by.setdefault(r["season"], []).append(r["value"])
    n = min(len(x) for x in by.values())
    cols = [sorted(x, reverse=True)[:n] for x in by.values()]
    return [float(np.median(c)) for c in zip(*cols)]


def useful_value(curve):
    """The typical value of the 144th-best season: the starter line for top-N."""
    return curve[STARTERS - 1]


def rating_target(mlb, cohort, curve):
    """Best season in cohort+1..cohort+4 with >=100 PA, valued at the typical value
    of its rank, floored at 0."""
    vals = [curve[min(r["rank"], len(curve)) - 1] for r in mlb
            if cohort < r["season"] <= cohort + RATING_YEARS and (r.get("pa") or 0) >= targets.MIN_PA]
    return max(0.0, max(vals)) if vals else 0.0


def soon_target(mlb, cohort):
    """A top-144 season (starter-quality in that year) in cohort+1..cohort+2."""
    return any(r["rank"] <= STARTERS for r in mlb if cohort < r["season"] <= cohort + SOON_YEARS)


def rating_known(cohort, v):
    return cohort + RATING_YEARS <= v


def soon_known(cohort, v):
    return cohort + SOON_YEARS <= v
```

- [ ] **Step 4: Run** `python -m unittest tests.test_asof` → 6 pass. (`test_walkforward` now fails until Task 2; that's expected.)
- [ ] **Step 5: Commit** `feat(prospects-model): rank-based 3c targets that mean the same thing every season`.

---

### Task 2: The harness takes a target context

**Files:** Modify `psmodel/walkforward.py`, `tests/test_walkforward.py`

- [ ] **Step 1: Rename `bar` → `ctx` and `bars` → `ctxs` (whole words only)**, then confirm nothing named `bar` is left:

```bash
python - <<'EOF'
import re
p = "psmodel/walkforward.py"
s = open(p, encoding="utf-8").read()
s = re.sub(r"\bbars\b", "ctxs", s)
s = re.sub(r"\bbar\b", "ctx", s)
open(p, "w", encoding="utf-8").write(s)
EOF
grep -nwE "bar|bars" psmodel/walkforward.py || echo "no bar left"
```

- [ ] **Step 2:** In `psmodel/walkforward.py` replace

```python
def _y(r, target, ctx):
    if target == "rating":
        return asof.rating_target(r["mlb"], r["season"])
    return 1.0 if asof.soon_target(r["mlb"], r["season"], ctx) else 0.0
```

with

```python
def _y(r, target, ctx):
    """ctx is the as-of target context: the rank-value curve for the rating; unused for soon."""
    if target == "rating":
        return asof.rating_target(r["mlb"], r["season"], ctx)
    return 1.0 if asof.soon_target(r["mlb"], r["season"]) else 0.0
```

and in `metrics` replace

```python
        useful = r["y"] >= ctx if target == "rating" else r["y"] == 1.0
```

with

```python
        useful = r["y"] >= asof.useful_value(ctx) if target == "rating" else r["y"] == 1.0
```

- [ ] **Step 3: Tests.** In `tests/test_walkforward.py` replace everything from `def cohort_rows(` through the line `BARS = {v: 0.5 for v in range(2015, 2026)}` with:

```python
def cohort_rows(n=400, cohorts=range(2012, 2025), seed=0):
    """Synthetic cohorts: x drives the MLB outcome. Each outcome season is ranked
    within its year, as asof.attach_ranks does for real labels."""
    rng = np.random.default_rng(seed)
    rows, pid, seasons = [], 0, {}
    for c in cohorts:
        if c == 2020:
            continue
        for _ in range(n):
            x, z = float(rng.normal()), float(rng.normal())
            rec = {"season": c + 1, "value": x, "pa": 500, "ip": 0.0}
            seasons.setdefault(c + 1, []).append(rec)
            rows.append({"player_id": pid, "season": c, "sport_id": 12, "f": {"x": x, "z": z}, "mlb": [rec]})
            pid += 1
    for recs in seasons.values():
        for i, rec in enumerate(sorted(recs, key=lambda r: -r["value"]), 1):
            rec["rank"] = i
    return rows


CURVE = [3.0 - 0.01 * i for i in range(500)]       # rank r is typically worth 3.0 - 0.01 (r - 1)
CTXS = {v: CURVE for v in range(2015, 2026)}
```

Then, in the same file, make these exact replacements (every occurrence):

```bash
python - <<'EOF'
p = "tests/test_walkforward.py"
s = open(p, encoding="utf-8").read()
for old, new in (("BARS", "CTXS"),
                 ('"rating", 2019, 0.5', '"rating", 2019, CURVE'),
                 ('"rating", 2022, 0.5', '"rating", 2022, CURVE'),
                 ('"ridge", 0.5, 2019', '"ridge", CURVE, 2019')):
    s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
EOF
grep -n "0\.5" tests/test_walkforward.py
```

The remaining `0.5`s must all be "soon" calls (`"soon", 2024, 0.5`, `"soon", 2021, 0.5`, `metrics(test, p, "soon", 0.5)`) or the hand-made `_m`/`_r` metric values. The "soon" target ignores its context.

- [ ] **Step 4: Run** the full suite → 172 pass.
- [ ] **Step 5: Commit** `feat(prospects-model): walk-forward harness takes a target context`.

---

### Task 3: The drivers

**Files:** Modify `model3c_base.py`, `model3c_final.py`

- [ ] **Step 1: `model3c_base.py`.**

After `labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))` add:

```python
    asof.attach_ranks(labels)
```

Replace

```python
        bars = {v: asof.useful_bar(labels, v) for v in vantages}
```

with

```python
        bars = {v: asof.ref_curve(labels, v) for v in vantages}
```

Replace

```python
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; useful bar as-of: "
                 + ", ".join(f"{v} {b:.3f}" for v, b in bars.items()))
```

with

```python
        L.append(f"== {target.upper()} -- vantages {list(vantages)}; starter line (typical value of rank "
                 f"{asof.STARTERS}) as-of: " + ", ".join(f"{v} {asof.useful_value(b):.3f}" for v, b in bars.items()))
```

- [ ] **Step 2: `model3c_final.py`.**

In the module docstring, replace item 3 with:

```
3. OPENS THE 2024 COHORT for "soon" and reports its metrics. The two decisions
   made at 2024's first opening (contact+approach kept; tracking-for-soon not
   used) are FROZEN -- re-deciding on a cohort already seen would be moving the
   goalposts.
```

Delete the `built_on` function. After `labels = dataset.load_labels(os.path.join(CACHE, "labels.csv"))` add `    asof.attach_ranks(labels)`.

Then make these replacements:

| Find | Replace with |
|---|---|
| `        bars = {v: asof.useful_bar(labels, v) for v in vants[t]}` | `        bars = {v: asof.ref_curve(labels, v) for v in vants[t]}` |
| `    bar24 = asof.useful_bar(labels, 2024)` | `    bar24 = asof.ref_curve(labels, 2024)` |
| `    bar_now = asof.useful_bar(labels, PRODUCTION)` | `    bar_now = asof.ref_curve(labels, PRODUCTION)` |
| `                y_tr = np.concatenate([y_tr, [asof.rating_target(r["mlb"], r["season"]) for r in extra]])` | `                y_tr = np.concatenate([y_tr, [asof.rating_target(r["mlb"], r["season"], bar_now) for r in extra]])` |

Replace the whole contact+approach verdict block (from `    ca = set(cohorts.GROUPS["contact"] + cohorts.GROUPS["approach"])` through `            keys["soon"] = base_k`) with:

```python
    L.append("  2024 decisions are FROZEN from its first opening (2026-09-27, first labels): contact+approach "
             "kept, tracking-for-soon not used. The numbers below are for information only.")
```

Replace

```python
    use_soon = (lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z
```

with

```python
    would_use = (lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z
    use_soon = False            # frozen at 2024's first opening
```

and in the line after it replace

```python
          f"-> {'USE' if use_soon else 'do not use'}", ""]
```

with

```python
          f"-> frozen: not used (this run alone would say {'use' if would_use else 'do not use'})", ""]
```

- [ ] **Step 3: Check** `grep -n "useful_bar\|built_on" model3c_base.py model3c_final.py psmodel/*.py tests/*.py` → no matches. Run the full suite → 172 pass.
- [ ] **Step 4: Commit** `feat(prospects-model): 3c drivers use rank-based targets; 2024 decisions frozen`.

---

### Task 4: Rerun and record

- [ ] **Step 1: Security audit** (no network expected):

```bash
tasklist 2>/dev/null | grep -i python || echo "no stray python"
grep -rhoE "https?://[a-zA-Z0-9.-]+" psmodel/*.py *.py | sort -u
grep -rniE "api[_-]?key|password|token|secret|authorization" psmodel/*.py *.py || echo "no credentials"
git ls-files cache | wc -l
```

- [ ] **Step 2: Re-decide plan A** by running `python model3c_base.py` (several minutes). It rewrites `cache/model3c_choice.json`.
  - Sanity: the starter line for each vantage is a positive SGP, similar across vantages (the curve is a median, so it moves slowly).
  - Sanity: the ranks and AUCs are in the same range as before.

- [ ] **Step 3: Final run** with `python model3c_final.py`.
  - Sanity: in section 3's 2024 calibration, the top bucket's predicted and actual rates should now be close. That's the point of the fix.
  - Sanity: `hitter_ratings.csv` has ~1,400+ hitters.
  - Sanity: the top 15 are young AA/AAA players.

- [ ] **Step 4: Commit** any code touched while running (none expected). **Hand the report to Opus before telling the user** (standing lesson). After the review, add a "Rank-target rerun result" section to the 3c spec and update memory. Commit `docs(spec): record the rank-target rerun`.

---

## Not in this plan

Plan C (the FV consensus gate) needs the user's Board exports. Pitchers. Sub-project 4 (`prospects.html`).
