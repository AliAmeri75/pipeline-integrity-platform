"""Spatial planning output must expand the exact shared joint populations."""
import unittest

import numpy as np

from assessment_project import sample_project
from profile_map import point_at_chainage, route_length_km
from planning_project import planning_handoff
from inspection_planning.risk_map import sliding_window_reliability, reliability_map


class PlanningRiskMapTests(unittest.TestCase):
    def setUp(self):
        self.handoff = planning_handoff(sample_project())

    def result(self, handoff=None):
        h = handoff or self.handoff
        return dict(times=[0., 1., 2.], joint_names=[j['name'] for j in h['joints']],
            joint_leak_pofs=np.zeros((len(h['joints']), 3)),
            joint_burst_pofs=np.zeros((len(h['joints']), 3)),
            max_annual_leak_pof=.01, max_annual_burst_pof=.001)

    def test_default_route_cracks_and_white_legend_are_retained(self):
        windows, spatial = sliding_window_reliability(self.result(), self.handoff)
        self.assertEqual(len(spatial), 834)
        self.assertAlmostEqual(spatial.end_km.iloc[-1], 10.)
        self.assertEqual(spatial.initial_cracks.sum(), 3)
        self.assertTrue(spatial.category.eq('Low').all())
        self.assertAlmostEqual(windows.start_km.iloc[-1], 9.)
        rendered = reliability_map(self.handoff['project']['route'], spatial).get_root().render()
        self.assertIn('Selected Pf Limits', rendered)
        self.assertIn('background:white', rendered)
        self.assertIn('no consequences included', rendered)

    def test_clean_group_probability_only_appears_in_its_segment(self):
        result = self.result()
        index = result['joint_names'].index('Initially crack-free · Segment 10')
        result['joint_burst_pofs'][index] = [0., .0001, .0002]
        windows, spatial = sliding_window_reliability(result, self.handoff)
        self.assertEqual(windows.peak_annual_burst_pof.iloc[0], 0.)
        self.assertGreater(windows.peak_annual_burst_pof.iloc[-1], .001)
        self.assertEqual(spatial.category.iloc[0], 'Low')
        self.assertEqual(spatial.category.iloc[-1], 'High')

    def test_multiple_cracks_on_one_joint_do_not_duplicate_joint_probability(self):
        project = sample_project()
        project['summary'].loc[1, 'Feature location (m)'] = 501.
        handoff = planning_handoff(project)
        result = self.result(handoff)
        index = result['joint_names'].index('Joint 42')
        result['joint_burst_pofs'][index] = [0., .002, .004]
        windows, spatial = sliding_window_reliability(result, handoff)
        self.assertEqual(spatial.loc[spatial.joint_id.eq('Joint 42'), 'initial_cracks'].iloc[0], 2)
        self.assertAlmostEqual(windows.peak_annual_burst_pof.iloc[0], .002/.998)

    def test_group_order_is_resolved_by_name_and_missing_groups_are_rejected(self):
        result = self.result()
        result['joint_burst_pofs'][0] = [0., .001, .002]
        before, _ = sliding_window_reliability(result, self.handoff)
        result['joint_names'].reverse()
        result['joint_leak_pofs'] = result['joint_leak_pofs'][::-1]
        result['joint_burst_pofs'] = result['joint_burst_pofs'][::-1]
        after, _ = sliding_window_reliability(result, self.handoff)
        np.testing.assert_array_equal(before.peak_annual_burst_pof, after.peak_annual_burst_pof)
        result['joint_names'][0] = 'Wrong group'
        with self.assertRaisesRegex(ValueError, 'do not match'):
            sliding_window_reliability(result, self.handoff)

    def test_invalid_cumulative_probabilities_are_rejected(self):
        result = self.result()
        result['joint_burst_pofs'][0] = [0., .9, 1.1]
        with self.assertRaisesRegex(ValueError, 'Repeated-failure'):
            sliding_window_reliability(result, self.handoff)

    def test_short_route_uses_actual_length_and_includes_final_partial_joint(self):
        project = sample_project()
        project['route'] = [project['route'][0], point_at_chainage(project['route'], .061)]
        project['segments'] = project['segments'].iloc[:1].copy()
        project['segments'].loc[0, 'end_km'] = route_length_km(project['route'])
        project['uncertainties'] = project['uncertainties'].query('section_id == 1').copy()
        project['summary']['Feature location (m)'] = [1., 2., 3.]
        handoff = planning_handoff(project)
        windows, spatial = sliding_window_reliability(self.result(handoff), handoff)
        self.assertEqual(len(windows), 1)
        self.assertEqual(len(spatial), 6)
        self.assertAlmostEqual(windows.section_length_km.iloc[0], handoff['pipeline_length_km'])
        self.assertAlmostEqual(spatial.end_km.iloc[-1], handoff['pipeline_length_km'])
        self.assertEqual(spatial.initial_cracks.sum(), 3)

    def test_zero_limit_is_supported_without_division_warning(self):
        result = self.result()
        result['max_annual_burst_pof'] = 0.
        result['joint_burst_pofs'][0] = [0., .001, .002]
        with np.errstate(all='raise'):
            windows, _ = sliding_window_reliability(result, self.handoff)
        self.assertTrue(np.isinf(windows.limit_ratio).any())

    def test_map_uses_operating_year_events_including_repeat_failures(self):
        result = self.result()
        result['joint_leak_step_pofs'] = np.zeros_like(result['joint_leak_pofs'])
        result['joint_burst_step_pofs'] = np.zeros_like(result['joint_burst_pofs'])
        result['joint_burst_pofs'][0] = [0., .5, .75]
        result['joint_burst_step_pofs'][0] = [0., .5, .75]
        windows, _ = sliding_window_reliability(result, self.handoff)
        self.assertAlmostEqual(windows.peak_annual_burst_pof.iloc[0], .75)
        self.assertEqual(windows.burst_peak_year.iloc[0], 2.)

    def test_invalid_operating_step_probabilities_are_rejected(self):
        result = self.result()
        result['joint_burst_step_pofs'] = np.zeros_like(result['joint_burst_pofs'])
        result['joint_burst_step_pofs'][0,1] = 1.1
        with self.assertRaisesRegex(ValueError, 'operating-step'):
            sliding_window_reliability(result, self.handoff)


if __name__ == '__main__':
    unittest.main()
