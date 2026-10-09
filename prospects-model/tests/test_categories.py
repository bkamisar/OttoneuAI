import unittest

import numpy as np

from psmodel import categories as K
from psmodel import labels

REPL_H = {"pa": 400.0, "hr": 10.0, "r": 45.0, "obp": .300, "slg": .380}
REPL_P = {"ip": 60.0, "so": 55.0, "era": 4.6, "whip": 1.35, "hr9": 1.3}
DEN = {"HR": 9.0, "R": 25.0, "OBP": .005, "SLG": .009, "SO": 40.0, "ERA": .25, "WHIP": .03, "HR9": .08}
AVG = {"H": 6000.0, "P": 1400.0}


def hit(pid, pa, ab, hr, r, obp, slg):
    return {"player_id": pid, "pa": pa, "ab": ab, "hr": hr, "r": r, "obp": obp, "slg": slg}


def pit(pid, ip, so, era, whip, hr):
    return {"player_id": pid, "ip": ip, "so": so, "era": era, "whip": whip, "hr": hr, "hr9": hr * 9 / ip}


class TestTerms(unittest.TestCase):
    def test_hitter_terms_sum_to_labels(self):
        r = hit(1, 550, 480, 25, 80, .350, .480)
        self.assertAlmostEqual(sum(K.hitter_terms(r, REPL_H, DEN, AVG["H"]).values()),
                               labels.hitter_sgp(r, REPL_H, DEN, AVG["H"]))

    def test_pitcher_terms_sum_to_labels_above_replacement_ip(self):
        r = pit(2, 150.0, 170, 3.40, 1.10, 15)
        self.assertAlmostEqual(sum(K.pitcher_terms(r, REPL_P, DEN, AVG["P"]).values()),
                               labels.pitcher_sgp(r, REPL_P, DEN, AVG["P"]))

    def test_k_term_is_linear_so_no_innings_means_zero(self):
        t = K.pitcher_terms({"ip": 0.0, "so": 0, "era": 0.0, "whip": 0.0, "hr9": 0.0}, REPL_P, DEN, AVG["P"])
        self.assertEqual(t, {"K": 0.0, "ERA": 0.0, "WHIP": 0.0, "HR9": 0.0})


class TestOutcome(unittest.TestCase):
    def tables(self):
        t = {s: {"H": {}, "P": {}, "repl": {"H": REPL_H, "P": REPL_P}} for s in range(2021, 2027)}
        t[2022]["H"][1] = hit(1, 300, 260, 10, 40, .340, .450)
        t[2024]["H"][1] = hit(1, 100, 90, 2, 10, .280, .350)
        return t

    def test_sums_window_terms_and_pools_rates(self):
        terms, pt, rates = K.outcome(1, "H", 2021, self.tables(), DEN, AVG)
        a = K.hitter_terms(hit(1, 300, 260, 10, 40, .340, .450), REPL_H, DEN, AVG["H"])
        b = K.hitter_terms(hit(1, 100, 90, 2, 10, .280, .350), REPL_H, DEN, AVG["H"])
        for c in K.HIT_CATS:
            self.assertAlmostEqual(terms[c], a[c] + b[c])
        self.assertEqual(pt, 400)
        self.assertAlmostEqual(rates["OBP"], (.340 * 300 + .280 * 100) / 400)
        self.assertAlmostEqual(rates["SLG"], (.450 * 260 + .350 * 90) / 350)
        self.assertAlmostEqual(rates["HR"], 12 / 400)

    def test_window_excludes_the_vantage_and_no_time_means_no_rates(self):
        terms, pt, rates = K.outcome(1, "H", 2024, self.tables(), DEN, AVG)   # window 2025-2028
        self.assertEqual((pt, rates), (0, None))
        self.assertEqual(set(terms.values()), {0.0})


class TestExpected(unittest.TestCase):
    def test_linear_in_playing_time(self):
        rates = {"HR": .04, "R": .13, "OBP": .340, "SLG": .460}
        one = K.expected_terms("H", 500, rates, REPL_H, DEN, AVG)
        two = K.expected_terms("H", 1000, rates, REPL_H, DEN, AVG)
        for c in K.HIT_CATS:
            self.assertAlmostEqual(two[c], 2 * one[c])
        self.assertEqual(set(K.expected_terms("H", 0, rates, REPL_H, DEN, AVG).values()), {0.0})
        p = K.expected_terms("P", 100, {"K": 1.0, "ERA": 4.0, "WHIP": 1.3, "HR9": 1.1}, REPL_P, DEN, AVG)
        self.assertAlmostEqual(p["K"], (100 - 55 * 100 / 60) / 40)


class TestModels(unittest.TestCase):
    def test_design_fill_and_weighted_ridge(self):
        rows = [{"f": {"a": float(i), "b": None if i % 3 == 0 else 1.0}} for i in range(60)]
        X, fill = K.design(rows, ["a", "b"])
        self.assertFalse(np.isnan(X).any())
        y = np.array([2.0 * i for i in range(60)])
        m, fill = K.fit_ridge(rows, ["a", "b"], y, w=np.ones(60))
        p = K.predict(m, fill, rows, ["a", "b"])
        self.assertGreater(np.corrcoef(p, y)[0, 1], 0.99)


class TestLadder(unittest.TestCase):
    def test_monotone_ladder(self):
        rng = np.random.default_rng(0)
        score = rng.normal(size=500)
        actual = score + rng.normal(scale=0.5, size=500)
        lad = K.ladder(score, actual)
        self.assertEqual(lad["inversions"], 0)
        self.assertEqual(sum(lad["counts"]), 500)
        self.assertGreater(lad["d"] - 1.96 * lad["se"], 0)
        self.assertTrue(K.ladder_pass(lad, 0.01))
        self.assertFalse(K.ladder_pass(lad, 0.2))

    def test_inversions(self):
        self.assertEqual(K.inversions([1, 2, 1.5, 3, 2.5]), 2)


if __name__ == "__main__":
    unittest.main()
