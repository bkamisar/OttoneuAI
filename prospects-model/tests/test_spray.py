import unittest

from psmodel import spray


def e(x, y, side="R", traj="fly_ball", code="X"):
    return {"batter": 1, "code": code, "ev": 95.0, "traj": traj, "hc_x": x, "hc_y": y, "bat_side": side}


class TestSpray(unittest.TestCase):
    def test_angle_mirrors_lefties(self):
        self.assertLess(spray.angle(e(60.0, 100.0)), -15.0)            # RHB to left field: pulled
        self.assertGreater(spray.angle(e(60.0, 100.0, "L")), 15.0)     # LHB, same spot: opposite
        self.assertIsNone(spray.angle(e(None, 100.0)))

    def test_pull_and_fb(self):
        events = [e(60.0, 100.0), e(60.0, 100.0, traj="ground_ball"), e(125.42, 100.0),
                  e(190.0, 100.0, traj="line_drive"), e(60.0, 100.0, code="F")]   # a foul isn't a batted ball
        pull, fb, n = spray.pull_and_fb(events)[1]
        self.assertEqual(n, 4)
        self.assertAlmostEqual(pull, 50.0)
        self.assertAlmostEqual(fb, 50.0)


class TestPulledAir(unittest.TestCase):
    def test_share_of_angled_balls_pulled_in_the_air(self):
        events = [e(60, 120),                          # pulled, air
                  e(60, 120, traj="ground_ball"),      # pulled, ground
                  e(125, 100, traj="line_drive"),      # straightaway
                  e(190, 120, side="L"),               # pulled for a lefty, air
                  e(None, None)]                       # no angle: not counted
        rate, n = spray.pulled_air(events)[1]
        self.assertEqual(n, 4)
        self.assertAlmostEqual(rate, 50.0)


if __name__ == "__main__":
    unittest.main()
