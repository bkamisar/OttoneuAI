import os
import tempfile
import unittest

from psmodel import http, mlbteams, statsapi
from psmodel import consensus as C


HITTERS = ("Name,Org,Pos,Current Level,Age,Top 100,Org Rk,Hit,Game Pwr,Raw Pwr,Spd,FV,PA,OBP,SLG,ISO,BB%,K%,wRC+,playerId\n"
           "A B,StL,SS/2B,AA,21.5,,3,40 / 55,30 / 50,55 / 60,50 / 50,50,,,,,,,,sa1\n")
PITCHERS = ("Name,Org,Pos,Current Level,Age,Top 100,Org Rk,FB,SL,CB,CH,CMD,FV,IP,K%,BB%,GB%,ERA,xFIP,playerId\n"
            "C D,ATH,SIRP,AAA,24.0,,9,60 / 70,,50 / 55,,40 / 45,45+,,,,,,,sa2\n")


def board(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        return C.load_board(path)
    finally:
        os.remove(path)


class TestBoardExtras(unittest.TestCase):
    def test_hitter_extras(self):
        e = board(HITTERS)[0]
        self.assertEqual((e["org"], e["pos"]), ("StL", "SS"))
        self.assertEqual((e["hit_fut"], e["pwr_fut"], e["raw_pwr_fut"], e["spd_fut"]), (55, 50, 60, 50))
        self.assertIsNone(e["fb_fut"])

    def test_pitcher_extras(self):
        e = board(PITCHERS)[0]
        self.assertEqual((e["org"], e["pos"], e["fv"]), ("ATH", "SIRP", 47.5))
        self.assertEqual((e["fb_fut"], e["sl_fut"], e["cb_fut"], e["ch_fut"], e["cmd_fut"]), (70, None, 55, None, 45))


class TestGroundOuts(unittest.TestCase):
    def test_pitcher_rows_carry_go_ao(self):
        split = {"player": {"id": 7, "fullName": "X"}, "team": {"name": "T"}, "league": {"name": "PCL"},
                 "stat": {"inningsPitched": "10.0", "groundOuts": 12, "airOuts": 8, "homeRuns": 1}}
        r = statsapi.normalize_pitcher(split, 2023, 11)
        self.assertEqual((r["go"], r["ao"]), (12, 8))


def standings_payload(rename=None, drop=None):
    teams = [{"team": {"id": tid, "name": f"City {nick}"}, "wins": 81 + i % 5, "losses": 81 - i % 5}
             for i, (tid, nick) in enumerate(sorted(set(mlbteams.TEAMS.values())))
             if tid != drop]
    if rename:
        teams[0]["team"]["name"] = rename
    return {"records": [{"teamRecords": teams[:15]}, {"teamRecords": teams[15:]}]}


class TestStandings(unittest.TestCase):
    def test_parses_thirty_clubs(self):
        pct = mlbteams.parse_standings(standings_payload(), 2023)
        self.assertEqual(len(pct), 30)
        self.assertTrue(all(0 < v < 1 for v in pct.values()))

    def test_wrong_name_or_missing_club_is_an_error(self):
        with self.assertRaises(http.DataError):
            mlbteams.parse_standings(standings_payload(rename="Somebody Else"), 2023)
        with self.assertRaises(http.DataError):
            mlbteams.parse_standings(standings_payload(drop=147), 2023)

    def test_org_aliases(self):
        self.assertEqual(mlbteams.team_of("StL"), mlbteams.team_of("STL"))
        self.assertEqual(mlbteams.team_of("ATH")[0], 133)
        self.assertEqual(mlbteams.team_of("OAK")[0], 133)


if __name__ == "__main__":
    unittest.main()
