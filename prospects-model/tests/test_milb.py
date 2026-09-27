import unittest
from psmodel import milb


def hit(pid, pa, ab, obp, slg, league="INT", **kw):
    r = {"player_id": pid, "name": f"p{pid}", "season": 2018, "sport_id": 11, "team": "T",
         "league": league, "age": 23, "g": 50, "pa": pa, "ab": ab, "h": 50, "hr": 5, "r": 20,
         "bb": 20, "so": 40, "sb": 3, "np": pa * 4, "hbp": 2, "obp": obp, "slg": slg}
    r.update(kw)
    return r


class TestCombine(unittest.TestCase):
    def test_team_splits_become_one_row(self):
        rows = milb.combine_by_player([hit(1, 200, 180, .300, .400), hit(1, 100, 90, .360, .500)], "hitting")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["pa"], 300)
        self.assertAlmostEqual(r["obp"], (.300 * 200 + .360 * 100) / 300, places=9)
        self.assertAlmostEqual(r["slg"], (.400 * 180 + .500 * 90) / 270, places=9)
        self.assertEqual(r["team"], "multiple")

    def test_single_split_unchanged(self):
        r = hit(2, 400, 360, .320, .450)
        self.assertEqual(milb.combine_by_player([r], "hitting")[0]["obp"], .320)

    def test_pitcher_rates_weighted_by_innings(self):
        a = {"player_id": 3, "name": "x", "team": "A", "g": 10, "gs": 10, "ip": 60.0, "so": 60, "bb": 20,
             "hr": 6, "np": 1000, "strikes": 640, "bf": 250, "era": 3.00, "whip": 1.10, "hr9": 0.9}
        b = dict(a, ip=30.0, so=30, bb=12, hr=6, np=500, strikes=310, bf=130, era=6.00, whip=1.50)
        r = milb.combine_by_player([a, b], "pitching")[0]
        self.assertAlmostEqual(r["ip"], 90.0)
        self.assertAlmostEqual(r["era"], (3.00 * 60 + 6.00 * 30) / 90, places=9)
        self.assertAlmostEqual(r["hr9"], 12 * 9 / 90, places=9)
        self.assertEqual(r["strikes"], 950)


class TestSeasonRows(unittest.TestCase):
    def setUp(self):
        self._s, self._a = milb.statsapi.season_stats, milb.statsapi.season_advanced

    def tearDown(self):
        milb.statsapi.season_stats, milb.statsapi.season_advanced = self._s, self._a

    def test_excludes_mexican_league_and_attaches_swings(self):
        milb.statsapi.season_stats = lambda s, g, sp: [hit(1, 300, 270, .3, .4),
                                                       hit(2, 300, 270, .3, .4, league="MEX")]
        milb.statsapi.season_advanced = lambda s, g, sp: {1: {"swings": 600, "whiffs": 150},
                                                          2: {"swings": 1, "whiffs": 1}}
        rows = milb.season_rows(2018, 11, "hitting")
        self.assertEqual([r["player_id"] for r in rows], [1])
        self.assertEqual((rows[0]["swings"], rows[0]["whiffs"]), (600, 150))

    def test_missing_advanced_is_zero_not_crash(self):
        milb.statsapi.season_stats = lambda s, g, sp: [hit(1, 300, 270, .3, .4)]
        milb.statsapi.season_advanced = lambda s, g, sp: {}
        self.assertEqual(milb.season_rows(2018, 11, "hitting")[0]["swings"], 0)


if __name__ == "__main__":
    unittest.main()
