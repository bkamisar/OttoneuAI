import unittest

import numpy as np

from psmodel import walkforward as W


def cohort_rows(n=150, cohorts=range(2012, 2025), seed=0):
    rng = np.random.default_rng(seed)
    rows, pid = [], 0
    for c in cohorts:
        if c == 2020:
            continue
        for _ in range(n):
            x, z = float(rng.normal()), float(rng.normal())
            rows.append({"player_id": pid, "season": c, "sport_id": 12, "f": {"x": x, "z": z},
                         "mlb": [{"season": c + 1, "value": x, "pa": 500, "ip": 0.0}]})
            pid += 1
    return rows


BARS = {v: 0.5 for v in range(2015, 2026)}


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
        train, test = W.frames(rows, "rating", 2019, 0.5, ["x"])
        self.assertEqual(max(r["season"] for r in train), 2015)
        self.assertNotIn(999, {r["player_id"] for r in train})
        self.assertIn(999, {r["player_id"] for r in test})
        soon_train, _ = W.frames(rows, "soon", 2021, 0.5, ["x"])
        self.assertEqual(max(r["season"] for r in soon_train), 2019)

    def test_rows_missing_a_key_are_dropped(self):
        rows = cohort_rows(n=5)
        rows[0]["f"]["x"] = None
        train, _ = W.frames(rows, "rating", 2019, 0.5, ["x"])
        self.assertNotIn(rows[0]["player_id"], {r["player_id"] for r in train})


class TestFitting(unittest.TestCase):
    def test_signal_family_is_adopted(self):
        res = W.compare(cohort_rows(), ["z"], ["x"], "rating", "ridge", BARS, W.RATING_VANTAGES)
        self.assertTrue(W.adopt(res)[0])

    def test_soon_classifier_ranks_signal(self):
        preds = W.predictions(cohort_rows(), ["x"], "soon", "logit", BARS, W.SOON_VANTAGES)
        self.assertEqual(sorted(preds), list(W.SOON_VANTAGES))
        for v, (test, p) in preds.items():
            self.assertGreater(W.metrics(test, p, "soon", 0.5)["rank"], 0.8)

    def test_too_little_training_is_not_available(self):
        res = W.compare(cohort_rows(n=5), ["z"], ["x"], "rating", "ridge", BARS, (2019,))
        self.assertIsNone(res[2019])


class TestDecisions(unittest.TestCase):
    def _m(self, rank, t50=0.5, t100=0.5):
        return {"rank": rank, "top50": t50, "top100": t100}

    def test_adopt_needs_two_wins_without_top_losses(self):
        win = {"base": self._m(0.3), "fam": self._m(0.4)}
        top_loss = {"base": self._m(0.3, t50=0.6), "fam": self._m(0.4, t50=0.5)}
        self.assertEqual(W.adopt({1: win, 2: win, 3: top_loss})[:2], (True, 2))
        self.assertEqual(W.adopt({1: win, 2: top_loss, 3: top_loss})[:2], (False, 1))
        self.assertFalse(W.adopt({1: win, 2: None, 3: None})[0])     # only one vantage available

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


class TestInteractions(unittest.TestCase):
    def test_pairs_reported_per_vantage(self):
        hits = W.interactions_by_vantage(cohort_rows(), ["x", "z"], "soon", BARS, (2021,))
        self.assertEqual(list(hits), [("x", "z")])
        self.assertEqual(hits[("x", "z")][0][0], 2021)


if __name__ == "__main__":
    unittest.main()
