import unittest

from psmodel import features as F
from psmodel import milb, statsapi


def raw(pa=200):
    return {"player_id": 1, "name": "A", "season": 2014, "sport_id": 12, "league": "Eastern League",
            "age": 22, "g": 50, "pa": pa, "ab": pa - 20, "h": 50, "hr": 5, "r": 20, "bb": 15, "so": 40,
            "sb": 3, "obp": 0.33, "slg": 0.40, "np": pa * 4}


class TestMissingSwings(unittest.TestCase):
    def test_missing_swings_give_missing_rates(self):
        f = F.hitter_features(dict(raw(), swings=None, whiffs=None))
        self.assertIsNone(f["whiff"])
        self.assertIsNone(f["swing"])
        self.assertIsNone(f["swstr"])
        self.assertAlmostEqual(f["k"], 0.2)

    def test_season_rows_can_skip_advanced(self):
        orig = (statsapi.season_stats, statsapi.season_advanced)
        calls = []
        statsapi.season_stats = lambda s, g, sid: [raw()]
        statsapi.season_advanced = lambda *a: calls.append(a) or {}
        try:
            rows = milb.season_rows(2014, 12, "hitting", advanced=False)
        finally:
            statsapi.season_stats, statsapi.season_advanced = orig
        self.assertEqual(calls, [])
        self.assertIsNone(rows[0]["swings"])
        self.assertIsNone(rows[0]["whiffs"])


if __name__ == "__main__":
    unittest.main()
