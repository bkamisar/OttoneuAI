import unittest

from psmodel import labels, stuff

REPL = {"ip": 118.5, "so": 106.2, "era": 4.311, "whip": 1.3402, "hr9": 1.2711}
DEN = {"SO": 41.3, "ERA": 0.2184, "WHIP": 0.0312, "HR9": 0.0975}


def stat(pid=1, ip=60.0, so=70, bb=20, age=25):
    return {"player_id": pid, "sport_id": 1, "age": age, "ip": ip, "so": so, "bb": bb, "bf": int(ip * 4.2),
            "hr9": 1.0, "era": 3.5, "whip": 1.2, "np": int(ip * 16), "strikes": int(ip * 10)}


class TestTarget(unittest.TestCase):
    def test_value_is_the_rate_line_at_100_ip(self):
        want = labels.pitcher_sgp({"ip": 100.0, "so": 120.0, "era": 3.0, "whip": 1.1, "hr9": 1.0}, REPL, DEN, 1500.0)
        for ip in (50.0, 150.0):                  # same rates, any workload -> same value
            row = {"ip": ip, "so": 1.2 * ip, "era": 3.0, "whip": 1.1, "hr9": 1.0}
            self.assertAlmostEqual(stuff.value_at_workload(row, REPL, DEN, 1500.0), want)
        self.assertIsNone(stuff.value_at_workload({"ip": 24.0, "so": 30, "era": 3.0, "whip": 1.1, "hr9": 1.0},
                                                  REPL, DEN, 1500.0))

    def test_useful_line_is_the_median_120th_best(self):
        values = {i: {2020: (float(i), 50.0), 2021: (float(i) + 2, 50.0)} for i in range(1, 121)}
        self.assertEqual(stuff.useful_threshold(values), 2.0)          # 120th best: 1.0 and 3.0

    def test_season_values_skip_small_workloads(self):
        rows = [dict(stat(i, ip=100.0 + i), era=4.0, whip=1.3, hr9=1.2) for i in range(250)]
        rows.append(stat(999, ip=10.0))
        vals = stuff.season_values({2021: rows}, dict(DEN, HR=4.0, R=12.0, OBP=0.008, SLG=0.012))
        self.assertEqual(vals[0][2021][1], 100.0)
        self.assertNotIn(999, vals)


FULL = {"pitches": 400, "fb_speed": 95.0, "fb_spin": 2300.0, "fb_ivb": 16.0, "fb_hb": 8.0,
        "breaking_speed": 85.0, "breaking_spin": 2500.0, "whiff_percent": 28.0}


class TestRows(unittest.TestCase):
    def test_mlb_rows_need_tracked_volume_and_a_valued_next_season(self):
        table = {(1, 2020): FULL, (2, 2020): dict(FULL, pitches=200), (3, 2020): FULL}
        values = {1: {2021: (1.5, 60.0)}, 2: {2021: (1.0, 60.0)}}
        stats = {(p, 2020): stat(p) for p in (1, 2, 3)}
        rows = stuff.mlb_rows(table, values, stats, threshold=1.0)
        self.assertEqual([(r["player_id"], r["target"], r["weight"], r["useful"]) for r in rows],
                         [(1, 1.5, 60.0, True)])
        self.assertEqual((rows[0]["f"]["fb_speed"], rows[0]["f"]["age"]), (95.0, 25))
        self.assertAlmostEqual(rows[0]["f"]["k"], 70 / 252)

    def test_later_outcome_is_the_best_valued_season_after(self):
        values = {1: {2020: (9.0, 90.0), 2021: (0.5, 30.0), 2023: (1.2, 80.0), 2027: (5.0, 100.0)}}
        self.assertEqual(stuff.later_outcome(values, 1, 2020), (True, 1.2))
        self.assertEqual(stuff.later_outcome(values, 2, 2020), (False, None))

    def test_aaa_rows_first_qualifying_season_prospects_only(self):
        table = {(1, 2022): FULL, (1, 2023): FULL, (2, 2022): dict(FULL, pitches=100), (3, 2023): FULL}
        stats = {k: stat(k[0]) for k in table}
        rows = stuff.aaa_rows(table, stats, {1: {2024: (2.0, 70.0)}}, (2022, 2023), 1.0, {3: {2021: 150.0}})
        self.assertEqual([(r["player_id"], r["season"], r["arrived"], r["target"], r["useful"]) for r in rows],
                         [(1, 2022, True, 2.0, True)])

    def test_translation_is_a_pitch_weighted_same_season_offset(self):
        aaa = {(1, 2023): {"pitches": 200, "fb_speed": 94.0}, (2, 2023): {"pitches": 400, "fb_speed": 92.0},
               (3, 2023): {"pitches": 100, "fb_speed": 90.0}}
        mlb = {(1, 2023): {"pitches": 300, "fb_speed": 95.0}, (2, 2023): {"pitches": 200, "fb_speed": 93.5},
               (3, 2023): {"pitches": 500, "fb_speed": 99.0}}
        t = stuff.fit_translation(aaa, mlb, ["fb_speed"])["fb_speed"]
        self.assertEqual(t["n"], 2)
        self.assertAlmostEqual(t["offset"], 1.25)


def shuffles(drho, dtop):
    return [{"rho_base": 0.3, "rho_fam": 0.3 + a, "top_base": 0.5, "top_fam": 0.5 + b} for a, b in zip(drho, dtop)]


class TestAdopt(unittest.TestCase):
    def test_one_player_top50_swings_do_not_veto(self):
        self.assertEqual(stuff.adopt(shuffles([0.02] * 10, [-0.02, 0.02] * 5)), (True, 10))

    def test_consistent_top50_loss_beyond_tolerance_rejects(self):
        self.assertFalse(stuff.adopt(shuffles([0.07] * 10, [-0.044] * 10))[0])

    def test_needs_rank_wins_in_8_of_10(self):
        self.assertEqual(stuff.adopt(shuffles([0.01] * 7 + [-0.01] * 3, [0.0] * 10)), (False, 7))


if __name__ == "__main__":
    unittest.main()
