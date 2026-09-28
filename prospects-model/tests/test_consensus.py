import csv
import os
import tempfile
import unittest

import numpy as np

from psmodel import consensus as C

HEADER = ["Name", "Org", "Pos", "Current Level", "Age", "Top 100", "Org Rk", "Hit", "Game Pwr", "Raw Pwr",
          "Spd", "FV", "PA", "OBP", "SLG", "ISO", "BB%", "K%", "wRC+", "playerId"]


def entry(name, age, fv, top100=None, org_rk=None, fg_id=None):
    return {"fg_id": fg_id or name, "name": name, "key": C.norm_name(name), "age": age,
            "fv": fv, "top100": top100, "org_rk": org_rk}


def player(pid, name, age):
    return {"player_id": pid, "name": name, "age": age}


class TestNames(unittest.TestCase):
    def test_accents_case_punctuation_suffixes(self):
        self.assertEqual(C.norm_name("Jesús  Báez"), "jesus baez")
        self.assertEqual(C.norm_name("Bobby Witt Jr."), "bobby witt")
        self.assertEqual(C.norm_name("J.C. Escarra"), "jc escarra")
        self.assertEqual(C.norm_name("Logan O'Hoppe"), "logan ohoppe")
        self.assertEqual(C.norm_name("Jean-Carlos Mejia"), "jean carlos mejia")
        self.assertEqual(C.norm_name("James Tibbs III"), "james tibbs")

    def test_witt_is_not_witte(self):
        self.assertNotEqual(C.norm_name("Bobby Witt Jr."), C.norm_name("Bobby Witte"))


class TestBoard(unittest.TestCase):
    def test_parse_fv(self):
        self.assertEqual(C.parse_fv("45+"), 47.5)
        self.assertEqual(C.parse_fv("50"), 50.0)
        self.assertIsNone(C.parse_fv(""))
        self.assertIsNone(C.parse_fv(None))

    def test_load_board(self):
        def row(name, age, top, org, fv, pid):
            r = dict.fromkeys(HEADER, "")
            r.update({"Name": name, "Age": age, "Top 100": top, "Org Rk": org, "FV": fv, "playerId": pid})
            return r
        rows = [row("Dixon Machado", "24", "0", "7", "45", "11472"),     # 2017/18 style: 0 = unranked
                row("Top Guy", "20.5", "3", "1", "60", "sa1"),
                row("Top Guy", "20.5", "3", "1", "60", "sa1"),           # duplicate id: kept once
                row("No Grade", "19", "", "", "", "sa2")]                # no FV: not graded
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=HEADER)
                w.writeheader()
                w.writerows(rows)
            board = C.load_board(path)
        self.assertEqual([e["fg_id"] for e in board], ["11472", "sa1"])
        self.assertIsNone(board[0]["top100"])
        self.assertEqual(board[0]["org_rk"], 7)
        self.assertEqual(board[1]["top100"], 3)
        self.assertEqual(board[1]["age"], 20.5)
        self.assertEqual(board[1]["key"], "top guy")

    def test_fv_order(self):
        # FV first; within a grade any Top 100 player beats any unranked one; then org rank
        e = C.fv_score(entry("e", 20, 50.0, top100=1, org_rk=1))
        a = C.fv_score(entry("a", 20, 50.0, top100=90, org_rk=3))
        b = C.fv_score(entry("b", 20, 50.0, org_rk=1))
        c = C.fv_score(entry("c", 20, 50.0, org_rk=2))
        d = C.fv_score(entry("d", 20, 47.5, top100=1, org_rk=1))
        self.assertTrue(e > a > b > c > d)
        self.assertEqual(C.fv_score(entry("f", 20, 40.0)), 40.0)


if __name__ == "__main__":
    unittest.main()
