import unittest
import subprocess
import sys
from unittest.mock import patch

from education.pof_model import POFInputs, UncertaintyInputs
from preliminary_analysis_model import analyze_crack_profiles,analyze_deterministic_profiles
from profile_data import (
    parse_profile_workbook,
    summary_for_defect_type,
    synthetic_sample_workbook,
)


class PreliminaryAnalysisTests(unittest.TestCase):
    def test_deterministic_ui_import_with_old_cached_preliminary_module(self):
        code = '''
import sys,types
old = types.ModuleType("preliminary_analysis_model")
sys.modules["preliminary_analysis_model"] = old
from deterministic_analysis import render_deterministic_analysis
from deterministic_model import analyze_deterministic_profiles
from education.pof_model import POFInputs
from profile_data import parse_profile_workbook,synthetic_sample_workbook,summary_for_defect_type
summary,_ = parse_profile_workbook(synthetic_sample_workbook())
result = analyze_deterministic_profiles(summary_for_defect_type(summary,"Crack"),POFInputs())
assert (result.Status=="Calculated").all()
assert "POF" not in result
'''
        completed = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_deterministic_mode_never_runs_monte_carlo(self):
        summary,_ = parse_profile_workbook(synthetic_sample_workbook())
        cracks = summary_for_defect_type(summary,'Crack')
        with patch('preliminary_analysis_model.simulate_probability_of_failure',side_effect=AssertionError('Monte Carlo called')) as simulation:
            result = analyze_deterministic_profiles(cracks,POFInputs(operating_pressure_psi=936.))
        simulation.assert_not_called()
        self.assertNotIn('POF',result)
        self.assertNotIn('Monte Carlo samples',result)
        self.assertTrue((result.Status=='Calculated').all())
        self.assertTrue(((result['Burst resistance pressure (psi)']/936.-result.FPR).abs()<1e-12).all())

    def test_corrosion_fpr_is_unknown_not_crack_model(self):
        summary,_ = parse_profile_workbook(synthetic_sample_workbook())
        corrosion = summary_for_defect_type(summary,'Corrosion / metal loss')
        result = analyze_deterministic_profiles(corrosion,POFInputs())
        self.assertTrue(result.FPR.isna().all())
        self.assertTrue(result.Status.str.contains('corrosion-specific').all())

    def test_each_crack_profile_receives_pressure_fpr_and_pof(self):
        summary, _ = parse_profile_workbook(synthetic_sample_workbook())
        cracks = summary_for_defect_type(summary, "Crack")

        results = analyze_crack_profiles(
            cracks,
            POFInputs(),
            UncertaintyInputs(),
            samples=100,
            seed=17,
        )

        self.assertEqual(len(results), len(cracks))
        self.assertTrue((results["Status"] == "Calculated").all())
        self.assertTrue((results["Burst resistance pressure (psi)"] > 0.0).all())
        self.assertTrue((results["FPR"] > 0.0).all())
        self.assertTrue(results["POF"].between(0.0, 1.0).all())

    def test_invalid_profile_remains_visible_with_status(self):
        summary, _ = parse_profile_workbook(synthetic_sample_workbook())
        cracks = summary_for_defect_type(summary, "Crack").iloc[[0]].copy()
        cracks.loc[:, "Maximum depth (mm)"] = cracks["Wall thickness (mm)"]

        results = analyze_crack_profiles(
            cracks,
            POFInputs(),
            UncertaintyInputs(),
            samples=100,
        )

        self.assertEqual(
            results.loc[0, "Status"],
            "Crack depth must be below wall thickness",
        )
        self.assertTrue(results.loc[0, "POF"] is None)


if __name__ == "__main__":
    unittest.main()
