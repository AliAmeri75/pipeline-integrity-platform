import unittest

import numpy as np

from education.pof_model import (
    DistributionSpec,
    POFInputs,
    UncertaintyInputs,
    corlas_failure_pressure,
    deterministic_fpr_boundary,
    deterministic_pressure_sweep,
    evaluate_deterministic_cracks,
    failure_pressure_ratio,
    limit_state_density_curve,
    normal_pdf_curve,
    recommended_distribution_specs,
    simulate_probability_of_failure,
)


class EducationalPOFTests(unittest.TestCase):
    def test_failure_pressure_is_positive_and_above_operating_pressure(self):
        inputs = POFInputs()
        result = corlas_failure_pressure(inputs)
        self.assertGreater(result["failure_pressure_psi"], inputs.operating_pressure_psi)
        self.assertGreater(result["folias_factor"], 1.0)

    def test_failure_pressure_ratio_uses_operating_pressure(self):
        inputs = POFInputs(operating_pressure_psi=936.0)
        result = corlas_failure_pressure(inputs)
        self.assertAlmostEqual(
            failure_pressure_ratio(inputs),
            result["failure_pressure_psi"] / 936.0,
            places=12,
        )

    def test_deterministic_pressure_decreases_with_crack_size(self):
        inputs = POFInputs()
        depth_sweep = deterministic_pressure_sweep(
            inputs, "flaw_depth_mm", [1.0, 3.0, 5.0]
        )
        length_sweep = deterministic_pressure_sweep(
            inputs, "flaw_length_mm", [10.0, 80.0, 200.0]
        )
        self.assertGreater(
            depth_sweep[0]["failure_pressure_psi"],
            depth_sweep[-1]["failure_pressure_psi"],
        )
        self.assertGreater(
            length_sweep[0]["failure_pressure_psi"],
            length_sweep[-1]["failure_pressure_psi"],
        )

    def test_deterministic_fpr_boundary_matches_requested_ratio(self):
        inputs = POFInputs()
        boundary = deterministic_fpr_boundary(
            inputs, 1.0, maximum_length_mm=300.0, length_points=21
        )
        self.assertGreater(len(boundary), 5)
        middle = boundary[len(boundary) // 2]
        boundary_inputs = POFInputs(
            **{
                **inputs.__dict__,
                "flaw_length_mm": middle["crack_length_mm"],
                "flaw_depth_mm": middle["crack_depth_mm"],
            }
        )
        self.assertAlmostEqual(failure_pressure_ratio(boundary_inputs), 1.0, places=6)
        self.assertLess(middle["crack_depth_mm"], inputs.wall_thickness_mm)

    def test_uploaded_crack_list_receives_pressure_and_fpr(self):
        inputs = POFInputs()
        results = evaluate_deterministic_cracks(
            inputs,
            crack_lengths_mm=[20.0, 40.0, 80.0],
            crack_depths_mm=[2.0, 3.0, 4.0],
        )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["crack_number"], 1)
        self.assertGreater(results[0]["failure_pressure_psi"], 0.0)
        self.assertAlmostEqual(
            results[0]["fpr"],
            results[0]["failure_pressure_psi"] / inputs.operating_pressure_psi,
            places=12,
        )
        self.assertGreater(results[0]["fpr"], results[-1]["fpr"])

    def test_uploaded_crack_depth_must_be_below_wall_thickness(self):
        with self.assertRaisesRegex(ValueError, "smaller than wall thickness"):
            evaluate_deterministic_cracks(
                POFInputs(), crack_lengths_mm=[40.0], crack_depths_mm=[6.35]
            )

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

    def test_every_pipeline_parameter_has_a_recommended_distribution(self):
        inputs = POFInputs()
        specs = recommended_distribution_specs(inputs)
        self.assertEqual(set(specs), set(inputs.__dict__))

    def test_all_parameters_can_be_deterministic(self):
        inputs = POFInputs()
        specs = {name: DistributionSpec() for name in inputs.__dict__}
        result = simulate_probability_of_failure(
            inputs, variable_specs=specs, samples=100, seed=11
        )
        for name, values in result["sampled_inputs"].items():
            self.assertTrue(np.allclose(values, getattr(inputs, name)), name)

    def test_student_selected_distributions_respect_their_definitions(self):
        inputs = POFInputs()
        result = simulate_probability_of_failure(
            inputs,
            variable_specs={
                "diameter_in": DistributionSpec(
                    "Uniform", minimum=18.0, maximum=22.0
                ),
                "wall_thickness_mm": DistributionSpec(
                    "Normal", standard_deviation=0.2
                ),
                "flaw_length_mm": DistributionSpec(
                    "Lognormal", standard_deviation=8.0
                ),
                "flaw_depth_mm": DistributionSpec(
                    "Triangular", minimum=2.5, mode=4.0, maximum=5.5
                ),
            },
            samples=100,
            seed=13,
        )
        diameters = result["sampled_inputs"]["diameter_in"]
        self.assertGreaterEqual(float(diameters.min()), 18.0)
        self.assertLessEqual(float(diameters.max()), 22.0)
        self.assertGreater(float(np.std(diameters)), 0.0)
        self.assertTrue(np.all(result["sampled_inputs"]["flaw_length_mm"] > 0.0))
        depths = result["sampled_inputs"]["flaw_depth_mm"]
        self.assertGreaterEqual(float(depths.min()), 2.5)
        self.assertLessEqual(float(depths.max()), 5.5)


if __name__ == "__main__":
    unittest.main()
