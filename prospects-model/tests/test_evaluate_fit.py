import unittest

import numpy as np

from psmodel import evaluate


class TestFitPredict(unittest.TestCase):
    def test_fit_then_predict_orders_rows(self):
        rng = np.random.default_rng(0)
        rows = [{"player_id": i, "f": {"x": float(x), "z": float(z)}, "target": 2 * x + 0.1 * z, "weight": 1.0}
                for i, (x, z) in enumerate(rng.normal(size=(200, 2)))]
        for kind in evaluate.KINDS:
            m = evaluate.fit(rows, ["x", "z"], kind)
            p = evaluate.predict(m, [{"f": {"x": -1.0, "z": 0.0}}, {"f": {"x": 1.0, "z": 0.0}}], ["x", "z"])
            self.assertLess(p[0], p[1], kind)

    def test_fit_refuses_phantom_feature(self):
        rows = [{"player_id": i, "f": {"x": float(i), "c": 1.0}, "target": float(i), "weight": 1.0}
                for i in range(10)]
        with self.assertRaises(ValueError):
            evaluate.fit(rows, ["x", "c"])


if __name__ == "__main__":
    unittest.main()
