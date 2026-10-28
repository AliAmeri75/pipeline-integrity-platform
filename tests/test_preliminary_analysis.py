import unittest

from education.pof_model import POFInputs, UncertaintyInputs
from preliminary_analysis_model import analyze_crack_profiles
from profile_data import (
    parse_profile_workbook,
    summary_for_defect_type,
    synthetic_sample_workbook,
)


class PreliminaryAnalysisTests(unittest.TestCase):
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
