import unittest
from psmodel import labels

DEN = {"HR": 4.0, "R": 12.5, "OBP": 0.00765, "SLG": 0.01165,
       "SO": 40.0, "ERA": 0.22, "WHIP": 0.03, "HR9": 0.10}
REPL_H = {"pa": 400, "ab": 360, "hr": 10, "r": 45, "obp": 0.305, "slg": 0.390}
REPL_P = {"ip": 120.0, "so": 110, "era": 4.20, "whip": 1.33, "hr9": 1.25}


class TestHitterSGP(unittest.TestCase):
    def test_replacement_level_player_scores_about_zero(self):
        row = {"pa": 400, "ab": 360, "hr": 10, "r": 45, "obp": 0.305, "slg": 0.390}
        self.assertAlmostEqual(labels.hitter_sgp(row, REPL_H, DEN, 600), 0.0, places=9)

    def test_better_player_scores_higher(self):
        weak = {"pa": 600, "ab": 540, "hr": 15, "r": 60, "obp": 0.310, "slg": 0.400}
        strong = {"pa": 600, "ab": 540, "hr": 40, "r": 100, "obp": 0.390, "slg": 0.560}
        self.assertGreater(labels.hitter_sgp(strong, REPL_H, DEN, 600),
                           labels.hitter_sgp(weak, REPL_H, DEN, 600))

    def test_counting_stats_prorate_replacement_to_playing_time(self):
        """Half a season of replacement-rate production is still ~0, not a
        penalty -- the 'Will Smith fix' in shared.js."""
        half = {"pa": 200, "ab": 180, "hr": 5, "r": 22.5, "obp": 0.305, "slg": 0.390}
        self.assertAlmostEqual(labels.hitter_sgp(half, REPL_H, DEN, 600), 0.0, places=6)


class TestPitcherSGP(unittest.TestCase):
    def test_replacement_level_pitcher_scores_about_zero(self):
        row = {"ip": 120.0, "so": 110, "era": 4.20, "whip": 1.33, "hr9": 1.25}
        self.assertAlmostEqual(labels.pitcher_sgp(row, REPL_P, DEN, 1400), 0.0, places=9)

    def test_ip_scale_never_scales_down(self):
        """max(1, ip/repl.ip) is load-bearing: a short reliever faces the FULL
        replacement strikeout total, so identical rates over fewer innings must
        score LOWER, not the same. Pro-rating down once inflated relievers to
        ~47% of all pitching value (shared.js invariant #3)."""
        rate = {"era": 2.50, "whip": 1.00, "hr9": 0.80}
        short = dict(rate, ip=30.0, so=40)      # 12.0 K/9
        full = dict(rate, ip=120.0, so=160)     # 12.0 K/9, same rates
        self.assertLess(labels.pitcher_sgp(short, REPL_P, DEN, 1400),
                        labels.pitcher_sgp(full, REPL_P, DEN, 1400))

    def test_lower_era_is_better(self):
        good = {"ip": 180.0, "so": 200, "era": 2.80, "whip": 1.05, "hr9": 0.90}
        bad = {"ip": 180.0, "so": 200, "era": 4.80, "whip": 1.05, "hr9": 0.90}
        self.assertGreater(labels.pitcher_sgp(good, REPL_P, DEN, 1400),
                           labels.pitcher_sgp(bad, REPL_P, DEN, 1400))


if __name__ == "__main__":
    unittest.main()
