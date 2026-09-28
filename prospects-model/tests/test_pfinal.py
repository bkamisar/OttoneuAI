import json
import os
import tempfile
import unittest

from psmodel import pfinal as PF


class TestRules(unittest.TestCase):
    def test_calibration_error_is_the_size_weighted_gap(self):
        self.assertAlmostEqual(PF.calibration_error([(0.1, 0.0, 10), (0.5, 0.2, 30)]), (1.0 + 9.0) / 40)

    def test_logit_only_if_strictly_better_on_both(self):
        t, l = {"top50": 0.10, "calib": 0.02}, {"top50": 0.12, "calib": 0.01}
        self.assertEqual(PF.soon_kind(t, l), "logit")
        self.assertEqual(PF.soon_kind(t, dict(l, top50=0.10)), "gbm")        # tie on top-50 keeps trees
        self.assertEqual(PF.soon_kind(t, dict(l, calib=0.02)), "gbm")        # tie on calibration keeps trees

    def test_wilson_interval(self):
        lo, hi = PF.wilson(10, 100)
        self.assertAlmostEqual(lo, 0.0552, places=3)
        self.assertAlmostEqual(hi, 0.1744, places=3)

    def test_percent_ok_needs_top_bucket_and_overall(self):
        good = [(0.01, 0.01, 100)] * 9 + [(0.10, 0.10, 100)]
        self.assertTrue(PF.percent_ok(good))
        self.assertFalse(PF.percent_ok(good[:-1] + [(0.25, 0.10, 100)]))      # top bucket overconfident
        self.assertFalse(PF.percent_ok([(0.05, 0.0, 100)] * 9 + [(0.10, 0.10, 100)]))   # overall too high


class TestFrozen(unittest.TestCase):
    def test_written_once_then_only_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dec.json")
            self.assertIsNone(PF.load_frozen(path))
            PF.freeze(path, {"soon_kind": "gbm"})
            self.assertEqual(PF.load_frozen(path), {"soon_kind": "gbm"})
            with self.assertRaises(SystemExit):
                PF.freeze(path, {"soon_kind": "logit"})
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["soon_kind"], "gbm")


if __name__ == "__main__":
    unittest.main()
