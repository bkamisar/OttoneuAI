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


def p(season, value, ip=60.0, rank=None):
    d = {"season": season, "value": value, "pa": 0, "ip": ip}
    if rank is not None:
        d["rank"] = rank
    return d


class TestPitchers(unittest.TestCase):
    def test_attach_ranks_by_type(self):
        labels = {(1, "P"): [p(2020, 1.0)], (2, "P"): [p(2020, 3.0)], (1, "H"): [s(2020, 9.0)]}
        asof.attach_ranks(labels, "P")
        self.assertEqual([labels[(1, "P")][0]["rank"], labels[(2, "P")][0]["rank"]], [2, 1])
        self.assertNotIn("rank", labels[(1, "H")][0])

    def test_ref_curve_uses_only_the_type(self):
        labels = {(i, "P"): [p(2013, float(10 - i)), p(2014, float(20 - 2 * i))] for i in range(3)}
        labels[(9, "H")] = [s(2013, 99.0), s(2014, 99.0)]
        self.assertEqual(asof.ref_curve(labels, 2014, "P"), [15.0, 13.5, 12.0])

    def test_rating_eligibility_is_by_innings(self):
        mlb = [p(2019, 0, ip=20.0, rank=1), p(2020, 0, ip=30.0, rank=3)]
        self.assertEqual(asof.rating_target(mlb, 2018, CURVE, "P"), 3.0)   # the 20-IP season doesn't count
        self.assertEqual(asof.rating_target(mlb, 2018, CURVE), 0.0)        # as hitter seasons: 0 PA, none count

    def test_soon_and_useful_line_are_top_120_for_pitchers(self):
        self.assertTrue(asof.soon_target([p(2020, 0, rank=120)], 2018, "P"))
        self.assertFalse(asof.soon_target([p(2020, 0, rank=121)], 2018, "P"))
        self.assertTrue(asof.soon_target([p(2020, 0, rank=121)], 2018))     # hitters: top 144
        self.assertEqual(asof.useful_value(list(range(200, 0, -1)), "P"), 81)


if __name__ == "__main__":
    unittest.main()
