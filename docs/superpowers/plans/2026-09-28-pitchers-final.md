# Pitchers Plan P-D: The Pitcher Final Run — Implementation Plan

> **For agentic workers:** executed inline on Opus at the user's request ("we only get one shot at it kinda"). Steps use checkbox (`- [ ]`) syntax. The design and every pre-registered rule are in `docs/superpowers/specs/2026-09-28-pitchers-design.md`, "P-D: the pitcher final run". **Where this plan and the spec differ, the spec wins.**

**Goal:** Test the rating leads, open the sealed 2024 pitcher class once for the two pre-registered "soon" decisions, and write production `cache/pitcher_ratings.csv`.

**Architecture:** `model_p_final.py` mirrors the hitters' `model3c_final.py`. It has two helper modules:
- `psmodel/stuff_layer.py`: the P-C season-level stuff score as-of a vantage, for AAA pitchers. It is the pitcher analog of `tracking_layer.step1_model` / `offsets` / `aaa_scores`, and reuses `tracking_layer.residualize` / `trust_weight` / `adjust`.
- `psmodel/pfinal.py`: the pure decision rules (calibration error, trees vs logit, the Wilson rule for showing percentages) and the write-once 2024 decisions file.

**Tech Stack:** Python 3, numpy, scikit-learn, and the existing `psmodel` modules. No network.

## Ground rules

- Run from `prospects-model/`. Before this plan: 239 collected, 236 pass, 3 skipped.
- **2024 is opened only by the real run (Task 5, step 3).**
  - Tests use synthetic rows.
  - `--no-open` runs everything up to the opening, then stops.
- `cache/` is never committed. Commit locally after each task; never push.
- **After the run, stop.** The results get an Opus review, which is recorded in the spec and memory before P-F.

---

### Task 1: Leads and the raw start share in `pcohorts.py`

**Files:** modify `psmodel/pcohorts.py`; test in `tests/test_pcohorts.py`.

- [ ] **Step 1: Failing tests** (add to `tests/test_pcohorts.py`):

```python
    # in TestBuildRows (its fixture: pitcher 1 in 2019 has gs=20 of g=20, pitcher 2 gs=0 of g=20)
    def test_rows_keep_the_raw_start_share(self):
        self.assertEqual((self.by[(1, 2019, 12)]["start_share"], self.by[(2, 2019, 12)]["start_share"]), (1.0, 0.0))


class TestLeads(unittest.TestCase):
    def test_leads_are_products_of_the_standardized_features(self):
        rows = [{"f": {"age": 1.5, "k": -2.0, "csw": 0.5}}, {"f": {"age": None, "k": 1.0, "csw": 1.0}}]
        pcohorts.add_products(rows)
        self.assertEqual((rows[0]["f"]["age_x_k"], rows[0]["f"]["age_x_csw"]), (-3.0, 0.75))
        self.assertIsNone(rows[1]["f"]["age_x_k"])
```

- [ ] **Step 2:** Run `python -m pytest tests/test_pcohorts.py -q`. Expect FAIL: `add_products` is missing.
- [ ] **Step 3: Implement:**

```python
LEADS = {"age_x_k": ("age", "k"), "age_x_csw": ("age", "csw")}   # P-A tree leads (rating)


def add_products(rows):
    for r in rows:
        f = r["f"]
        for name, (a, b) in LEADS.items():
            f[name] = f[a] * f[b] if f.get(a) is not None and f.get(b) is not None else None
    return rows
```

In `build_rows`, add `"start_share": r["gs"] / r["g"] if r.get("g") else None` to the row dict.

- [ ] **Step 4:** Run the file's tests again. Expect PASS.
- [ ] **Step 5:** Commit: `feat(pitchers): age x K / age x CSW lead terms and the raw start share on pitcher rows`.

### Task 2: `psmodel/stuff_layer.py`

**Files:** create `psmodel/stuff_layer.py`; create `tests/test_stuff_layer.py`.

- [ ] **Step 1: Failing tests:**

```python
import unittest

from psmodel import stuff_layer as SL

KEYS = ["age", "fb_speed"]


def stat(pid, age=24):
    return {"player_id": pid, "sport_id": 11, "age": age, "ip": 60.0, "so": 60, "bb": 20, "bf": 250,
            "hr9": 1.0, "era": 3.5, "whip": 1.2, "np": 960, "strikes": 600}


class Fixed:
    def predict(self, X):
        return [row[1] for row in X]           # score = translated fb_speed


class TestScores(unittest.TestCase):
    def test_aaa_scores_translate_and_need_volume_stats_and_the_season(self):
        table = {(1, 2022): {"pitches": 400, "fb_speed": 93.0}, (2, 2022): {"pitches": 200, "fb_speed": 99.0},
                 (3, 2023): {"pitches": 400, "fb_speed": 95.0}, (4, 2022): {"pitches": 400, "fb_speed": 90.0}}
        stats = {(1, 2022): stat(1), (2, 2022): stat(2), (3, 2023): stat(3)}      # 4 has no stat row
        got = SL.aaa_scores(table, stats, Fixed(), {"fb_speed": {"offset": 1.5}}, KEYS, {2022})
        self.assertEqual(got, {(1, 2022): 94.5})

    def test_offsets_and_mapping_rows_respect_the_vantage(self):
        aaa = {(1, 2022): {"pitches": 300, "fb_speed": 93.0}, (1, 2024): {"pitches": 300, "fb_speed": 80.0}}
        mlb = {(1, 2022): {"pitches": 300, "fb_speed": 94.0}, (1, 2024): {"pitches": 300, "fb_speed": 99.0}}
        self.assertAlmostEqual(SL.offsets(2023, aaa, mlb, ["fb_speed"])["fb_speed"]["offset"], 1.0)
        self.assertEqual(SL.mapping_table(mlb, 2023), {(1, 2022): mlb[(1, 2022)]})    # t <= v - 1
```

- [ ] **Step 2:** Run `python -m pytest tests/test_stuff_layer.py -q`. Expect FAIL: the module is missing.
- [ ] **Step 3: Implement:**

```python
"""The pitcher stuff layer (P-D): P-C's season-level stuff score, refit as-of a
vantage, for AAA pitchers -- the pitcher counterpart of tracking_layer's step-1
helpers. The layer math (residualize / trust_weight / adjust) is tracking_layer's."""
from . import evaluate, step1, stuff


def mapping_table(mlb_table, v):
    """MLB metric rows whose outcome season (t + 1) is known by v."""
    return {k: m for k, m in mlb_table.items() if k[1] <= v - 1}


def stuff_model(v, mlb_table, values, mlb_stats, keys, kind):
    rows = step1.complete(stuff.mlb_rows(mapping_table(mlb_table, v), values, mlb_stats, threshold=0.0), keys)
    return evaluate.fit(rows, keys, kind)


def offsets(v, aaa_table, mlb_table, metrics):
    """AAA->MLB offsets from same-season pairs in seasons <= v."""
    return stuff.fit_translation({k: m for k, m in aaa_table.items() if k[1] <= v},
                                 {k: m for k, m in mlb_table.items() if k[1] <= v}, metrics)


def aaa_scores(aaa_table, aaa_stats, model, translation, keys, seasons_wanted):
    """{(player_id, season): stuff score} for AAA pitcher-seasons with >= MIN_PITCHES
    tracked pitches, a StatsAPI row and every key present after translation."""
    out = {}
    for (pid, s), m in aaa_table.items():
        st = aaa_stats.get((pid, s))
        if s not in seasons_wanted or st is None or (m.get("pitches") or 0) < stuff.MIN_PITCHES:
            continue
        f = step1.translate(stuff._features(m, st), translation)
        if all(f.get(k) is not None for k in keys):
            out[(pid, s)] = float(evaluate.predict(model, [{"f": f}], keys)[0])
    return out
```

- [ ] **Step 4:** Run the tests. Expect PASS.
- [ ] **Step 5:** Commit: `feat(pitchers): stuff layer -- the season-level stuff score as-of a vantage for AAA pitchers`.

### Task 3: `psmodel/pfinal.py`, the pre-registered decision rules

**Files:** create `psmodel/pfinal.py`; create `tests/test_pfinal.py`.

- [ ] **Step 1: Failing tests:**

```python
import json
import os
import tempfile
import unittest

from psmodel import pfinal as PF


class TestRules(unittest.TestCase):
    def test_calibration_error_is_the_size_weighted_gap(self):
        self.assertAlmostEqual(PF.calibration_error([(0.1, 0.0, 10), (0.5, 0.2, 30)]), (1.0 + 9.0) / 40)

    def test_logit_only_if_strictly_better_on_both(self):
        t, l = {"top50": 0.10, "calib": 0.02}, {"top50": 0.12, "calib": 0.01}
        self.assertEqual(PF.soon_kind(t, l), "logit")
        self.assertEqual(PF.soon_kind(t, dict(l, top50=0.10)), "gbm")        # tie on top-50 keeps trees
        self.assertEqual(PF.soon_kind(t, dict(l, calib=0.02)), "gbm")        # tie on calibration keeps trees

    def test_wilson_interval(self):
        lo, hi = PF.wilson(10, 100)
        self.assertAlmostEqual(lo, 0.0552, places=3)
        self.assertAlmostEqual(hi, 0.1744, places=3)

    def test_percent_ok_needs_top_bucket_and_overall(self):
        good = [(0.01, 0.01, 100)] * 9 + [(0.10, 0.10, 100)]
        self.assertTrue(PF.percent_ok(good))
        self.assertFalse(PF.percent_ok(good[:-1] + [(0.25, 0.10, 100)]))      # top bucket overconfident
        self.assertFalse(PF.percent_ok([(0.05, 0.0, 100)] * 9 + [(0.10, 0.10, 100)]))   # overall too high


class TestFrozen(unittest.TestCase):
    def test_written_once_then_only_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dec.json")
            self.assertIsNone(PF.load_frozen(path))
            PF.freeze(path, {"soon_kind": "gbm"})
            self.assertEqual(PF.load_frozen(path), {"soon_kind": "gbm"})
            with self.assertRaises(SystemExit):
                PF.freeze(path, {"soon_kind": "logit"})
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["soon_kind"], "gbm")
```

- [ ] **Step 2:** Run `python -m pytest tests/test_pfinal.py -q`. Expect FAIL: the module is missing.
- [ ] **Step 3: Implement:**

```python
"""P-D's pre-registered decision rules and the write-once record of the 2024
opening (spec: 2026-09-28-pitchers-design.md, "P-D: the pitcher final run")."""
import json
import math
import os

Z95 = 1.959964


def calibration_error(buckets):
    """Size-weighted mean |mean predicted - actual| over walkforward.calibration buckets."""
    n = sum(b[2] for b in buckets)
    return sum(b[2] * abs(b[0] - b[1]) for b in buckets) / n


def soon_kind(trees, logit):
    """'logit' only if the trees LOSE on both: the logit's top-50 hit rate strictly
    higher AND its calibration error strictly lower. Otherwise the preset trees."""
    return "logit" if logit["top50"] > trees["top50"] and logit["calib"] < trees["calib"] else "gbm"


def wilson(k, n, z=Z95):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def _inside(pred, act, n):
    lo, hi = wilson(round(act * n), n)
    return lo <= pred <= hi


def percent_ok(buckets):
    """'Soon' odds may be shown as percentages only if the mean predicted rate is
    inside the actual rate's 95% Wilson interval in the TOP bucket and overall."""
    n = sum(b[2] for b in buckets)
    pred = sum(b[0] * b[2] for b in buckets) / n
    act = sum(b[1] * b[2] for b in buckets) / n
    return _inside(*buckets[-1]) and _inside(pred, act, n)


def load_frozen(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def freeze(path, decisions):
    """Write the 2024 decisions once. Refuses to overwrite: re-deciding on an opened
    class would be moving the goalposts (deleting the file takes the user's say-so)."""
    if os.path.exists(path):
        raise SystemExit(f"{path} exists -- the 2024 decisions are frozen; not overwriting")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 4:** Run the tests. Expect PASS.
- [ ] **Step 5:** Commit: `feat(pitchers): P-D decision rules -- calibration error, trees vs logit, percent display, write-once 2024 record`.

### Task 4: `model_p_final.py`

**Files:** create `prospects-model/model_p_final.py`.

The structure is `model3c_final.py`'s. The differences:

- **Setup:**
  - Labels: `asof.attach_ranks(labels, "P")`.
  - Rows: `pcohorts.build_rows(pcohorts.load_milb(), pcohorts.mlb_ip_history(), mlb)`, then `pcohorts.add_products(rows)`.
  - Choices: `model_p_choice.json` (P-A), `stuff_choice.json` (P-C keys and kind), `stuff_choice_final.json`. Stop unless its `choice == "season"`.
  - Tables: Savant `mlb_pitch_tracking.csv`, our `aaa_pitch_tracking.csv`.
  - Values: `stuff.season_values` built exactly as `stuff_run.py` builds them.
  - AAA StatsAPI rows 2022–26. Every context uses `asof.ref_curve(labels, v, "P")`.
- **`stuff_scores(v, wanted)`:** `SL.stuff_model(v, …)`, then `SL.offsets(v, …)`, then `SL.aaa_scores(…)`.
- **Section 1, leads (rating only):**
  - For each lead in `pcohorts.LEADS`, run `W.compare(rows, keys["rating"], [lead], "rating", "ridge", bars, W.RATING_VANTAGES)`, then `W.adopt`.
  - A parent dropped from the keys → "not testable".
- **Pre-flight:**
  - Build `bar24` and `stuff_scores(2024, (2022, 2024))`.
  - Build the training/test frames `W.frames(rows, "soon", 2024, bar24, keys["soon"], unseal=True)`, but compute no 2024 metric yet.
  - Print the counts of AAA-2022 training rows and AAA-2024 test rows that have a score.
  - **`--no-open` stops here.**
- **Section 2, the 2024 opening:**
  - If `PF.load_frozen(FROZEN)` returns decisions, use them and print "frozen from the first opening".
  - Otherwise:
    - (a) For each kind in `("gbm", "logit")`: `W.predictions(rows, keys["soon"], "soon", kind, {2024: bar24}, (2024,), unseal=True)[2024]`, then `W.metrics` and `W.calibration`, with `calib = PF.calibration_error(buckets)`. Then `kind_s = PF.soon_kind(m_gbm, m_logit)`.
    - (b) The stuff layer on `kind_s`, exactly as `model3c_final.py` section 3: `W.oof`, `TL.residualize`, `TL.trust_weight("soon", …)`, `TL.adjust`, `W.paired_gain`. Set `use_soon = (lo > 0 or hi < 0) and W.z_score(d, se) >= W.WIN_Z`.
    - `percent_ok = PF.percent_ok(buckets of kind_s)`.
    - Then `PF.freeze(FROZEN, {...})` with every number: both kinds' AUC / top-25 / 50 / 100 / calibration buckets / calibration error; the stuff weight and CI; the AUC gain, SE and counts; `soon_kind`, `use_soon_stuff`, `percent_ok`.
- **Section 3:** print the P-E gate from `stuff_choice_final.json`.
- **Section 4, production at v = 2026:**
  - `model3c_final.py` section 5 with `kind = "ridge"` for the rating (keys + adopted leads) and `kind_s` for soon.
  - Rating partial windows: `asof.rating_target(r["mlb"], r["season"], bar_now, "P")`.
  - Soon's stuff layer is applied only if `use_soon` AND the production CI excludes 0.
  - `pitcher_ratings.csv` columns, per the spec: `player_id, name, level, age, start_share, rating_sgp, rating_percentile, p_useful_within_2, stuff_in_rating, stuff_in_soon, flags`.
  - The flags are "rating stuff provisional" and, when `percent_ok` is false, "soon odds: rank only".
- **Sanity (report only):** the top 15 by rating (level, age), and the top 50's median start share and reliever count (start share < 0.5).
- **Outputs:** the report to `cache/model_p_final_report.txt`; the decisions (section 1 leads, frozen 2024, production weights) to `cache/model_p_final.json`.

- [ ] **Step 1:** Write the script.
- [ ] **Step 2:** Run `python -c "import model_p_final"` and the full suite.
- [ ] **Step 3:** Commit: `feat(pitchers): P-D final run -- leads, the one-time 2024 opening (frozen), production pitcher ratings`.

### Task 5: Run, review, record

- [ ] **Step 1:** Check for stray python processes.
- [ ] **Step 2:** Run `python model_p_final.py --no-open`. It must finish and show non-zero AAA-2022 / AAA-2024 scored counts. Section 1's lead results are fine to see, since the decision vantages are not sealed.
- [ ] **Step 3:** Run `python model_p_final.py`, the one opening. If it crashes after the freeze, fix the bug and rerun; the frozen decisions are reused.
- [ ] **Step 4:** Opus review:
  - Check every number in the report against the rule that produced it.
  - Check the sanity lists.
  - Write a "P-D result" section in the spec and update memory.
  - Commit: `docs(pitchers): P-D result`.
- [ ] **Step 5:** Stop. Hand the results to the user before P-F.
