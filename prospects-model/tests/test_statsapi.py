import os, unittest
from psmodel import statsapi


class TestInnings(unittest.TestCase):
    """Baseball notation: 62.2 means 62 and 2/3 innings, not 62.2."""

    def test_thirds(self):
        self.assertAlmostEqual(statsapi.parse_innings("62.2"), 62 + 2 / 3, places=9)
        self.assertAlmostEqual(statsapi.parse_innings("10.1"), 10 + 1 / 3, places=9)
        self.assertAlmostEqual(statsapi.parse_innings("7.0"), 7.0, places=9)

    def test_junk_is_zero(self):
        self.assertEqual(statsapi.parse_innings(""), 0.0)
        self.assertEqual(statsapi.parse_innings(None), 0.0)
        self.assertEqual(statsapi.parse_innings("-.--"), 0.0)


class TestNum(unittest.TestCase):
    def test_leading_dot(self):
        self.assertAlmostEqual(statsapi.num(".369"), 0.369, places=9)

    def test_junk(self):
        self.assertEqual(statsapi.num(""), 0.0)
        self.assertEqual(statsapi.num("-.--"), 0.0)
        self.assertEqual(statsapi.num(None), 0.0)


class TestNormalize(unittest.TestCase):
    def test_hitter_row(self):
        split = {
            "player": {"id": 665742, "fullName": "Juan Soto"},
            "team": {"name": "New York Mets"},
            "league": {"name": "NL"},
            "stat": {"age": 27, "plateAppearances": 477, "atBats": 395, "hits": 110,
                     "homeRuns": 27, "runs": 63, "baseOnBalls": 78, "strikeOuts": 65,
                     "obp": ".397", "slg": ".522"},
        }
        r = statsapi.normalize_hitter(split, 2026, 1)
        self.assertEqual(r["player_id"], 665742)
        self.assertEqual(r["pa"], 477)
        self.assertEqual(r["hr"], 27)
        self.assertAlmostEqual(r["obp"], 0.397, places=9)
        self.assertEqual(r["season"], 2026)
        self.assertEqual(r["sport_id"], 1)

    def test_pitcher_row_converts_innings(self):
        split = {
            "player": {"id": 663878, "fullName": "Nate Pearson"},
            "team": {"name": "New Hampshire Fisher Cats"},
            "league": {"name": "EAS"},
            "stat": {"age": 22, "inningsPitched": "62.2", "strikeOuts": 69,
                     "baseOnBalls": 21, "homeRuns": 4, "era": "2.59", "whip": "0.99",
                     "gamesStarted": 16, "gamesPlayed": 16},
        }
        r = statsapi.normalize_pitcher(split, 2019, 12)
        self.assertAlmostEqual(r["ip"], 62 + 2 / 3, places=9)
        self.assertEqual(r["so"], 69)
        self.assertAlmostEqual(r["era"], 2.59, places=9)
        # HR/9 is derived, not served
        self.assertAlmostEqual(r["hr9"], 4 * 9 / (62 + 2 / 3), places=6)

    def test_zero_innings_gives_zero_hr9(self):
        split = {"player": {"id": 1, "fullName": "x"}, "stat": {"inningsPitched": "0.0", "homeRuns": 0}}
        self.assertEqual(statsapi.normalize_pitcher(split, 2020, 1)["hr9"], 0.0)


@unittest.skipUnless(os.environ.get("PROSPECTS_LIVE") == "1", "set PROSPECTS_LIVE=1 for network tests")
class TestLive(unittest.TestCase):
    def test_known_line_matches_spot_check(self):
        """Soto 2026: 477 PA, 27 HR, .397 OBP -- user-verified 2026-09-26."""
        rows = statsapi.season_stats(2026, "hitting", 1)
        soto = [r for r in rows if r["player_id"] == 665742]
        self.assertEqual(len(soto), 1, "exactly one row per player-season-sport")
        self.assertEqual(soto[0]["pa"], 477)
        self.assertEqual(soto[0]["hr"], 27)

    def test_multi_level_season_is_two_rows(self):
        """Witt Jr. 2021: 279 PA at AA and 285 at AAA. Both must survive."""
        aa = [r for r in statsapi.season_stats(2021, "hitting", 12) if r["player_id"] == 677951]
        aaa = [r for r in statsapi.season_stats(2021, "hitting", 11) if r["player_id"] == 677951]
        self.assertEqual(aa[0]["pa"], 279)
        self.assertEqual(aaa[0]["pa"], 285)


if __name__ == "__main__":
    unittest.main()
