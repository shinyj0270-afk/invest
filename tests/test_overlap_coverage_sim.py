import math
import unittest
import numpy as np
from tools.overlap_coverage_sim import plan_returns, newey_west_se, stationary_bootstrap_means, simulate, render, METHODS


class OverlapSimTests(unittest.TestCase):
    def test_plan_returns_counts_and_sums(self):
        plans = plan_returns(np.ones(252), 63)
        self.assertEqual(len(plans), 10)  # starts 0,21,...,189
        self.assertTrue(np.allclose(plans, 63.0))
        self.assertEqual(len(plan_returns(np.ones(62), 63)), 0)

    def test_newey_west_matches_plain_variance_at_lag_zero_and_grows_with_positive_autocorrelation(self):
        rng = np.random.default_rng(1);x = rng.normal(size=400)
        self.assertAlmostEqual(newey_west_se(x, 0), math.sqrt(float(((x - x.mean()) ** 2).mean()) / len(x)), places=12)
        smooth = np.convolve(x, np.ones(6) / 6, mode='valid')  # strong positive autocorrelation by construction
        self.assertGreater(newey_west_se(smooth, 5), 1.5 * newey_west_se(smooth, 0))

    def test_stationary_bootstrap_is_reproducible_and_stays_in_range(self):
        values = np.arange(20, dtype=float)
        a = stationary_bootstrap_means(values, 4, 50, np.random.default_rng(3));b = stationary_bootstrap_means(values, 4, 50, np.random.default_rng(3))
        self.assertTrue(np.array_equal(a, b));self.assertTrue(((a >= 0) & (a <= 19)).all())

    def test_simulation_is_deterministic_for_a_seed(self):
        self.assertEqual(simulate(126, 5, reps=40, boot_reps=40, seed=7), simulate(126, 5, reps=40, boot_reps=40, seed=7))

    def test_ignoring_overlap_undercovers_and_nonoverlap_is_closer(self):
        result = simulate(252, 10, reps=150, boot_reps=100, seed=20261103)['methods']
        self.assertEqual(set(result), set(METHODS))
        self.assertLess(result['naive']['coverage'], 0.60)
        self.assertGreater(result['nonoverlap']['coverage'], result['naive']['coverage'] + 0.25)
        self.assertGreater(result['newey_west']['coverage'], result['naive']['coverage'] + 0.2)
        self.assertGreater(result['naive']['mean_width'], 0)

    def test_garch_model_runs_and_rejects_bad_inputs(self):
        self.assertEqual(simulate(63, 3, model='garch', reps=20, boot_reps=30, seed=1)['model'], 'garch')
        for kwargs in (dict(horizon=100, years=5), dict(horizon=63, years=1), dict(horizon=63, years=5, model='x'), dict(horizon=63, years=5, reps=3)):
            with self.assertRaises(ValueError):simulate(**kwargs)

    def test_render_lists_every_method(self):
        text = render([simulate(63, 3, reps=20, boot_reps=30, seed=2)])
        for method in METHODS:self.assertIn(method, text)


if __name__ == '__main__':unittest.main()
