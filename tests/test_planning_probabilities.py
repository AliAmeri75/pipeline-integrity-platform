"""Failure probabilities must describe realizations, not renewal event counts."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from inspection_planning import engine
from inspection_planning.execution import run_batched_flexible_simulation
from tests.test_inspection_planning_engine import inputs


class PlanningProbabilityTests(unittest.TestCase):
    def test_repeated_failures_count_once_for_probability_but_every_time_for_cost(self):
        joint, costs, sim = inputs()
        joint.update(cracks=[], birth_rate=1.)
        original = engine.sample_individual_joint_properties

        def properties(joints, nx, seed=0):
            props = original(joints, nx, seed)
            # Only realization 0 fails; it is replaced and fails again annually.
            props[0]['Pservice'][:] = [1., 0.]
            return props

        def burst(_names, _values, _factor, pressure, **kwargs):
            failed = int(pressure > .5)
            return (1. - 2 * failed, failed, 1., 1., 1., 1.)

        with patch.object(engine, 'sample_individual_joint_properties', side_effect=properties), \
             patch.object(engine, 'generate_num_cracks', return_value=1), \
             patch.object(engine, 'generate_initiation_times', return_value=[1.]), \
             patch.object(engine, 'reset_births_after_failure',
                          side_effect=lambda t, T, rate: [t + 1] if t < T else []), \
             patch.object(engine, 'limit_state_burst', side_effect=burst), \
             patch.object(engine, 'simulate_cracks_vectorized',
                          side_effect=lambda d, l, *args: (d, l, 0, 0)):
            result = engine.run_flexible_simulation('equidistant', 3, 1, 2,
                [joint], costs, sim, [0., 0.], 0., track_debug=False,
                decision_mode='excavation')
        np.testing.assert_allclose(result[16]['joint_burst_pofs'][0], [0., .5, .5, .5])
        np.testing.assert_allclose(result[2], [0., .5, .5, .5])
        np.testing.assert_allclose(result[4], [0., .05, .05, .05])
        np.testing.assert_allclose(result[16]['joint_burst_step_pofs'][0], [0., .5, .5, .5])
        np.testing.assert_allclose(result[7], [0., 10., 10., 10.])
        np.testing.assert_allclose(result[16]['joint_burst_event_means'][0], [0., .5, 1., 1.5])

    def test_two_cracks_in_one_joint_do_not_double_count_a_joint_failure(self):
        joint, costs, sim = inputs()
        joint['cracks'] = [dict(mean_length=40., mean_depth=1.,
            length_std=0., depth_std=0.) for _ in range(2)]

        def burst(_names, values, _factor, pressure, **kwargs):
            failed = int(values[1] >= 2.)
            return (1. - 2 * failed, failed, 1., 1., 1., 1.)

        with patch.object(engine, 'limit_state_burst', side_effect=burst), \
             patch.object(engine, 'simulate_cracks_vectorized',
                          side_effect=lambda d, l, *args: (d + 1., l, 0, 0)):
            result = engine.run_flexible_simulation('equidistant', 1, 1, 4,
                [joint], costs, sim, [0., 0.], 0., track_debug=False,
                decision_mode='excavation')
        np.testing.assert_allclose(result[16]['joint_burst_pofs'], [[0., 1.]])
        np.testing.assert_allclose(result[2], [0., 1.])
        self.assertAlmostEqual(result[7][1], costs['Cf_burst'])

    def test_leakage_repeat_events_are_counted_in_the_operating_year(self):
        joint, costs, sim = inputs()
        joint.update(cracks=[], birth_rate=1.)
        original = engine.sample_individual_joint_properties

        def properties(joints, nx, seed=0):
            props = original(joints, nx, seed)
            props[0]['WT'][:] = [.05, 100.]
            return props

        with patch.object(engine, 'sample_individual_joint_properties', side_effect=properties), \
             patch.object(engine, 'generate_num_cracks', return_value=1), \
             patch.object(engine, 'generate_initiation_times', return_value=[1.]), \
             patch.object(engine, 'reset_births_after_failure',
                          side_effect=lambda t, T, rate: [t + 1] if t < T else []), \
             patch.object(engine, 'limit_state_burst', return_value=(1., 0, 1., 1., 1., 1.)), \
             patch.object(engine, 'simulate_cracks_vectorized',
                          side_effect=lambda d, l, *args: (d, l, 0, 0)):
            result = engine.run_flexible_simulation('equidistant', 3, 1, 2,
                [joint], costs, sim, [0., 0.], 0., track_debug=False,
                decision_mode='excavation')
        np.testing.assert_allclose(result[16]['joint_leak_pofs'][0], [0., .5, .5, .5])
        np.testing.assert_allclose(result[16]['joint_leak_step_pofs'][0], [0., .5, .5, .5])
        np.testing.assert_allclose(result[3], [0., .05, .05, .05])
        np.testing.assert_allclose(result[7], [0., 1., 1., 1.])

    def test_grouped_system_and_length_normalization_match_hand_calculation(self):
        probabilities = np.array([[0., .02, .03], [0., .01, .02]])
        counts, times = [1, 3], [0., 1., 2.]
        expected = 1 - (1 - probabilities[0]) * (1 - probabilities[1]) ** 3
        system, annual = engine.grouped_system_pof_history(probabilities, counts, times, 10.)
        np.testing.assert_allclose(system, expected, atol=1e-14)
        np.testing.assert_allclose(annual[1:], np.diff(expected) / (1 - expected[:-1]) / 10.)
        same_system, per_one_km = engine.grouped_system_pof_history(probabilities, counts, times, 1.)
        np.testing.assert_allclose(same_system, system)
        np.testing.assert_allclose(per_one_km, annual * 10.)
        _, two_year_steps = engine.grouped_system_pof_history(probabilities, counts, [0., 2., 4.], 10.)
        np.testing.assert_allclose(two_year_steps, annual / 2.)

    def test_annual_probability_survives_system_cdf_rounding_to_one(self):
        system, annual = engine.grouped_system_pof_history([[0., .5, .6]], [100], [0., 1., 2.], 10.)
        self.assertEqual(system[1], 1.)  # Rounded system CDF, not zero true survival.
        self.assertAlmostEqual(annual[2], (1 - (.4 / .5) ** 100) / 10.)
        self.assertGreater(annual[2], .09)

    def test_invalid_joint_cdfs_are_rejected(self):
        for probabilities in ([[0., 1.1]], [[0., .2, .1]], [[0., float('nan')]]):
            with self.assertRaises(ValueError):
                engine.grouped_system_pof_history(probabilities, [1], np.arange(len(probabilities[0])), 10.)

    def test_annual_pof_outputs_include_route_and_per_km_metrics(self):
        steps = np.array([[0., .002, .001], [0., .001, .003]])
        counts = [1, 100]
        expected = 1 - (1 - steps[0]) * (1 - steps[1]) ** 100
        system, annual = engine.grouped_annual_failure_pofs(steps, counts, [0., 1., 2.], 10.)
        np.testing.assert_allclose(system, expected, atol=1e-14)
        np.testing.assert_allclose(annual, expected / 10., atol=1e-14)
        _, one_km = engine.grouped_annual_failure_pofs(steps, counts, [0., 1., 2.], 1.)
        np.testing.assert_allclose(one_km, annual * 10.)
        _, two_year_steps = engine.grouped_annual_failure_pofs(steps, counts, [0., 2., 4.], 10.)
        np.testing.assert_allclose(two_year_steps, annual / 2.)

    def test_whole_route_annual_safety_does_not_divide_by_route_length(self):
        step_probability = np.array([0., .008])
        whole_route_annual = engine.annualize_system_step_pofs(
            step_probability, [0., 1.])
        _, per_km_diagnostic = engine.grouped_annual_failure_pofs(
            [[0., .008]], [1], [0., 1.], 10.)
        np.testing.assert_allclose(whole_route_annual, [0., .008])
        np.testing.assert_allclose(per_km_diagnostic, [0., .0008])
        self.assertTrue(engine.exceeds_safety_criteria(
            0., whole_route_annual[1],
            {'max_annual_leak_pof': .01, 'max_annual_burst_pof': .001}))

    def test_small_non_growing_cracks_can_pass_an_interval_above_four_years(self):
        joint, costs, sim = inputs()
        joint['properties'] = {name: dict(mean=spec['mean'], std=0., distribution='Deterministic')
            for name, spec in engine.DEFAULT_PROPERTY_SPECS.items()}
        for name in ['alpha', 'C', 'Neq']:
            joint['properties'][name]['mean'] = 0.
        joint['cracks'] = [dict(mean_length=5., mean_depth=.1,
            length_std=0., depth_std=0.)]
        sim['inspection_interval'] = 10
        for mode in ['excavation', 'ili']:
            result = run_batched_flexible_simulation('equidistant', 15, 1, 8,
                [deepcopy(joint)], costs, sim, [0., 0.], 0., batch_size=3,
                decision_mode=mode)
            self.assertTrue(result[10])
            np.testing.assert_array_equal(result[3], 0.)
            np.testing.assert_array_equal(result[4], 0.)


if __name__ == '__main__':
    unittest.main()
