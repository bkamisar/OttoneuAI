import os
import tempfile
import unittest

import numpy as np

from psmodel import step1


def stat(pid, season, pa=500, age=27):
    return {"player_id": pid, "season": season, "sport_id": 1, "age": age, "pa": pa, "ab": pa - 50,
            "h": 120, "hr": 20, "r": 70, "bb": 45, "so": 110, "sb": 5, "obp": 0.330, "slg": 0.450, "np": 2000}


def metrics_row(bbe=200.0, **over):
    m = {k: 50.0 for k in step1.tracking_keys()}
    m.update({"bbe": bbe, "pa": 500.0})
    m.update(over)
    return m


class TestTarget(unittest.TestCase):
    def test_rescales_to_600(self):
        self.assertAlmostEqual(step1.value_at_full_time(1.0, 300), 2.0)
        self.assertAlmostEqual(step1.value_at_full_time(-0.5, 600), -0.5)

    def test_small_samples_have_no_target(self):
        self.assertIsNone(step1.value_at_full_time(1.0, 99))
        self.assertIsNone(step1.value_at_full_time(1.0, 0))


class TestTables(unittest.TestCase):
    def test_load_table_parses_numbers_and_blanks(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("player_id,season,level,bbe,exit_velocity_avg\n5,2024,MLB,120,91.5\n6,2024,MLB,,\n")
            t = step1.load_table(p)
        self.assertEqual(t[(5, 2024)], {"bbe": 120.0, "exit_velocity_avg": 91.5})
        self.assertEqual(t[(6, 2024)], {"bbe": None, "exit_velocity_avg": None})

    def test_hitter_seasons_ignores_pitcher_labels(self):
        labels = {(1, "H"): [{"season": 2020, "value": 1.0, "pa": 300, "ip": 0.0}],
                  (1, "P"): [{"season": 2020, "value": 9.0, "pa": 0, "ip": 50.0}]}
        self.assertEqual(step1.hitter_seasons(labels), {1: {2020: (1.0, 300)}})


class TestMlbRows(unittest.TestCase):
    def test_filters_and_target(self):
        table = {(1, 2020): metrics_row(), (2, 2020): metrics_row(bbe=80.0),
                 (3, 2020): metrics_row(), (4, 2020): metrics_row()}
        seasons = {1: {2021: (1.0, 300)}, 2: {2021: (1.0, 300)}, 3: {2021: (1.0, 50)}, 4: {}}
        stats = {(p, 2020): stat(p, 2020) for p in (1, 2, 3, 4)}
        rows = step1.mlb_rows(table, seasons, stats, threshold=1.5)
        self.assertEqual([r["player_id"] for r in rows], [1])   # 2: <100 BBE; 3: <100 PA next; 4: no next season
        r = rows[0]
        self.assertAlmostEqual(r["target"], 2.0)
        self.assertEqual(r["weight"], 300.0)
        self.assertTrue(r["useful"])
        self.assertEqual(r["f"]["age"], 27)
        self.assertAlmostEqual(r["f"]["k"], 110 / 500)
        self.assertEqual(r["f"]["exit_velocity_avg"], 50.0)

    def test_complete_drops_rows_missing_a_key(self):
        rows = [{"f": {"a": 1.0, "b": None}}, {"f": {"a": 1.0, "b": 2.0}}]
        self.assertEqual(len(step1.complete(rows, ["a", "b"])), 1)

    def test_groups_cover_spray(self):
        self.assertIn("pull_percent", step1.GROUPS["spray"])
        self.assertEqual(step1.tracking_keys(["contact"]),
                         ["whiff_percent", "iz_contact_percent", "oz_contact_percent"])


class TestTranslation(unittest.TestCase):
    def test_offset_from_same_season_pairs(self):
        aaa = {(p, 2024): {"bbe": 100.0, "exit_velocity_avg": 90.0 + p} for p in range(10)}
        mlb = {(p, 2024): {"bbe": 60.0, "exit_velocity_avg": 89.0 + p} for p in range(10)}
        aaa[(99, 2024)] = {"bbe": 100.0, "exit_velocity_avg": 95.0}
        mlb[(99, 2024)] = {"bbe": 10.0, "exit_velocity_avg": 80.0}   # too few MLB batted balls
        t = step1.fit_translation(aaa, mlb, ["exit_velocity_avg"], n_boot=200)["exit_velocity_avg"]
        self.assertEqual(t["n"], 10)
        self.assertAlmostEqual(t["offset"], -1.0)
        self.assertAlmostEqual(t["lo"], -1.0)
        self.assertAlmostEqual(t["hi"], -1.0)
        self.assertAlmostEqual(t["slope"], 1.0)

    def test_metric_with_no_pairs(self):
        t = step1.fit_translation({}, {}, ["whiff_percent"])["whiff_percent"]
        self.assertEqual((t["n"], t["offset"]), (0, None))

    def test_translate_moves_only_translated_metrics(self):
        f = step1.translate({"exit_velocity_avg": 90.0, "obp": 0.35, "whiff_percent": None},
                            {"exit_velocity_avg": {"offset": -1.0}, "whiff_percent": {"offset": 2.0}})
        self.assertEqual(f, {"exit_velocity_avg": 89.0, "obp": 0.35, "whiff_percent": None})


class TestProspects(unittest.TestCase):
    def test_later_outcome_uses_only_later_qualifying_seasons(self):
        seasons = {7: {2022: (5.0, 600), 2024: (0.5, 300), 2025: (0.2, 80)}}
        self.assertEqual(step1.later_outcome(seasons, 7, 2022), (True, 1.0))
        self.assertEqual(step1.later_outcome(seasons, 8, 2022), (False, None))

    def test_aaa_rows_first_cohort_only(self):
        table = {(7, 2022): metrics_row(), (7, 2023): metrics_row(), (8, 2023): metrics_row(bbe=50.0)}
        stats = {k: stat(*k) for k in table}
        rows = step1.aaa_rows(table, stats, {7: {2024: (0.9, 600)}}, (2022, 2023), threshold=0.61)
        self.assertEqual([(r["player_id"], r["season"]) for r in rows], [(7, 2022)])
        self.assertTrue(rows[0]["arrived"])
        self.assertTrue(rows[0]["useful"])
        self.assertAlmostEqual(rows[0]["target"], 0.9)

    def test_spearman_ci(self):
        x = np.arange(50, dtype=float)
        rho, lo, hi = step1.spearman_ci(x, x * 2 + 1, n_boot=200)
        self.assertAlmostEqual(rho, 1.0)
        self.assertGreater(lo, 0.99)


if __name__ == "__main__":
    unittest.main()
