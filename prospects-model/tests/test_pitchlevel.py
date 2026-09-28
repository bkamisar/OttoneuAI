import math
import unittest

import numpy as np

from psmodel import pitchlevel as PL


def pe(pid, typ, hand="R", side="R", code="B", speed=95.0, spin=2300.0, ivb=16.0, hb=-8.0, ext=6.5,
       x0=-1.5, z0=6.0, ev=None, la=None, event=None):
    return {"pitcher": pid, "p_hand": hand, "b_side": side, "type": typ, "code": code, "speed": speed,
            "spin": spin, "ivb": ivb, "hb": hb, "ext": ext, "x0": x0, "z0": z0, "ev": ev, "la": la, "event": event}


class TestFrame(unittest.TestCase):
    def setUp(self):
        ps = ([pe(1, "FF") for _ in range(40)]
              + [pe(1, "SL", speed=85.0, ivb=2.0, hb=5.0, side="L") for _ in range(20)]
              + [pe(1, "EP") for _ in range(5)]                                  # eephus: dropped
              + [pe(2, "SI", hand="L", hb=12.0, x0=2.0) for _ in range(10)]      # too few for a primary fastball
              + [pe(3, "FF", code="X", ev=104.0, la=25.0, event="home_run"), pe(3, "FF", code="T")])
        self.fr = PL.season_frame(iter(ps))
        self.col = {k: i for i, k in enumerate(PL.FEATURES)}

    def test_families_and_drops(self):
        self.assertEqual(len(self.fr["fam"]), 72)
        self.assertEqual(int((self.fr["fam"] == 1).sum()), 20)

    def test_gaps_to_the_primary_fastball_and_handedness(self):
        X, c = self.fr["X"], self.col
        sl = np.where((self.fr["pitcher"] == 1) & (self.fr["fam"] == 1))[0][0]
        self.assertAlmostEqual(float(X[sl, c["d_speed"]]), -10.0, places=4)
        self.assertAlmostEqual(float(X[sl, c["d_ivb"]]), -14.0, places=4)
        self.assertAlmostEqual(float(X[sl, c["d_hb"]]), 13.0, places=4)   # 5 - (-8), right-hander: no flip
        self.assertEqual(float(X[sl, c["same_side"]]), 0.0)                # R pitcher vs L batter
        lhp = np.where(self.fr["pitcher"] == 2)[0][0]
        self.assertAlmostEqual(float(X[lhp, c["hb_arm"]]), -12.0, places=4)  # flipped for a left-hander
        self.assertAlmostEqual(float(X[lhp, c["rel_side"]]), -2.0, places=4)
        self.assertTrue(math.isnan(float(X[lhp, c["d_speed"]])))           # no primary fastball: gaps missing

    def test_outcome_flags(self):
        hr = np.where(self.fr["pitcher"] == 3)[0]
        self.assertEqual(self.fr["bip"][hr].tolist(), [True, False])
        self.assertEqual(self.fr["swing"][hr].tolist(), [True, True])
        self.assertEqual(self.fr["whiff"][hr].tolist(), [False, True])      # foul tip = whiff (hitter parity)
        self.assertAlmostEqual(float(self.fr["woba"][hr[0]]), 2.10, places=4)
        self.assertTrue(math.isnan(float(self.fr["woba"][hr[1]])))


class TestModels(unittest.TestCase):
    def test_faster_pitchers_grade_as_more_whiffs(self):
        rng = np.random.default_rng(0)
        ps = []
        for pid, speed in ((1, 90.0), (2, 99.0)):
            for _ in range(1500):
                v = speed + rng.normal(0, 1.0)
                swing = rng.random() < 0.5
                whiff = swing and rng.random() < (0.1 if speed < 95 else 0.4)
                bip = swing and not whiff and rng.random() < 0.3
                code = "S" if whiff else ("X" if bip else ("F" if swing else "B"))
                ps.append(pe(pid, "FF", code=code, speed=v, ev=90.0 + rng.normal(0, 8) if bip else None,
                             la=rng.normal(12, 15) if bip else None, event="single" if bip and rng.random() < 0.3
                             else ("field_out" if bip else None)))
        fr = PL.season_frame(iter(ps))
        models = PL.train([fr])
        feats = PL.pitcher_features(models, fr)
        self.assertEqual(feats[1]["pitches"], 1500)
        self.assertGreater(feats[2]["pl_whiff"], feats[1]["pl_whiff"])
        self.assertTrue(np.isfinite(feats[1]["pl_damage"]))


if __name__ == "__main__":
    unittest.main()
