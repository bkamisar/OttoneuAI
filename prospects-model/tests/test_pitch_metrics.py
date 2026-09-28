import unittest

from psmodel import pitch_metrics as PM


def pitch(pid, typ, code="B", speed=95.0, spin=2300.0, ivb=16.0, hb=-8.0, pfx_x=-0.7, pfx_z=1.3):
    return {"pitcher": pid, "type": typ, "code": code, "speed": speed, "spin": spin, "ivb": ivb, "hb": hb,
            "pfx_x": pfx_x, "pfx_z": pfx_z}


class TestPitcherMetrics(unittest.TestCase):
    def test_primary_fastball_is_the_most_thrown_and_hb_is_a_magnitude(self):
        ps = ([pitch(1, "SI", speed=94.0, hb=-15.0) for _ in range(60)]
              + [pitch(1, "FF", speed=96.0, hb=-5.0) for _ in range(20)]
              + [pitch(1, "SL", speed=85.0, spin=2500.0) for _ in range(40)])
        m = PM.pitcher_metrics(ps)[1]
        self.assertEqual((m["fb_speed"], m["fb_hb"], m["fb_n"]), (94.0, 15.0, 60))
        self.assertEqual((m["breaking_speed"], m["breaking_spin"], m["breaking_n"]), (85.0, 2500.0, 40))
        self.assertEqual(m["pitches"], 120)

    def test_too_few_pitches_of_a_kind_leave_metrics_empty(self):
        m = PM.pitcher_metrics([pitch(2, "FF") for _ in range(49)] + [pitch(2, "CU") for _ in range(29)])[2]
        self.assertIsNone(m["fb_speed"])
        self.assertIsNone(m["fb_hb"])
        self.assertIsNone(m["breaking_spin"])

    def test_whiffs_and_variants(self):
        ps = ([pitch(3, "FF", code="S") for _ in range(10)] + [pitch(3, "FF", code="F") for _ in range(20)]
              + [pitch(3, "FF", code="T") for _ in range(10)] + [pitch(3, "FF", code="B") for _ in range(20)]
              + [pitch(3, "SV") for _ in range(30)])
        m = PM.pitcher_metrics(ps)[3]
        self.assertAlmostEqual(m["whiff_percent"], 50.0)            # default: foul tips are whiffs, 20/40
        v = {"breaking": PM.BREAKING_NARROW, "movement": "pfx", "foul_tip_is_whiff": False}
        n = PM.pitcher_metrics(ps, v)[3]
        self.assertAlmostEqual(n["whiff_percent"], 25.0)            # 10/40
        self.assertIsNone(n["breaking_speed"])                      # SV isn't in the narrow set
        self.assertAlmostEqual(n["fb_ivb"], 1.3)                    # pfx movement fields


if __name__ == "__main__":
    unittest.main()
