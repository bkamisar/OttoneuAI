import csv
import os
import tempfile
import unittest

from psmodel import consensus as C
from psmodel import shopping as S


def entry(name, age, fv, fg_id, top100=None, org_rk=None):
    return {"fg_id": fg_id, "name": name, "key": C.norm_name(name), "age": age,
            "fv": fv, "top100": top100, "org_rk": org_rk}


def rated(pid, name, age, rating, soon, rating_pct):
    return {"player_id": pid, "name": name, "level": "AA", "age": age, "rating": rating,
            "rating_pct": rating_pct, "soon": soon}


def write_csv(d, name, rows, encoding="utf-8"):
    path = os.path.join(d, name)
    with open(path, "w", encoding=encoding, newline="") as fh:
        csv.writer(fh).writerows(rows)
    return path


class TestBoardFile(unittest.TestCase):
    def test_load_current_board(self):
        header = ["Top 100", "Org Rk", "Name", "Org", "Pos", "Current Level", "ETA", "FV", "Age"]
        rows = [["Report", "x"],                                                  # preamble line
                header,
                ["", "3", "Ann Able", "SEA", "SS", "AA", "2027", "45+", "20.5"],
                ["", "4", "Pat Pitch", "SEA", "P", "AA", "2027", "50", "22.0"],     # pitcher: skipped
                ["", "3", "Ann Able", "SEA", "SS", "AA", "2027", "45+", "20.5"],    # duplicate: skipped
                ["", "9", "No Grade", "SEA", "C", "A", "2029", "", "19.0"]]         # no FV: skipped
        with tempfile.TemporaryDirectory() as d:
            board = S.load_current_board(write_csv(d, "prospects.csv", rows, "utf-8-sig"))
        self.assertEqual(len(board), 1)
        e = board[0]
        self.assertEqual(e["fg_id"], "Ann Able|SEA")
        self.assertEqual((e["fv"], e["age"], e["org_rk"], e["top100"], e["key"]),
                         (47.5, 20.5, 3, None, "ann able"))

    def test_missing_header_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_csv(d, "bad.csv", [["a", "b"], ["1", "2"]])
            with self.assertRaises(ValueError):
                S.load_current_board(path)

    def test_load_ratings_undoes_the_csv_guard(self):
        header = ["player_id", "name", "level", "age", "rating_sgp", "rating_percentile",
                  "p_useful_within_2", "tracking_in_rating", "tracking_in_soon", "flags"]
        rows = [header,
                ["1", "'=Odd Name", "AAA", "21", "0.5", "99.0", "0.25", "yes", "no", ""],
                ["2", "'Tis Name", "AA", "", "0.1", "10.0", "0.01", "no", "no", ""]]
        with tempfile.TemporaryDirectory() as d:
            r = S.load_ratings(write_csv(d, "ratings.csv", rows))
        self.assertEqual(r[0], {"player_id": 1, "name": "=Odd Name", "level": "AAA", "age": 21.0,
                                "rating": 0.5, "rating_pct": 0.99, "soon": 0.25})
        self.assertEqual((r[1]["name"], r[1]["age"]), ("'Tis Name", None))


class TestText(unittest.TestCase):
    def test_odds_round_to_five(self):
        self.assertEqual([S.odds(p) for p in (0.6, 0.188, 0.03, 0.024, 0.0)], [60, 20, 5, 0, 0])

    def test_take(self):
        self.assertEqual(S.take(0.3, 0.0), "Model: readier than the grade suggests")
        self.assertEqual(S.take(-0.3, 0.1), "Model: further away than the grade suggests")
        self.assertEqual(S.take(0.1, 0.4), "Model likes the bat more (ceiling: unproven)")
        self.assertEqual(S.take(0.0, -0.5), "Model likes the bat less (ceiling: unproven)")
        self.assertEqual(S.take(0.3, -0.3),
                         "Model: readier than the grade suggests; likes the bat less (ceiling: unproven)")
        self.assertEqual(S.take(0.2, -0.2), "Model agrees")


if __name__ == "__main__":
    unittest.main()
