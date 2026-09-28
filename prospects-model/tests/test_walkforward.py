import unittest

import numpy as np

from psmodel import walkforward as W


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


class TestFrames(unittest.TestCase):
    def test_sealed_cohort_refused_unless_unsealed(self):
        rows = cohort_rows(n=5)
        with self.assertRaises(ValueError):
            W.frames(rows, "soon", 2024, 0.5, ["x"])
        W.frames(rows, "soon", 2024, 0.5, ["x"], unseal=True)

    def test_train_only_known_cohorts_and_no_test_players(self):
        rows = cohort_rows(n=5)
        for season in (2014, 2019):
            rows.append({"player_id": 999, "season": season, "sport_id": 12,
                         "f": {"x": 0.0, "z": 0.0}, "mlb": []})
        train, test = W.frames(rows, "rating", 2019, CURVE, ["x"])
        self.assertEqual(max(r["season"] for r in train), 2015)
        self.assertNotIn(999, {r["player_id"] for r in train})
        self.assertIn(999, {r["player_id"] for r in test})
        soon_train, _ = W.frames(rows, "soon", 2021, 0.5, ["x"])
        self.assertEqual(max(r["season"] for r in soon_train), 2019)

    def test_rows_missing_a_key_are_dropped(self):
        rows = cohort_rows(n=5)
        rows[0]["f"]["x"] = None
        train, _ = W.frames(rows, "rating", 2019, CURVE, ["x"])
        self.assertNotIn(rows[0]["player_id"], {r["player_id"] for r in train})


class TestFitting(unittest.TestCase):
    def test_signal_family_is_adopted(self):
        res = W.compare(cohort_rows(), ["z"], ["x"], "rating", "ridge", CTXS, W.RATING_VANTAGES)
        self.assertTrue(W.adopt(res)[0])

    def test_soon_classifier_ranks_signal(self):
        preds = W.predictions(cohort_rows(), ["x"], "soon", "logit", CTXS, W.SOON_VANTAGES)
        self.assertEqual(sorted(preds), list(W.SOON_VANTAGES))
        for v, (test, p) in preds.items():
            self.assertGreater(W.metrics(test, p, "soon", 0.5)["rank"], 0.8)

    def test_too_little_training_is_not_available(self):
        res = W.compare(cohort_rows(n=5), ["z"], ["x"], "rating", "ridge", CTXS, (2019,))
        self.assertIsNone(res[2019])


class TestDecisions(unittest.TestCase):
    def _m(self, rank, t50=0.5, t100=0.5):
        return {"rank": rank, "top50": t50, "top100": t100}

    def _r(self, d, se=0.01, t50b=0.5, t50f=0.5):
        return {"base": self._m(0.3, t50=t50b), "fam": self._m(0.3 + d, t50=t50f), "d": d, "se": se}

    def test_adopt_counts_only_gains_beyond_the_noise(self):
        real, noise = self._r(0.02), self._r(0.001)
        self.assertEqual(W.adopt({1: real, 2: real, 3: noise})[:2], (True, 2))
        self.assertEqual(W.adopt({1: real, 2: noise, 3: noise})[:2], (False, 1))
        self.assertFalse(W.adopt({1: real, 2: None, 3: None})[0])     # only one vantage available

    def test_adopt_vetoes_a_clearly_worse_year_and_a_top50_collapse(self):
        real, harm = self._r(0.02), self._r(-0.03)
        self.assertFalse(W.adopt({1: real, 2: real, 3: harm})[0])
        slump = self._r(0.02, t50b=0.6, t50f=0.5)
        self.assertFalse(W.adopt({1: slump, 2: slump, 3: slump})[0])
        small = self._r(0.02, t50b=0.52, t50f=0.50)                     # one player, tolerated
        self.assertTrue(W.adopt({1: small, 2: small, 3: small})[0])

    def test_paired_gain(self):
        rng = np.random.default_rng(1)
        test = [{"player_id": i, "y": float(v)} for i, v in enumerate(rng.normal(size=300))]
        y = np.array([r["y"] for r in test])
        d, se = W.paired_gain(test, rng.normal(size=300), y, "rating", n_boot=100)
        self.assertGreater(d, 0.9)
        self.assertGreater(se, 0.0)
        self.assertEqual(W.paired_gain(test, y, y, "rating", n_boot=50), (0.0, 0.0))

    def test_pick_kind_prefers_simple_unless_complex_wins_twice(self):
        s, c = self._m(0.4), self._m(0.5)
        self.assertEqual(W.pick_kind({1: (s, c), 2: (c, s), 3: (c, s)}, "rating"), "ridge")
        self.assertEqual(W.pick_kind({1: (s, c), 2: (s, c), 3: (c, s)}, "soon"), "gbm")

    def test_calibration_bins(self):
        pred = np.linspace(0, 1, 100)
        test = [{"y": 1.0 if p > 0.5 else 0.0} for p in pred]
        bins = W.calibration(test, pred, bins=10)
        self.assertEqual(len(bins), 10)
        self.assertEqual(bins[0][1], 0.0)
        self.assertEqual(bins[-1][1], 1.0)


class TestProduction(unittest.TestCase):
    def test_production_keeps_every_known_player(self):
        rows = cohort_rows(n=100)
        for season in (2014, 2019):
            rows.append({"player_id": 999, "season": season, "sport_id": 12,
                         "f": {"x": 0.0, "z": 0.0}, "mlb": []})
        m, train, test, pred = W.production(rows, ["x"], "rating", "ridge", CURVE, 2019)
        self.assertIn(999, {r["player_id"] for r in train})
        self.assertEqual(max(r["season"] for r in train), 2015)
        self.assertEqual(len(pred), len(test))

    def test_oof_predictions_track_the_signal(self):
        train, _ = W.frames(cohort_rows(), "rating", 2022, CURVE, ["x"])
        p = W.oof(train, ["x"], "rating", "ridge")
        self.assertEqual(len(p), len(train))
        self.assertGreater(np.corrcoef(p, [r["f"]["x"] for r in train])[0, 1], 0.95)


class TestInteractions(unittest.TestCase):
    def test_pairs_reported_per_vantage(self):
        hits = W.interactions_by_vantage(cohort_rows(), ["x", "z"], "soon", CTXS, (2021,))
        self.assertEqual(list(hits), [("x", "z")])
        self.assertEqual(hits[("x", "z")][0][0], 2021)


if __name__ == "__main__":
    unittest.main()
