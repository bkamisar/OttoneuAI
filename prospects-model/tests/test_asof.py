import unittest

from psmodel import asof


def s(season, value, pa=500):
    return {"season": season, "value": value, "pa": pa, "ip": 0.0}


class TestTargets(unittest.TestCase):
    def test_rating_is_best_of_next_four_eligible_seasons(self):
        mlb = [s(2019, 3.0), s(2020, 1.0, 300), s(2021, 9.0, 50), s(2023, 5.0)]
        self.assertEqual(asof.rating_target(mlb, 2018), 3.0)   # 2021 under 100 PA; 2023 outside
        self.assertEqual(asof.rating_target(mlb, 2019), 5.0)

    def test_rating_floor_and_empty(self):
        self.assertEqual(asof.rating_target([s(2019, -1.0)], 2018), 0.0)
        self.assertEqual(asof.rating_target([], 2018), 0.0)

    def test_soon_window_is_two_seasons(self):
        mlb = [s(2020, 0.7), s(2021, 0.9)]
        self.assertTrue(asof.soon_target(mlb, 2018, 0.6))
        self.assertFalse(asof.soon_target(mlb, 2017, 0.6))    # window 2018-2019
        self.assertFalse(asof.soon_target([s(2019, 0.5)], 2018, 0.6))

    def test_known_by_vantage(self):
        self.assertTrue(asof.rating_known(2018, 2022))
        self.assertFalse(asof.rating_known(2019, 2022))
        self.assertTrue(asof.soon_known(2021, 2023))
        self.assertFalse(asof.soon_known(2022, 2023))


class TestUsefulBar(unittest.TestCase):
    def test_uses_only_seasons_through_the_vantage(self):
        labels = {(i, "H"): [s(2013, float(i)), s(2014, float(100 + i))] for i in range(150)}
        self.assertEqual(asof.useful_bar(labels, 2013), 6.0)     # 144th best of 0..149
        self.assertEqual(asof.useful_bar(labels, 2014), 56.0)    # median(6, 106)


if __name__ == "__main__":
    unittest.main()
