import unittest
import numpy as np
from psmodel import evaluate


def synth(n_players, family_matters, seed=7):
    """One row per player. Base feature b always predicts; family feature q
    predicts only when family_matters."""
    rng = np.random.default_rng(seed)
    b, q, e = rng.normal(size=n_players), rng.normal(size=n_players), rng.normal(size=n_players)
    y = 0.6 * b + (1.2 * q if family_matters else 0.0) + 0.8 * e
    cut = np.quantile(y, 0.8)
    return [{"player_id": i, "f": {"b": float(b[i]), "q": float(q[i])}, "target": float(y[i]),
             "weight": 1.0, "useful": bool(y[i] >= cut)} for i in range(n_players)]


class TestFolds(unittest.TestCase):
    def test_a_player_never_spans_folds(self):
        rows = [{"player_id": p} for p in (1, 1, 2, 3, 3, 3, 4)]
        folds = evaluate.assign_folds(rows, k=2, seed=0)
        by = {}
        for r, f in zip(rows, folds):
            by.setdefault(r["player_id"], set()).add(f)
        self.assertTrue(all(len(s) == 1 for s in by.values()))


class TestTopN(unittest.TestCase):
    def test_counts_players_not_rows(self):
        rows = [{"player_id": 1, "useful": True}, {"player_id": 1, "useful": True},
                {"player_id": 2, "useful": False}]
        self.assertAlmostEqual(evaluate.top_n_precision(rows, [0.9, 0.8, 0.7], n=2), 0.5)


class TestGuard(unittest.TestCase):
    def test_constant_feature_is_a_phantom(self):
        rows = [{"f": {"a": 1.0, "c": 5.0}}, {"f": {"a": 2.0, "c": 5.0}}]
        with self.assertRaises(ValueError):
            evaluate.guard_features(rows, ["a", "c"])

    def test_missing_value_raises(self):
        with self.assertRaises(ValueError):
            evaluate.guard_features([{"f": {"a": 1.0}}, {"f": {"a": None}}], ["a"])


class TestHarnessIsHonest(unittest.TestCase):
    """The harness itself is tested the way the parity gate was: it must adopt
    a feature that truly predicts and refuse one that is pure noise."""

    def test_adopts_a_real_signal(self):
        res = evaluate.compare(synth(1000, True), ["b"], ["q"], seeds=10, top_n=50)
        ok, wins = evaluate.adopt(res)
        self.assertTrue(ok, f"only {wins}/10 wins for a genuinely predictive feature")

    def test_rejects_pure_noise(self):
        res = evaluate.compare(synth(1000, False), ["b"], ["q"], seeds=10, top_n=50)
        ok, wins = evaluate.adopt(res)
        self.assertFalse(ok, f"adopted pure noise ({wins}/10 wins)")

    def test_trait_ranking_orders_by_weight(self):
        ranked = evaluate.trait_ranking(synth(1000, True), ["b", "q"])
        self.assertEqual(ranked[0][0], "q")


def synth_interaction(n=1500, seed=11):
    """q matters ONLY through its interaction with b: y = b + 1.5*q*b + noise.
    Its marginal correlation with y is ~0, so a linear model sees nothing."""
    rng = np.random.default_rng(seed)
    b, q, e = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
    y = b + 1.5 * q * b + 0.5 * e
    cut = np.quantile(y, 0.8)
    return [{"player_id": i, "f": {"b": float(b[i]), "q": float(q[i])}, "target": float(y[i]),
             "weight": 1.0, "useful": bool(y[i] >= cut)} for i in range(n)]


class TestInteraction(unittest.TestCase):
    """The user's case: 'whiffs a lot, but elite exit velo -> actually great'.
    A feature whose value is purely conditional must not be thrown away."""

    def test_linear_sees_little_trees_catch_it(self):
        rows = synth_interaction()
        lin = evaluate.compare(rows, ["b"], ["q"], kind="ridge")
        gain = sum(r["rho_fam"] - r["rho_base"] for r in lin) / len(lin)
        self.assertLess(gain, 0.02, "ridge should see almost nothing in a purely interactive effect")
        ok, wins = evaluate.adopt(evaluate.compare(rows, ["b"], ["q"], kind="gbm"))
        self.assertTrue(ok, f"gbm found the interaction in only {wins}/10 shuffles")


if __name__ == "__main__":
    unittest.main()
