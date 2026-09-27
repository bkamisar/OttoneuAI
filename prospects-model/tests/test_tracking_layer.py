import unittest

import numpy as np

from psmodel import tracking_layer as TL


class Stub:
    def predict(self, X):
        return X[:, 1]


def stat(pid, season):
    return {"player_id": pid, "season": season, "sport_id": 11, "age": 24, "pa": 400, "ab": 360, "h": 100,
            "hr": 15, "r": 50, "bb": 35, "so": 90, "sb": 5, "obp": 0.34, "slg": 0.45, "np": 1600,
            "swings": 800, "whiffs": 200}


class TestScores(unittest.TestCase):
    def test_scores_translated_rows_with_enough_batted_balls(self):
        aaa = {(1, 2024): {"bbe": 150.0, "exit_velocity_avg": 90.0},
               (2, 2024): {"bbe": 50.0, "exit_velocity_avg": 95.0},
               (3, 2021): {"bbe": 150.0, "exit_velocity_avg": 95.0}}
        stats = {k: stat(*k) for k in aaa}
        got = TL.aaa_scores(aaa, stats, Stub(), {"exit_velocity_avg": {"offset": -1.0}},
                            ["age", "exit_velocity_avg"], {2024})
        self.assertEqual(got, {(1, 2024): 89.0})


class TestResidual(unittest.TestCase):
    def test_residual_is_uncorrelated_with_base(self):
        rng = np.random.default_rng(0)
        base = rng.normal(size=500)
        resid, (a, b) = TL.residualize(2 * base + rng.normal(size=500), base)
        self.assertAlmostEqual(float(np.corrcoef(resid, base)[0, 1]), 0.0, places=6)
        self.assertAlmostEqual(b, 2.0, delta=0.15)


class TestWeights(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1)
        self.n = 3000

    def test_rating_weight_recovers_signal(self):
        base, resid = self.rng.normal(size=self.n), self.rng.normal(size=self.n)
        y = base + 0.5 * resid + 0.1 * self.rng.normal(size=self.n)
        w, lo, hi = TL.trust_weight("rating", y, base, resid, np.ones(self.n), np.arange(self.n), n_boot=200)
        self.assertAlmostEqual(w, 0.5, delta=0.05)
        self.assertGreater(lo, 0.0)

    def test_soon_weight_recovers_signal(self):
        base = self.rng.uniform(0.02, 0.5, size=self.n)
        resid = self.rng.normal(size=self.n)
        p = 1 / (1 + np.exp(-(np.log(base / (1 - base)) + resid)))
        y = (self.rng.uniform(size=self.n) < p).astype(float)
        w, lo, hi = TL.trust_weight("soon", y, base, resid, np.ones(self.n), np.arange(self.n), n_boot=200)
        self.assertAlmostEqual(w, 1.0, delta=0.25)
        self.assertGreater(lo, 0.0)

    def test_no_signal_interval_covers_zero(self):
        base, e, r = (self.rng.normal(size=400) for _ in range(3))
        resid = r - (r @ e) / (e @ e) * e          # exactly uncorrelated with y - base
        w, lo, hi = TL.trust_weight("rating", base + e, base, resid, np.ones(400), np.arange(400), n_boot=300)
        self.assertAlmostEqual(w, 0.0, places=9)
        self.assertLess(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_adjust(self):
        self.assertTrue(np.allclose(TL.adjust("rating", np.array([1.0]), np.array([2.0]), 0.5), [2.0]))
        self.assertAlmostEqual(float(TL.adjust("soon", np.array([0.5]), np.array([1.0]), np.log(3.0))[0]), 0.75)


if __name__ == "__main__":
    unittest.main()
