import unittest

import numpy as np

from psmodel import interactions


class Stub:
    """f = x0 * x1 + x2: one pure interaction (0, 1), everything else additive."""
    def predict(self, X):
        return X[:, 0] * X[:, 1] + X[:, 2]


class TestH(unittest.TestCase):
    def setUp(self):
        self.X = np.random.default_rng(0).uniform(-1, 1, size=(60, 3))

    def test_product_term_is_an_interaction(self):
        self.assertGreater(interactions.h_stat(Stub(), self.X, 0, 1), 0.2)

    def test_additive_pair_is_not(self):
        self.assertLess(interactions.h_stat(Stub(), self.X, 0, 2), 1e-9)

    def test_top_pairs_ranks_the_product_first(self):
        top = interactions.top_pairs(Stub(), self.X, ["a", "b", "c"], n=3)
        self.assertEqual((top[0][1], top[0][2]), ("a", "b"))
        self.assertEqual(len(top), 3)


if __name__ == "__main__":
    unittest.main()
