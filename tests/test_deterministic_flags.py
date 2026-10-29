import unittest
import pandas as pd
from deterministic_flags import flag_profiles, fpr_distance_figure, SEVERE_LABEL
from deterministic_model import analyze_deterministic_profiles
from education.pof_model import POFInputs
from profile_data import synthetic_sample_workbook, parse_profile_workbook, summary_for_defect_type


class ScreeningTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({
            'Profile ID': ['boundary', 'low-fpr', 'deep', 'missing'],
            'FPR': [1.1, 1.09, 1.3, float('nan')],
            'Defect depth (mm)': [5, 4, 5.1, float('nan')],
            'Wall thickness (mm)': [10]*4,
            'Status': ['Calculated']*3+['Unavailable'],
            'Distance from start (km)': [0, 1, 2, 3]})

    def test_strict_thresholds_and_or_rule(self):
        result = flag_profiles(self.data())
        self.assertEqual(result.Severe.tolist(), [False, True, True, False])
        self.assertEqual(result.iloc[3]['Screening status'], 'Assessment incomplete')

    def test_circle_and_labels(self):
        figure = fpr_distance_figure(self.data())
        self.assertEqual(figure.data[1].marker.symbol, 'circle-open')
        self.assertIsNone(figure.data[1].text)
        self.assertEqual(figure.data[1].mode,'markers')
        self.assertEqual(figure.data[1].name,SEVERE_LABEL)
        self.assertTrue(figure.data[1].showlegend)
        self.assertIn(SEVERE_LABEL,figure.data[1].hovertemplate)
        self.assertEqual(list(figure.data[1].customdata[:, 0]), ['low-fpr', 'deep'])

    def test_sample_three_is_critical_at_default_inputs(self):
        summary, _ = parse_profile_workbook(synthetic_sample_workbook())
        result = flag_profiles(analyze_deterministic_profiles(
            summary_for_defect_type(summary, 'Crack'), POFInputs()))
        third = result.loc[result['Profile ID']=='SYN-003'].iloc[0]
        self.assertLess(third.FPR, 1.1)
        self.assertGreater(third.FPR, 0)
        self.assertGreater(third['Depth / WT'], .5)
        self.assertTrue(third.Severe)


if __name__ == '__main__':
    unittest.main()
