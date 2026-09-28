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

    def test_load_board_parses_future_bat_grades(self):
        r = dict.fromkeys(HEADER, "")
        r.update({"Name": "Bat Guy", "Age": "21", "FV": "50", "playerId": "sa9",
                  "Hit": "30 / 55", "Game Pwr": "20 / 45+"})
        blank = dict(r, Name="No Tools", playerId="sa10", Hit="", **{"Game Pwr": ""})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=HEADER)
                w.writeheader()
                w.writerows([r, blank])
            board = C.load_board(path)
        self.assertEqual((board[0]["hit_fut"], board[0]["pwr_fut"]), (55.0, 47.5))
        self.assertEqual((board[1]["hit_fut"], board[1]["pwr_fut"]), (None, None))

    def test_fv_order(self):
        # FV first; within a grade any Top 100 player beats any unranked one; then org rank
        e = C.fv_score(entry("e", 20, 50.0, top100=1, org_rk=1))
        a = C.fv_score(entry("a", 20, 50.0, top100=90, org_rk=3))
        b = C.fv_score(entry("b", 20, 50.0, org_rk=1))
        c = C.fv_score(entry("c", 20, 50.0, org_rk=2))
        d = C.fv_score(entry("d", 20, 47.5, top100=1, org_rk=1))
        self.assertTrue(e > a > b > c > d)
        self.assertEqual(C.fv_score(entry("f", 20, 40.0)), 40.0)


class TestMatch(unittest.TestCase):
    def test_offset_calibrated_and_age_guard(self):
        # this list's ages run ~0.85 yr above StatsAPI season age
        board = [entry("Ann Able", 20.8, 50), entry("Bo Baker", 22.9, 45), entry("Cy Cole", 19.7, 40),
                 entry("Dee Dunn", 27.0, 40)]
        ours = [player(1, "Ann Able", 20), player(2, "Bo Baker", 22), player(3, "Cy Cole", 19),
                player(4, "Dee Dunn", 21), player(5, "Eve Ekk", 20), player(6, "Ann Able", None)]
        m = C.match(ours[:5], board)
        self.assertAlmostEqual(m["offset"], 0.85)          # median of 0.8, 0.9, 0.7, 6.0
        self.assertEqual(set(m["matched"]), {1, 2, 3})
        self.assertEqual(m["matched"][2]["name"], "Bo Baker")
        self.assertEqual(m["age_rejected"], {4})           # same name, 5 years off: a different person
        self.assertEqual(m["ambiguous"], [])
        self.assertIn(6, C.match([ours[5]], board)["age_rejected"])   # no age: never accepted

    def test_same_name_is_ambiguous_never_guessed(self):
        board = [entry("Luis Garcia", 21.0, 45, fg_id="x"), entry("Luis Garcia", 21.5, 40, fg_id="y"),
                 entry("Ann Able", 20.0, 50)]
        m = C.match([player(1, "Luis García", 21), player(2, "Ann Able", 20)], board)
        self.assertEqual(set(m["matched"]), {2})
        self.assertEqual([a["player_id"] for a in m["ambiguous"]], [1])
        self.assertEqual(len(m["ambiguous"][0]["candidates"]), 2)

    def test_two_of_ours_claiming_one_entry_are_ambiguous(self):
        board = [entry("Jose Ramos", 20.0, 45), entry("Ann Able", 20.0, 50)]
        ours = [player(1, "Jose Ramos", 20), player(2, "José Ramos", 21), player(3, "Ann Able", 20)]
        m = C.match(ours, board)
        self.assertEqual(set(m["matched"]), {3})
        self.assertEqual(sorted(a["player_id"] for a in m["ambiguous"]), [1, 2])


def soon_rows(y):
    return [{"player_id": i, "y": float(v)} for i, v in enumerate(y)]


def cls(d, se, t50_base=0.5, t50_fam=0.5):
    return {"base": {"top50": t50_base}, "fam": {"top50": t50_fam}, "d": d, "se": se}


WIN = {2021: cls(0.05, 0.01), 2022: cls(0.03, 0.01), 2023: cls(0.0, 0.01)}
LOSE = {2021: cls(-0.01, 0.01), 2022: cls(0.0, 0.01), 2023: cls(0.005, 0.01)}


class TestScoring(unittest.TestCase):
    def test_pct_averages_ties(self):
        np.testing.assert_allclose(C.pct([3, 1, 1, 2]), [1.0, 0.375, 0.375, 0.75])

    def test_head_to_head_positive_when_challenger_is_better(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 200)
        res = C.head_to_head(soon_rows(y), y + rng.normal(0, 3.0, 200), y + rng.normal(0, 0.3, 200),
                             "soon", None)
        self.assertGreater(res["d"], 0)
        self.assertGreater(res["fam"]["rank"], res["base"]["rank"])
        self.assertIn("top50", res["base"])

    def test_head_to_head_none_when_untestable(self):
        self.assertIsNone(C.head_to_head(soon_rows([0] * 40), np.arange(40), np.arange(40), "soon", None))
        self.assertIsNone(C.head_to_head(soon_rows([0, 1] * 10), np.arange(20), np.arange(20), "soon", None))

    def test_rank_ci_brackets_point_and_clears_chance_for_a_good_ranker(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, 150)
        pt, lo, hi = C.rank_ci(soon_rows(y), y + rng.normal(0, 0.5, 150), "soon")
        self.assertTrue(lo <= pt <= hi)
        self.assertGreater(lo, 0.5)

    def test_rank_ci_none_when_one_outcome(self):
        self.assertIsNone(C.rank_ci(soon_rows([0] * 50), np.arange(50), "soon"))


class TestVerdict(unittest.TestCase):
    def test_model_leads(self):
        self.assertEqual(C.verdict(WIN, LOSE), "model leads")

    def test_tiebreaker_when_only_the_blend_wins(self):
        self.assertEqual(C.verdict(LOSE, WIN), "model as tiebreaker")

    def test_harm_veto_means_follow_fv(self):
        harm = {2021: cls(0.05, 0.01), 2022: cls(0.03, 0.01), 2023: cls(-0.03, 0.01)}
        self.assertEqual(C.verdict(harm, harm), "follow FV")

    def test_top50_tolerance(self):
        drop = {v: cls(r["d"], r["se"], 0.5, 0.4) for v, r in WIN.items()}
        self.assertEqual(C.verdict(drop, drop), "follow FV")

    def test_missing_classes_are_unavailable(self):
        one = {2019: None, 2021: cls(0.05, 0.01), 2022: None}
        self.assertEqual(C.verdict(one, one), "follow FV")

    def test_cautious(self):
        self.assertEqual(C.cautious("model leads", "model as tiebreaker"), "model as tiebreaker")
        self.assertEqual(C.cautious("follow FV", "model leads"), "follow FV")

    def test_sleepers_ok(self):
        self.assertTrue(C.sleepers_ok({1: (0.2, 0.05, 0.3), 2: (0.1, 0.01, 0.2), 3: None}, "rating"))
        self.assertFalse(C.sleepers_ok({1: (0.6, 0.45, 0.7), 2: (0.7, 0.55, 0.8), 3: None}, "soon"))


class TestBlend(unittest.TestCase):
    def test_fitted_blend_leans_on_the_informative_input(self):
        rng = np.random.default_rng(2)
        y = rng.integers(0, 2, 400).astype(float)
        pm = C.pct(y + rng.normal(0, 0.3, 400))
        pf = C.pct(rng.normal(0, 1, 400))
        m = C.fit_blend(pm, pf, y, "soon")
        self.assertGreater(m.coef_[0][0], abs(m.coef_[0][1]))
        self.assertEqual(C.apply_blend(m, pm, pf, "soon").shape, (400,))
        r = C.fit_blend(pm, pf, y * 3.0, "rating")
        self.assertGreater(r.coef_[0], abs(r.coef_[1]))


if __name__ == "__main__":
    unittest.main()
