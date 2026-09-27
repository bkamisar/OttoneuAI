import unittest
from psmodel import dataset


def milb_hitter(pid, season=2017, pa=400, **kw):
    r = {"player_id": pid, "name": f"p{pid}", "season": season, "sport_id": 12, "age": 22,
         "pa": pa, "ab": 360, "h": 100, "hr": 12, "bb": 35, "so": 80, "sb": 5,
         "obp": .340, "slg": .450, "np": 1600, "swings": 700, "whiffs": 170}
    r.update(kw)
    return r


def lab(season, value, pa=500, ip=0.0):
    return {"season": season, "value": value, "pa": pa, "ip": ip}


class TestBuild(unittest.TestCase):
    def test_target_is_mlb_peak(self):
        labels = {(1, "H"): [lab(2019, 1.0), lab(2020, 3.0), lab(2021, 2.0)]}
        rows = dataset.build([milb_hitter(1)], "H", labels, threshold=2.5)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["target"], 3.0)
        self.assertTrue(rows[0]["useful"])

    def test_never_arrived_is_a_labeled_zero(self):
        rows = dataset.build([milb_hitter(2)], "H", {}, threshold=1.0)
        self.assertEqual(rows[0]["target"], 0.0)
        self.assertFalse(rows[0]["useful"])

    def test_established_major_leaguer_is_not_a_prospect(self):
        """A rehab stint by an MLB regular must not teach 'AAA -> star'."""
        labels = {(3, "H"): [lab(2014, 4.0, pa=350), lab(2018, 5.0)]}
        self.assertEqual(dataset.build([milb_hitter(3, season=2017)], "H", labels, 1.0), [])
        labels = {(4, "H"): [lab(2016, 0.5, pa=200), lab(2018, 2.0)]}
        self.assertEqual(len(dataset.build([milb_hitter(4, season=2017)], "H", labels, 1.0)), 1)

    def test_pitcher_uses_pitcher_labels_only(self):
        """Pitchers batted before 2022 and have H rows; they must be ignored."""
        r = {"player_id": 5, "name": "p", "season": 2017, "sport_id": 12, "age": 23, "ip": 120.0,
             "so": 120, "bb": 40, "bf": 500, "hr9": .8, "era": 3.2, "whip": 1.15,
             "np": 1900, "strikes": 1200, "swings": 850, "whiffs": 210}
        labels = {(5, "H"): [lab(2019, 9.9, pa=20)], (5, "P"): [lab(2019, 1.5, pa=0, ip=150.0)]}
        rows = dataset.build([r], "P", labels, threshold=1.0)
        self.assertAlmostEqual(rows[0]["target"], 1.5)

    def test_volume_floor(self):
        self.assertEqual(dataset.build([milb_hitter(6, pa=120)], "H", {}, 1.0), [])


class TestThreshold(unittest.TestCase):
    def test_median_of_nth_best_across_full_seasons(self):
        labels = {}
        for season, vals in ((2016, [5, 3, 1]), (2017, [6, 4, 2]), (2020, [9, 9, 9]), (2018, [7, 5, 3])):
            for i, v in enumerate(vals):
                labels.setdefault((season * 10 + i, "H"), []).append(lab(season, v))
        old = dataset.USEFUL_N["H"]
        try:
            dataset.USEFUL_N["H"] = 2          # 2nd-best: 3, 4, 5 -> median 4 (2020 excluded)
            self.assertEqual(dataset.useful_threshold(labels, "H"), 4)
        finally:
            dataset.USEFUL_N["H"] = old


class TestCompleteCases(unittest.TestCase):
    def test_drops_rows_missing_any_feature(self):
        rows = [{"f": {"a": 1, "b": 2}}, {"f": {"a": 1, "b": None}}]
        self.assertEqual(len(dataset.complete_cases(rows, ["a", "b"])), 1)


if __name__ == "__main__":
    unittest.main()
