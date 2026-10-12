import unittest

import numpy as np

from education.pof_model import (
    POFInputs,
    UncertaintyInputs,
    corlas_failure_pressure,
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


if __name__ == "__main__":
    unittest.main()
