import unittest
from psmodel import metrics as M


def ev(code, zone, side="R", **hit):
    e = {"batter": 1, "pitcher": 2, "bat_side": side, "pitch_hand": "R", "code": code, "zone": zone,
         "ev": None, "la": None, "dist": None, "traj": None, "hc_x": None, "hc_y": None}
    e.update(hit)
    return e


EVENTS = [
    ev("C", 5),                                                       # called strike, zone, no swing
    ev("S", 12),                                                      # whiff out of zone
    ev("F", 4),                                                       # foul in zone
    ev("T", 6),                                                       # foul tip in zone
    ev("X", 5, ev=100.0, la=28.0, dist=400.0, traj="fly_ball", hc_x=60.0, hc_y=100.0),     # pulled (RHB)
    ev("B", 13),                                                      # ball out of zone
    ev("D", 7, ev=90.0, la=10.0, dist=250.0, traj="line_drive", hc_x=125.42, hc_y=100.0),  # straightaway
    ev("L", 8),                                                       # foul bunt in zone
]


class TestBarrel(unittest.TestCase):
    def test_window(self):
        self.assertTrue(M.is_barrel(98.0, 28.0))
        self.assertFalse(M.is_barrel(98.0, 25.0))
        self.assertFalse(M.is_barrel(97.9, 28.0))
        self.assertTrue(M.is_barrel(116.0, 8.0))
        self.assertFalse(M.is_barrel(116.0, 51.0))
        self.assertTrue(M.is_barrel(120.0, 50.0), "window stops widening at 116 mph")
        self.assertFalse(M.is_barrel(None, 28.0))


class TestSpray(unittest.TestCase):
    def test_pull_depends_on_handedness(self):
        self.assertEqual(M.direction(ev("X", 5, "R", hc_x=60.0, hc_y=100.0), 15.0), "pull")
        self.assertEqual(M.direction(ev("X", 5, "L", hc_x=60.0, hc_y=100.0), 15.0), "oppo")
        self.assertEqual(M.direction(ev("X", 5, "R", hc_x=125.42, hc_y=100.0), 15.0), "straight")
        self.assertIsNone(M.direction(ev("X", 5, "R"), 15.0))


class TestDefault(unittest.TestCase):
    def setUp(self):
        self.m = M.hitter_metrics(EVENTS)[1]

    def test_discipline(self):
        m = self.m
        self.assertEqual((m["pitches"], m["swings"]), (8, 6))
        self.assertAlmostEqual(m["whiff_percent"], 100 / 6)
        self.assertAlmostEqual(m["swing_percent"], 75.0)
        self.assertAlmostEqual(m["oz_swing_percent"], 50.0)
        self.assertAlmostEqual(m["oz_contact_percent"], 0.0)
        self.assertAlmostEqual(m["z_swing_percent"], 500 / 6)
        self.assertAlmostEqual(m["iz_contact_percent"], 100.0)

    def test_batted_balls(self):
        m = self.m
        self.assertEqual(m["bbe"], 2)
        self.assertAlmostEqual(m["exit_velocity_avg"], 95.0)
        self.assertAlmostEqual(m["max_hit_speed"], 100.0)
        self.assertAlmostEqual(m["avg_best_speed"], 100.0)
        self.assertAlmostEqual(m["hard_hit_percent"], 50.0)
        self.assertAlmostEqual(m["barrel_batted_rate"], 50.0)
        self.assertAlmostEqual(m["sweet_spot_percent"], 100.0)
        self.assertAlmostEqual(m["launch_angle_avg"], 19.0)
        self.assertAlmostEqual(m["avg_distance"], 325.0)
        self.assertAlmostEqual(m["flyballs_percent"], 50.0)
        self.assertAlmostEqual(m["linedrives_percent"], 50.0)
        self.assertAlmostEqual(m["pull_percent"], 50.0)
        self.assertAlmostEqual(m["straightaway_percent"], 50.0)
        self.assertAlmostEqual(m["opposite_percent"], 0.0)


class TestVariants(unittest.TestCase):
    def test_foul_tip_as_whiff(self):
        m = M.hitter_metrics(EVENTS, {"foul_tip_is_whiff": True})[1]
        self.assertAlmostEqual(m["whiff_percent"], 200 / 6)
        self.assertAlmostEqual(m["iz_contact_percent"], 80.0)

    def test_bunts_excluded(self):
        m = M.hitter_metrics(EVENTS, {"count_bunts": False})[1]
        self.assertEqual(m["swings"], 5)
        self.assertAlmostEqual(m["whiff_percent"], 20.0)
        self.assertAlmostEqual(m["z_swing_percent"], 400 / 6)

    def test_bunt_batted_balls_follow_the_variant(self):
        bunt = ev("X", 5, ev=40.0, la=-20.0, dist=20.0, traj="bunt_grounder", hc_x=150.0, hc_y=170.0)
        self.assertEqual(M.hitter_metrics([bunt])[1]["groundballs_percent"], 100.0)
        self.assertEqual(M.hitter_metrics([bunt], {"count_bunts": False})[1]["bbe"], 0)

    def test_zero_denominators_are_none(self):
        m = M.hitter_metrics([ev("B", 13)])[1]
        self.assertIsNone(m["whiff_percent"])
        self.assertIsNone(m["exit_velocity_avg"])
        self.assertIsNone(m["oz_contact_percent"])


if __name__ == "__main__":
    unittest.main()
