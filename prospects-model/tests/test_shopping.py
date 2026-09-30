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


class TestBuild(unittest.TestCase):
    def test_build(self):
        # Pool = Ann, Bo, Cy (on the board with a model read). Zed shares a board name
        # but is 10 years off; Dee was on the 2024 list; Eve was never listed.
        ratings = [rated(1, "Ann Able", 20, 0.5, 0.6, 0.9), rated(2, "Bo Baker", 21, 0.1, 0.4, 0.2),
                   rated(3, "Cy Cole", 22, 0.3, 0.1, 0.5), rated(4, "Dee Dunn", 23, 0.4, 0.05, 0.7),
                   rated(5, "Eve Ekk", 19, 0.2, 0.01, 0.3), rated(6, "Zed Zim", 20, 0.35, 0.2, 0.6)]
        board = [entry("Ann Able", 20.0, 45.0, "Ann Able|SEA"), entry("Bo Baker", 21.0, 55.0, "Bo Baker|NYY"),
                 entry("Cy Cole", 22.0, 50.0, "Cy Cole|BOS"), entry("Zed Zim", 30.0, 40.0, "Zed Zim|TEX")]
        history = {2024: [entry("Dee Dunn", 21.0, 45.0, "d")]}
        graded, ungraded, unreadable = S.build(ratings, board, history)
        # fv pct Ann 1/3 Cy 2/3 Bo 1; soon pct Cy 1/3 Bo 2/3 Ann 1; ready Bo .83, Ann .67, Cy .5
        self.assertEqual([(g["key"], g["ready_rank"], g["odds"]) for g in graded],
                         [("Bo Baker|NYY", 1, 40), ("Ann Able|SEA", 2, 60), ("Cy Cole|BOS", 3, 10)])
        takes = {g["key"]: g["take"] for g in graded}
        self.assertEqual(takes["Ann Able|SEA"],
                         "Model: readier than the grade suggests; likes the bat more (ceiling: unproven)")
        self.assertEqual(takes["Bo Baker|NYY"],
                         "Model: further away than the grade suggests; likes the bat less (ceiling: unproven)")
        self.assertEqual(takes["Cy Cole|BOS"], "Model: further away than the grade suggests")
        self.assertEqual([(u["name"], u["listed"], u["take"]) for u in ungraded],
                         [("Dee Dunn", 2024, "On the 2024 list, since dropped"),
                          ("Zed Zim", None, "Name matches a FanGraphs prospect of a different age — check"),
                          ("Eve Ekk", None, "Never on a FanGraphs list")])
        self.assertEqual(ungraded[0]["odds"], 5)
        self.assertEqual(unreadable, [])

    def test_shared_names_are_flagged_not_guessed(self):
        ratings = [rated(1, "Ann Able", 20, 0.5, 0.6, 0.9), rated(2, "Bo Baker", 21, 0.1, 0.4, 0.2),
                   rated(3, "Cy Cole", 22, 0.3, 0.1, 0.5), rated(7, "Luis García", 21, 0.3, 0.3, 0.8)]
        board = [entry("Ann Able", 20.0, 45.0, "A|SEA"), entry("Bo Baker", 21.0, 55.0, "B|NYY"),
                 entry("Cy Cole", 22.0, 50.0, "C|BOS"), entry("Luis Garcia", 21.0, 45.0, "LG1|SEA"),
                 entry("Luis Garcia", 21.5, 40.0, "LG2|NYY")]
        graded, ungraded, unreadable = S.build(ratings, board, {})
        self.assertEqual(len(graded), 3)
        self.assertEqual([(u["player_id"], u["take"]) for u in ungraded],
                         [(7, "Name shared with a FanGraphs prospect — check")])
        self.assertEqual(unreadable, ["LG1|SEA", "LG2|NYY"])


def pitched(pid, name, age, rating, soon, rating_pct, start_share=1.0):
    return {"player_id": pid, "name": name, "level": "AA", "age": age, "rating": rating,
            "rating_pct": rating_pct, "soon": soon, "start_share": start_share}


class TestPitchers(unittest.TestCase):
    def test_current_board_pitchers_only(self):
        header = ["Top 100", "Org Rk", "Name", "Org", "Pos", "Current Level", "ETA", "FV", "Age"]
        rows = [header,
                ["", "3", "Ann Able", "SEA", "SS", "AA", "2027", "45+", "20.5"],
                ["", "4", "Pat Pitch", "SEA", "P", "AA", "2027", "50", "22.0"]]
        with tempfile.TemporaryDirectory() as d:
            path = write_csv(d, "prospects.csv", rows, "utf-8-sig")
            board = S.load_current_board(path, pitchers=True)
            hitters = S.load_current_board(path)
        self.assertEqual([e["fg_id"] for e in board], ["Pat Pitch|SEA"])
        self.assertEqual([e["fg_id"] for e in hitters], ["Ann Able|SEA"])

    def test_load_pitcher_ratings(self):
        header = ["player_id", "name", "level", "age", "start_share", "rating_sgp", "rating_percentile",
                  "p_useful_within_2", "stuff_in_rating", "stuff_in_soon", "flags"]
        rows = [header, ["1", "A Arm", "AAA", "24", "0.080", "0.2", "99.9", "0.28", "no", "no", "x"],
                ["2", "B Arm", "AA", "", "", "0.1", "10.0", "0.01", "no", "no", ""]]
        with tempfile.TemporaryDirectory() as d:
            r = S.load_pitcher_ratings(write_csv(d, "pr.csv", rows))
        self.assertAlmostEqual(r[0].pop("rating_pct"), 0.999)
        self.assertEqual(r[0], {"player_id": 1, "name": "A Arm", "level": "AAA", "age": 24.0,
                                "rating": 0.2, "soon": 0.28, "start_share": 0.08})
        self.assertEqual((r[1]["age"], r[1]["start_share"]), (None, None))

    def test_tier_and_role(self):
        self.assertEqual([S.tier(p) for p in (1.0, 0.96, 0.95, 0.92, 0.8, 0.76, 0.75, 0.1)],
                         [5, 5, 10, 10, 25, 25, 0, 0])
        self.assertEqual([S.role(x) for x in (1.0, 0.5, 0.49, 0.0, None)], ["SP", "SP", "RP", "RP", ""])

    def test_pitcher_take_is_always_unproven(self):
        self.assertEqual(S.take_pitcher(0.3, 0.0), "Model: readier than the grade suggests (unproven)")
        self.assertEqual(S.take_pitcher(-0.3, 0.0), "Model: further away than the grade suggests (unproven)")
        self.assertEqual(S.take_pitcher(0.0, 0.4), "Model likes the arm more (unproven)")
        self.assertEqual(S.take_pitcher(0.0, -0.4), "Model likes the arm less (unproven)")
        self.assertEqual(S.take_pitcher(0.3, -0.3),
                         "Model: readier than the grade suggests; likes the arm less (unproven)")
        self.assertEqual(S.take_pitcher(0.1, 0.1), "Model agrees")

    def test_build_pitchers(self):
        # 20 rated pitchers so the tiers mean something; Ann/Bo/Cy are on the board.
        ratings = [pitched(i, f"P{i:02d} Arm", 22, 0.0, i / 100, i / 20, 1.0 if i % 2 else 0.2)
                   for i in range(1, 18)]
        ratings += [pitched(101, "Ann Able", 20, 0.5, 0.60, 0.9), pitched(102, "Bo Baker", 21, 0.1, 0.30, 0.2),
                    pitched(103, "Cy Cole", 22, 0.3, 0.01, 0.5)]
        board = [entry("Ann Able", 20.0, 45.0, "Ann Able|SEA"), entry("Bo Baker", 21.0, 55.0, "Bo Baker|NYY"),
                 entry("Cy Cole", 22.0, 50.0, "Cy Cole|BOS")]
        history = {2024: [entry("P05 Arm", 21.0, 40.0, "old")]}
        graded, ungraded, unreadable = S.build(ratings, board, history, pitchers=True)
        self.assertEqual(sorted(g["key"] for g in graded), ["Ann Able|SEA", "Bo Baker|NYY", "Cy Cole|BOS"])
        for g in graded:
            self.assertNotIn("ready_rank", g)
            self.assertNotIn("odds", g)
        tiers = {g["key"]: g["tier"] for g in graded}
        self.assertEqual(tiers, {"Ann Able|SEA": 5, "Bo Baker|NYY": 10, "Cy Cole|BOS": 0})
        takes = {g["key"]: g["take"] for g in graded}
        self.assertEqual(takes["Ann Able|SEA"], "Model: readier than the grade suggests; likes the arm more (unproven)")
        self.assertTrue(all("(unproven)" in t or t == "Model agrees" for t in takes.values()))
        top = ungraded[0]
        self.assertEqual((top["name"], top["role"], top["tier"]), ("P17 Arm", "SP", 25))
        self.assertNotIn("odds", top)
        self.assertEqual({u["name"]: u["take"] for u in ungraded}["P05 Arm"], "On the 2024 list, since dropped")
        self.assertEqual({u["name"]: u["role"] for u in ungraded}["P16 Arm"], "RP")
        self.assertEqual(unreadable, [])


if __name__ == "__main__":
    unittest.main()
