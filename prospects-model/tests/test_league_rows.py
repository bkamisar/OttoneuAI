import unittest
from psmodel import cohorts, pcohorts


def hit(pid, league, so):
    return {"player_id": pid, "name": f"h{pid}", "season": 2023, "sport_id": 11, "league": league,
            "age": 24, "pa": 400, "ab": 350, "h": 90, "hr": 12, "bb": 40, "so": so, "sb": 5,
            "obp": .330, "slg": .420, "np": 1600, "swings": 700, "whiffs": 170}


def pit(pid, league, so):
    return {"player_id": pid, "name": f"p{pid}", "season": 2023, "sport_id": 11, "league": league,
            "age": 24, "g": 20, "gs": 20, "ip": 100.0, "so": so, "bb": 35, "bf": 430, "hr": 10,
            "hr9": .9, "era": 4.0, "whip": 1.3, "np": 1700, "strikes": 1080, "swings": 780, "whiffs": 190}


class TestLeagueRows(unittest.TestCase):
    """30 per league (the fallback threshold); INT strikes out far more than PCL."""

    def check(self, rows):
        for lg in ("PCL", "INT"):
            mine = [r for r in rows if r["league"] == lg]
            self.assertEqual(len(mine), 30)
            self.assertAlmostEqual(sum(r["f"]["k"] for r in mine), 0.0, places=9)

    def test_hitter_rows_normalized_within_league(self):
        raw = [hit(i, "PCL", 60 + i) for i in range(30)] + [hit(100 + i, "INT", 120 + i) for i in range(30)]
        self.check(cohorts.build_rows(raw, {}, {}))

    def test_pitcher_rows_normalized_within_league(self):
        raw = [pit(i, "PCL", 60 + i) for i in range(30)] + [pit(100 + i, "INT", 120 + i) for i in range(30)]
        self.check(pcohorts.build_rows(raw, {}, {}))


if __name__ == "__main__":
    unittest.main()
