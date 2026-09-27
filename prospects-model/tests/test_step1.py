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


if __name__ == "__main__":
    unittest.main()
