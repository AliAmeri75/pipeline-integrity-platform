import unittest

import numpy as np

from education.pof_model import (
    POFInputs,
    UncertaintyInputs,
    corlas_failure_pressure,
    limit_state_density_curve,
    normal_pdf_curve,
    simulate_probability_of_failure,
)


class EducationalPOFTests(unittest.TestCase):
    def test_failure_pressure_is_positive_and_above_operating_pressure(self):
        inputs = POFInputs()
        result = corlas_failure_pressure(inputs)
        self.assertGreater(result["failure_pressure_psi"], inputs.operating_pressure_psi)
        self.assertGreater(result["folias_factor"], 1.0)

    def test_simulation_is_reproducible_and_bounded(self):
        inputs = POFInputs(flaw_depth_mm=5.5)
        uncertainty = UncertaintyInputs()
        first = simulate_probability_of_failure(inputs, uncertainty, samples=250, seed=9)
        second = simulate_probability_of_failure(inputs, uncertainty, samples=250, seed=9)
        self.assertEqual(first["failures"], second["failures"])
        self.assertGreaterEqual(first["probability_of_failure"], 0.0)
        self.assertLessEqual(first["probability_of_failure"], 1.0)

    def test_probability_density_integrates_to_approximately_one(self):
        x_values, density = normal_pdf_curve(4.0, 0.74)
        self.assertAlmostEqual(float(np.trapezoid(density, x_values)), 1.0, places=3)

    def test_limit_state_curve_highlights_all_failed_samples(self):
        margins = np.array([-12.0, -3.0, 0.0, 2.0, 4.0, 18.0])
        records = limit_state_density_curve(margins, maximum_bins_per_side=4)
        failed_count = sum(
            record["sample_count"]
            for record in records
            if record["outcome"] == "Failed sample (g ≤ 0)"
        )
        area = sum(
            record["density"] * (record["upper_psi"] - record["lower_psi"])
            for record in records
        )
        self.assertEqual(failed_count, 3)
        self.assertAlmostEqual(float(area), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
