"""Safety diagnostics expose the governing year and counted joint groups."""
import unittest

from inspection_planning.diagnostics import interval_safety_rows, joint_safety_rows


class PlanningDiagnosticsTests(unittest.TestCase):
    def result(self):
        return dict(interval=5, times=[0., 1., 2.],
            leak_hazard=[0., .001, .002], burst_hazard=[0., .0001, .002],
            max_annual_leak_pof=.01, max_annual_burst_pof=.001)

    def test_rejected_interval_identifies_burst_and_the_first_exceeded_year(self):
        row = interval_safety_rows([self.result()], 'Prior excavation')[0]
        self.assertEqual(row['Status'], 'Unsafe')
        self.assertEqual(row['First limit exceedance (year)'], 2.)
        self.assertEqual(row['Exceeded criterion'], 'Burst')
        self.assertEqual(row['Peak annual PfB / km-year'], .002)

    def test_safe_interval_has_no_exceedance_or_rejected_mode(self):
        result = self.result()
        result['burst_hazard'] = [0., .0001, .001]
        row = interval_safety_rows([result], 'ILI-informed')[0]
        self.assertEqual(row['Status'], 'Safe')
        self.assertIsNone(row['First limit exceedance (year)'])
        self.assertEqual(row['Exceeded criterion'], 'None')

    def test_clean_groups_keep_their_count_and_are_resolved_by_name(self):
        joints = [dict(name='Cracked', count=1, cracks=[{}, {}]),
                  dict(name='Initially clean', count=100, cracks=[])]
        result = dict(joint_names=['Initially clean', 'Cracked'], retained_samples=10000,
            times=[0., 1., 2.],
            joint_leak_step_pofs=[[0., 0., 0.], [0., 0., 0.]],
            joint_burst_step_pofs=[[0., .0001, .0001], [0., .001, .003]])
        rows = joint_safety_rows(result, joints, 10.)
        self.assertEqual(rows[0]['Joint / group'], 'Initially clean')
        self.assertEqual(rows[0]['Physical joints represented'], 100)
        self.assertAlmostEqual(rows[0]['Peak group PfB / km-year'], (1 - .9999**100) / 10.)
        self.assertAlmostEqual(rows[0]['Approx. one-event increment / km'], .001)
        self.assertEqual(rows[1]['Initial cracks per joint'], 2)
        self.assertAlmostEqual(rows[1]['Peak group PfB / km-year'], .003 / 10.)


if __name__ == '__main__':
    unittest.main()
