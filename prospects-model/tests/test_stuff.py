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


if __name__ == "__main__":
    unittest.main()
