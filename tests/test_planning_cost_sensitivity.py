"""Cost sensitivity uses annual event counts, weighted by the physical joints."""
import unittest

import numpy as np

from inspection_planning.comparison import select_optimal_result
from inspection_planning.cost_sensitivity import annual_counts, cost_quantities, reprice


class CostSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.times = np.array([0, 1, 2])
        self.joints = [
            {"name": "A", "count": 2, "costs": {"Cf_leak": 0., "Cf_burst": 30.}},
            {"name": "B", "count": 4},
        ]
        self.debug = {
            "joint_names": ["A", "B"],
            "type2_repair_means": np.array([0, .5, 1.]),
            "joint_leak_step_pofs": np.array([[0, .1, .1], [0, .2, 0]]),
            "joint_burst_step_pofs": np.array([[0, .2, .1], [0, .1, .1]]),
        }
        self.raw = [None] * 17
        self.raw[0], self.raw[5] = self.times, [2]
        self.raw[14], self.raw[16] = np.array([0., 2., 1.]), self.debug
        self.prices = dict(Cr1=1., Cr2=2., Cf_leak=3., Cf_burst=10.,
                           segment_leak=1., segment_burst=.5, rate=.1,
                           pipe_length_km=10., inspection_cost_per_km=.2)

    def plan(self, ili):
        return dict(times=self.times, cost_quantities=cost_quantities(
            self.raw, self.joints, self.prices, ili), cpp=np.zeros(3), total_cpp=0.,
            is_safe=True, **self.debug)

    def test_segment_costs_and_annual_count_reconciliation(self):
        plan = self.plan(ili=True)
        result = reprice(plan, self.prices)
        counts = annual_counts(result, self.joints, 10.)
        np.testing.assert_allclose(counts["Leaks"], [0, 1., .2])
        np.testing.assert_allclose(counts["Bursts"], [0, .8, .6])
        np.testing.assert_allclose(counts["Type 1 only"], [0, 1.5, 0])
        np.testing.assert_allclose(counts["Type 2"], [0, .5, 1])
        np.testing.assert_array_equal(counts["ILI runs"], [0, 0, 1])
        self.assertAlmostEqual(result["failure_cost"], 12.4 / 1.1 + 7. / 1.1**2)
        self.assertAlmostEqual(result["repair_cost"], 3. / 1.1 + 3. / 1.1**2)
        self.assertAlmostEqual(result["inspection_cost"], 2. / 1.1**2)
        np.testing.assert_allclose(result["cpp"], [0, 15.4 / 1.1, 12. / 1.1**2])
        self.assertAlmostEqual(result["total_cpp"], sum(result["cpp"]))
        np.testing.assert_array_equal(plan["cpp"], 0.)
        self.assertEqual(reprice(self.plan(ili=False), self.prices)["inspection_cost"], 0.)

    def test_reranking_selects_only_safe_plans(self):
        first, second, unsafe = [self.plan(ili=True) for _ in range(3)]
        first["cost_quantities"]["inspection_cost_per_km"] = np.array([0., 10., 10.])
        first["cost_quantities"]["Cr1"] = first["cost_quantities"]["Cr2"].copy()
        unsafe.update(is_safe=False)
        plans = [dict(p, name=name) for name, p in zip(("two runs", "one run", "unsafe"), (first, second, unsafe))]
        for price, expected in [(0., "two runs"), (10., "one run")]:
            repriced = [reprice(p, dict(self.prices, inspection_cost_per_km=price)) for p in plans]
            repriced[-1]["total_cpp"] = 0.
            optimum, found = select_optimal_result(repriced)
            self.assertTrue(found)
            self.assertEqual(optimum["name"], expected)
        self.assertEqual(select_optimal_result([unsafe]), (None, False))
