import statistics
import unittest
from psmodel import features as F


def hrow(**kw):
    r = {"sport_id": 11, "age": 23, "pa": 400, "ab": 350, "h": 100, "hr": 16, "bb": 40,
         "so": 90, "sb": 8, "obp": .340, "slg": .460, "np": 1600, "swings": 720, "whiffs": 180}
    r.update(kw)
    return r


class TestHitter(unittest.TestCase):
    def test_rates(self):
        f = F.hitter_features(hrow())
        self.assertAlmostEqual(f["k"], 90 / 400)
        self.assertAlmostEqual(f["bb"], 40 / 400)
        self.assertAlmostEqual(f["iso"], .460 - 100 / 350)
        self.assertAlmostEqual(f["whiff"], 180 / 720)
        self.assertAlmostEqual(f["swing"], 720 / 1600)
        self.assertAlmostEqual(f["swstr"], 180 / 1600)
        self.assertEqual(f["is_aaa"], 1.0)

    def test_zero_denominators_are_missing_not_zero(self):
        f = F.hitter_features(hrow(swings=0, whiffs=0, np=0))
        self.assertIsNone(f["whiff"]); self.assertIsNone(f["swing"]); self.assertIsNone(f["swstr"])

    def test_aa_flag(self):
        self.assertEqual(F.hitter_features(hrow(sport_id=12))["is_aaa"], 0.0)


class TestPitcher(unittest.TestCase):
    def test_csw_uses_strikes_minus_swings(self):
        """Every swing is a strike, so called = strikes - swings (validated r=0.994)."""
        r = {"sport_id": 12, "age": 22, "ip": 100.0, "so": 110, "bb": 35, "bf": 420, "hr9": .9,
             "era": 3.5, "whip": 1.2, "np": 1000, "strikes": 600, "swings": 450, "whiffs": 120}
        f = F.pitcher_features(r)
        self.assertAlmostEqual(f["csw"], (600 - 450 + 120) / 1000)
        self.assertAlmostEqual(f["k"], 110 / 420)
        self.assertAlmostEqual(f["kbb"], (110 - 35) / 420)
        self.assertAlmostEqual(f["whiff"], 120 / 450)


class TestStandardize(unittest.TestCase):
    def test_within_level_season_mean_zero_and_flags_untouched(self):
        rows = [{"sport_id": s, "season": 2018, "f": {"k": v, "is_aaa": 1.0 if s == 11 else 0.0}}
                for s, v in ((11, .20), (11, .30), (12, .10), (12, .40))]
        F.standardize_within(rows, ["k", "is_aaa"])
        for s in (11, 12):
            ks = [r["f"]["k"] for r in rows if r["sport_id"] == s]
            self.assertAlmostEqual(sum(ks), 0.0, places=9)
        self.assertEqual([r["f"]["is_aaa"] for r in rows], [1.0, 1.0, 0.0, 0.0])

    def test_missing_stays_missing(self):
        rows = [{"sport_id": 11, "season": 2018, "f": {"k": v}} for v in (.2, .3, None)]
        F.standardize_within(rows, ["k"])
        self.assertIsNone(rows[2]["f"]["k"])


class TestStandardizeLeague(unittest.TestCase):
    def rows(self):
        out = []
        for lg, ks in (("PCL", (.10, .20)), ("INT", (.30, .40))):
            out += [{"sport_id": 11, "season": 2023, "league": lg, "f": {"k": k, "is_aaa": 1.0}} for k in ks]
        return out

    def test_each_league_centred_on_its_own_mean(self):
        rows = F.standardize_within_league(self.rows(), ["k", "is_aaa"], min_rows=2)
        self.assertEqual([round(r["f"]["k"], 9) for r in rows], [-1.0, 1.0, -1.0, 1.0])
        self.assertEqual([r["f"]["is_aaa"] for r in rows], [1.0] * 4)

    def test_small_league_falls_back_to_level_season(self):
        rows = F.standardize_within_league(self.rows(), ["k"], min_rows=3)
        mu, sd = .25, statistics.pstdev([.1, .2, .3, .4])
        self.assertAlmostEqual(rows[0]["f"]["k"], (.10 - mu) / sd)

    def test_no_league_falls_back_and_missing_stays_missing(self):
        rows = self.rows() + [{"sport_id": 11, "season": 2023, "league": None, "f": {"k": .25}},
                              {"sport_id": 11, "season": 2023, "league": "PCL", "f": {"k": None}}]
        F.standardize_within_league(rows, ["k"], min_rows=2)
        self.assertAlmostEqual(rows[4]["f"]["k"], 0.0)
        self.assertIsNone(rows[5]["f"]["k"])


if __name__ == "__main__":
    unittest.main()
