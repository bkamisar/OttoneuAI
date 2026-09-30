import unittest

import numpy as np

from psmodel import fvplus as F


def hitter_entry(**kw):
    e = {"fv": 50.0, "top100": None, "org_rk": 5, "hit_fut": 55.0, "pwr_fut": 50.0, "raw_pwr_fut": 60.0,
         "spd_fut": None, "pos": "CF", "org": "NYY"}
    e.update(kw)
    return e


def pitcher_entry(**kw):
    e = {"fv": 45.0, "top100": None, "org_rk": 10, "fb_fut": 60.0, "sl_fut": None, "cb_fut": 55.0,
         "ch_fut": None, "cmd_fut": 40.0, "pos": "SP", "org": "SEA"}
    e.update(kw)
    return e


ROW = {"f": {"age": -0.5, "bb": 1.2, "is_aaa": 0.0, "is_aa": 1.0, "is_higha": 0.0}, "start_share": 0.2}


class TestKeysAndFeatures(unittest.TestCase):
    def test_keys_unique_and_drop(self):
        k = F.keys("H", "soon")
        self.assertEqual(len(k), len(set(k)))
        self.assertNotIn("sm", F.keys("H", "soon", drop="SM"))
        self.assertIn("raw_gap", F.keys("H", "rating"))
        self.assertNotIn("raw_gap", F.keys("H", "soon"))

    def test_hitter_features(self):
        x = F.features("H", hitter_entry(), ROW, {"hit_fut": 45, "pwr_fut": 45, "raw_pwr_fut": 50, "spd_fut": 40},
                       opp=0.45)
        self.assertEqual(x["spd"], 40)                 # blank -> the list median
        self.assertEqual(x["raw_gap"], 10)             # 60 - 50
        self.assertEqual(x["prem"], 1.0)
        self.assertEqual((x["bb"], x["age_rel"], x["opp"]), (1.2, -0.5, 0.45))

    def test_pitcher_features(self):
        x = F.features("P", pitcher_entry(), ROW, {"fb_fut": 50, "cmd_fut": 45}, opp=0.5, gb=0.3)
        self.assertEqual((x["brk"], x["ch"]), (55, F.NO_PITCH))
        self.assertAlmostEqual(x["fb_x_cmd"], (60 - 50) * (40 - 50) / 10)
        self.assertAlmostEqual(x["fb_x_brk"], (60 - 50) * (55 - 50) / 10)
        self.assertEqual((x["rel"], x["gb"]), (1.0, 0.3))
        x = F.features("P", pitcher_entry(sl_fut=None, cb_fut=None), dict(ROW, start_share=None),
                       {"fb_fut": 50, "cmd_fut": 45}, opp=0.5)
        self.assertEqual(x["brk"], F.NO_PITCH)
        self.assertIsNone(x["rel"])


class TestMatrixAndSplit(unittest.TestCase):
    def test_matrix_fills_with_training_mean(self):
        tr = [{"x": {"a": 1.0}}, {"x": {"a": 3.0}}, {"x": {"a": None}}]
        X, fill = F.matrix(tr, ["a"])
        self.assertEqual(list(X[:, 0]), [1.0, 3.0, 2.0])
        Xt, _ = F.matrix([{"x": {"a": None}}], ["a"], fill)
        self.assertEqual(Xt[0, 0], 2.0)

    def test_split_is_as_of_and_isolates_test_players(self):
        p = lambda pid: {"player_id": pid, "x": {}}
        classes = {2016: [p(1), p(2)], 2017: [p(3)], 2019: [p(4)], 2021: [p(2), p(5)]}
        known = lambda c, v: c + 4 <= v
        train, test = F._split(classes, 2021, known, lambda q: 1.0)
        self.assertEqual(sorted(q["player_id"] for q in train), [1, 3])   # 2019 unknown; player 2 is in the test
        self.assertEqual(sorted(q["player_id"] for q in test), [2, 5])

    def test_trainable(self):
        pl = lambda n, s: [{"y": 1.0}] * s + [{"y": 0.0}] * (n - s)
        self.assertTrue(F.trainable(pl(300, 0), "rating"))
        self.assertFalse(F.trainable(pl(299, 0), "rating"))
        self.assertFalse(F.trainable(pl(400, 29), "soon"))
        self.assertTrue(F.trainable(pl(400, 30), "soon"))


class TestDecisionMath(unittest.TestCase):
    def test_holm_adjust(self):
        adj = F.holm_adjust({"a": .01, "b": .04, "c": .03})
        self.assertAlmostEqual(adj["a"], .03)
        self.assertAlmostEqual(adj["c"], .06)
        self.assertAlmostEqual(adj["b"], .06)

    def test_pooled(self):
        d, z, n = F.pooled({1: {"d": .02, "se": .01}, 2: {"d": .01, "se": .01}, 3: None})
        self.assertAlmostEqual(d, .03)
        self.assertAlmostEqual(z, .03 / np.sqrt(2e-4))
        self.assertEqual(n, 2)

    def test_majority(self):
        self.assertEqual([F.majority(n) for n in (2, 4, 5)], [2, 3, 3])

    def test_conditions(self):
        r = lambda d, se, b50, f50: {"d": d, "se": se, "base": {"top50": b50}, "fam": {"top50": f50}}
        c = F.conditions({1: r(.02, .01, .1, .1), 2: r(-.01, .01, .1, .1), 3: r(.03, .01, .1, .1)}, "soon")
        self.assertTrue(c["majority"])
        self.assertFalse(c["harmed"])
        c = F.conditions({1: r(.05, .01, .1, .1), 2: r(-.03, .01, .1, .1)}, "rating")
        self.assertFalse(c["majority"])
        self.assertTrue(c["harmed"])


class TestShuffle(unittest.TestCase):
    def test_block_shuffle_stays_within_fv_grade(self):
        ps = [{"fv_grade": g, "x": {"fv": g, "a": i, "b": 10 * i}} for i, g in enumerate([45, 45, 45, 50, 50])]
        out = F.shuffled({2021: ps}, ["a", "b"], np.random.default_rng(1))[2021]
        for p in out:
            self.assertEqual(p["x"]["b"], 10 * p["x"]["a"])          # the block moves together
        self.assertEqual(sorted(p["x"]["a"] for p in out[:3]), [0, 1, 2])
        self.assertEqual(sorted(p["x"]["a"] for p in out[3:]), [3, 4])
        self.assertEqual([p["x"]["fv"] for p in out], [45, 45, 45, 50, 50])
        self.assertEqual([p["x"]["a"] for p in ps], [0, 1, 2, 3, 4])   # input untouched


class TestStatcastAndMap(unittest.TestCase):
    def test_partial_spearman(self):
        rng = np.random.default_rng(0)
        z = rng.normal(size=200)
        x = rng.normal(size=200)
        self.assertAlmostEqual(F.partial_spearman(x, x, z), 1.0)
        self.assertAlmostEqual(F.partial_spearman(z, x, z), 0.0, places=9)

    def test_fv_bucket_and_bins(self):
        self.assertEqual([F.fv_bucket(g) for g in (37.5, 42.5, 47.5, 55, 70)], [40, 40, 45, 55, 60])
        self.assertEqual([F.gbin(g) for g in (40, 45, 50, 52.5)], ["<=40", "45-50", "45-50", ">50"])

    def test_residuals_within_class_and_bucket(self):
        ps = [{"cls": 2021, "fv_grade": 50, "y": 1.0}, {"cls": 2021, "fv_grade": 50, "y": 0.0},
              {"cls": 2022, "fv_grade": 50, "y": 1.0}]
        self.assertEqual(F.residuals(ps), [0.5, -0.5, 0.0])

    def test_gb_z(self):
        rows = [{"player_id": i, "season": 2023, "sport_id": 11, "league": "PCL", "ip": 50.0, "go": g, "ao": 100 - g}
                for i, g in enumerate((30, 50, 70))]
        z = F.gb_z(rows)
        self.assertAlmostEqual(sum(z.values()), 0.0, places=9)
        self.assertGreater(z[(2, 2023, 11)], 0)


if __name__ == "__main__":
    unittest.main()
