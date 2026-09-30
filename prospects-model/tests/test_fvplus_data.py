import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
