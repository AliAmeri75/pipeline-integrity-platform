"""Small, transparent POF model used by the ALIRIM teaching tutorial.

The failure-pressure calculation is adapted from ``CorlasP.py`` in the
``pipeline-inspection-app`` repository.  The wrapper below adds validation and
keeps the classroom simulation deliberately small.  It is not a replacement
for an operator's verified engineering model or applicable codes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


MM_TO_INCH = 0.0393701
GPA_TO_PSI = 145038.0


@dataclass(frozen=True)
class POFInputs:
    """Mean values for one classroom pipe-and-crack example."""

    diameter_in: float = 20.0
    wall_thickness_mm: float = 6.35
    flaw_length_mm: float = 40.0
    flaw_depth_mm: float = 4.0
    yield_strength_psi: float = 57200.0
    ultimate_strength_psi: float = 73920.0
    elastic_modulus_gpa: float = 210.0
    charpy_energy: float = 85.0
    operating_pressure_psi: float = 936.0
    model_factor: float = 1.27
    safety_factor: float = 2.0


@dataclass(frozen=True)
class UncertaintyInputs:
    """Standard deviations used in the introductory Monte Carlo exercise."""

    flaw_length_mm: float = 15.6
    flaw_depth_mm: float = 0.74
    wall_thickness_mm: float = 0.60
    operating_pressure_psi: float = 20.0
    model_factor: float = 0.21


def _positive(name: str, value: float) -> None:
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive.")


def corlas_failure_pressure(inputs: POFInputs) -> dict[str, float]:
    """Return CorLAS failure pressure and intermediate teaching values.

    The implementation follows the flow-stress and fracture-toughness checks
    used by the existing ALIRIM inspection model.  Inputs are converted from
    the tutorial's student-facing SI fields to the units expected by that
    calculation.
    """

    for name, value in inputs.__dict__.items():
        _positive(name, float(value))
    if inputs.flaw_depth_mm >= inputs.wall_thickness_mm:
        raise ValueError("Crack depth must be smaller than wall thickness.")
    if inputs.yield_strength_psi >= inputs.ultimate_strength_psi:
        raise ValueError("Ultimate strength must exceed yield strength.")

    diameter = inputs.diameter_in
    wall = inputs.wall_thickness_mm * MM_TO_INCH
    length = inputs.flaw_length_mm * MM_TO_INCH
    depth = inputs.flaw_depth_mm * MM_TO_INCH
    elastic_modulus = inputs.elastic_modulus_gpa * GPA_TO_PSI
    sigma_y = inputs.yield_strength_psi
    sigma_u = inputs.ultimate_strength_psi
    pi = np.pi

    sigma_flow = (sigma_y + sigma_u) / 2.0
    y_factor = 0.4 if diameter / (2.0 * wall) <= 10.0 else 0.0
    reference_area = length * wall
    effective_area = pi * length * depth / 4.0
    effective_depth = 4.0 * effective_area / (pi * length)
    geometry_ratio = length**2 / (diameter * wall)
    if geometry_ratio <= 50.0:
        folias = np.sqrt(1.0 + 0.6275 * geometry_ratio - 0.003375 * geometry_ratio**2)
    else:
        folias = 3.3 + 0.032 * geometry_ratio

    flow_pressure = sigma_flow * (
        (1.0 - effective_area / reference_area)
        / (1.0 - effective_area / (folias * reference_area))
    ) / (diameter / (2.0 * wall) - y_factor)

    hardening_exponent = (
        -0.00546
        + 0.556 * (sigma_y / sigma_u)
        - 0.547 * (sigma_y / sigma_u) ** 2
    )
    if hardening_exponent <= 0:
        raise ValueError("The strength inputs produced an invalid hardening exponent.")
    f3 = (
        3.85 * np.sqrt(1.0 / hardening_exponent) * (1.0 - hardening_exponent)
        + pi * hardening_exponent
    ) * (1.0 + hardening_exponent)
    k_value = (0.005 - sigma_y / elastic_modulus) / sigma_y ** (1.0 / hardening_exponent)
    critical_j = round(12.0 * inputs.charpy_energy / 0.124)
    z_value = min(effective_depth / length, 0.5)
    q_factor = (
        1.2581
        - 0.20589 * z_value
        - 11.493 * z_value**2
        + 29.586 * z_value**3
        - 23.584 * z_value**4
    )
    depth_ratio = effective_depth / wall
    if depth_ratio <= 0.95:
        free_surface = (
            (2.0 * wall / (pi * effective_depth))
            * np.tan(pi * effective_depth / (2.0 * wall))
            * (1.0 - 2.0 * z_value)
            + 2.0 * z_value
        )
    else:
        free_surface = (
            8.515 + (depth_ratio - 0.95) * (162.0 / wall)
        ) * (1.0 - 2.0 * z_value) + 2.0 * z_value

    sigma = sigma_y
    for _ in range(1000):
        residual = (
            q_factor
            * free_surface
            * effective_depth
            * (
                sigma**2 * pi / elastic_modulus
                + f3 * k_value * sigma ** (1.0 / hardening_exponent) * sigma
            )
            - critical_j
        )
        if abs(residual) <= 1e-3:
            break
        derivative = (
            q_factor
            * free_surface
            * effective_depth
            * (
                2.0 * pi * sigma / elastic_modulus
                + (1.0 + 1.0 / hardening_exponent)
                * f3
                * k_value
                * sigma ** (1.0 / hardening_exponent)
            )
        )
        if derivative == 0 or not np.isfinite(derivative):
            raise ValueError("The fracture-toughness calculation did not converge.")
        sigma -= residual / derivative
    else:
        raise ValueError("The fracture-toughness calculation did not converge.")

    normal_stress = sigma * (
        (1.0 - effective_area / reference_area)
        / (1.0 - effective_area / (reference_area * folias))
    )
    toughness_pressure = 2.0 * normal_stress * wall / diameter
    failure_pressure = min(flow_pressure, toughness_pressure)
    margin = inputs.model_factor * failure_pressure - inputs.operating_pressure_psi

    return {
        "failure_pressure_psi": float(failure_pressure),
        "flow_pressure_psi": float(flow_pressure),
        "toughness_pressure_psi": float(toughness_pressure),
        "safe_operating_pressure_psi": float(failure_pressure / inputs.safety_factor),
        "limit_state_margin_psi": float(margin),
        "folias_factor": float(folias),
        "q_factor": float(q_factor),
        "free_surface_factor": float(free_surface),
    }


def simulate_probability_of_failure(
    inputs: POFInputs,
    uncertainty: UncertaintyInputs,
    *,
    samples: int = 1000,
    seed: int = 7,
) -> dict[str, object]:
    """Estimate POF with a reproducible introductory Monte Carlo simulation."""

    if samples < 100 or samples > 10000:
        raise ValueError("Samples must be between 100 and 10,000.")
    for name, value in uncertainty.__dict__.items():
        if value < 0 or not np.isfinite(value):
            raise ValueError(f"{name} uncertainty cannot be negative.")

    rng = np.random.default_rng(seed)
    lengths = np.maximum(
        rng.normal(inputs.flaw_length_mm, uncertainty.flaw_length_mm, samples), 0.1
    )
    walls = np.maximum(
        rng.normal(inputs.wall_thickness_mm, uncertainty.wall_thickness_mm, samples), 0.5
    )
    depths = rng.normal(inputs.flaw_depth_mm, uncertainty.flaw_depth_mm, samples)
    depths = np.clip(depths, 0.02, 0.95 * walls)
    pressures = np.maximum(
        rng.normal(inputs.operating_pressure_psi, uncertainty.operating_pressure_psi, samples),
        1.0,
    )
    model_factors = np.maximum(
        rng.normal(inputs.model_factor, uncertainty.model_factor, samples), 0.05
    )
    yields = np.maximum(
        rng.normal(inputs.yield_strength_psi, 0.035 * inputs.yield_strength_psi, samples),
        1000.0,
    )
    ultimates = np.maximum(
        rng.normal(inputs.ultimate_strength_psi, 0.035 * inputs.ultimate_strength_psi, samples),
        yields * 1.01,
    )
    charpy = np.maximum(
        rng.normal(inputs.charpy_energy, 0.0223 * inputs.charpy_energy**1.46, samples),
        1.0,
    )
    elastic = np.maximum(
        rng.normal(inputs.elastic_modulus_gpa, 0.04 * inputs.elastic_modulus_gpa, samples),
        1.0,
    )

    failure_pressures = np.empty(samples, dtype=float)
    margins = np.empty(samples, dtype=float)
    for index in range(samples):
        sampled = POFInputs(
            diameter_in=inputs.diameter_in,
            wall_thickness_mm=float(walls[index]),
            flaw_length_mm=float(lengths[index]),
            flaw_depth_mm=float(depths[index]),
            yield_strength_psi=float(yields[index]),
            ultimate_strength_psi=float(ultimates[index]),
            elastic_modulus_gpa=float(elastic[index]),
            charpy_energy=float(charpy[index]),
            operating_pressure_psi=float(pressures[index]),
            model_factor=float(model_factors[index]),
            safety_factor=inputs.safety_factor,
        )
        result = corlas_failure_pressure(sampled)
        failure_pressures[index] = result["failure_pressure_psi"]
        margins[index] = result["limit_state_margin_psi"]

    failures = int(np.count_nonzero(margins <= 0.0))
    return {
        "probability_of_failure": failures / samples,
        "failures": failures,
        "samples": samples,
        "failure_pressures_psi": failure_pressures,
        "margins_psi": margins,
    }


def normal_pdf_curve(mean: float, standard_deviation: float) -> tuple[np.ndarray, np.ndarray]:
    """Return a normal probability-density curve for a teaching plot."""

    _positive("standard deviation", standard_deviation)
    x_values = np.linspace(mean - 4.0 * standard_deviation, mean + 4.0 * standard_deviation, 241)
    density = np.exp(-0.5 * ((x_values - mean) / standard_deviation) ** 2) / (
        standard_deviation * np.sqrt(2.0 * np.pi)
    )
    return x_values, density


def limit_state_density_curve(
    margins_psi: np.ndarray, *, maximum_bins_per_side: int = 18
) -> list[dict[str, float | int | str]]:
    """Build a density curve with zero as the exact failure boundary.

    The negative and positive samples are binned separately so no plotted bin
    can mix ``g <= 0`` failures with ``g > 0`` non-failures.  Density is
    normalized by the total sample count, so the combined area is one and the
    red-side area is the Monte Carlo POF estimate.
    """

    values = np.asarray(margins_psi, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("At least one finite limit-state margin is required.")
    if maximum_bins_per_side < 2:
        raise ValueError("At least two bins per side are required.")

    total = values.size
    records: list[dict[str, float | int | str]] = []
    sides = (
        (values[values <= 0.0], "Failed sample (g ≤ 0)", True),
        (values[values > 0.0], "Non-failed sample (g > 0)", False),
    )
    overall_scale = max(float(np.std(values)), 1.0)

    for side_values, label, is_failure in sides:
        if side_values.size == 0:
            continue
        bin_count = min(
            maximum_bins_per_side,
            max(4, int(np.ceil(np.sqrt(side_values.size)))),
        )
        if is_failure:
            lower = float(np.min(side_values))
            if lower == 0.0:
                lower = -overall_scale
            edges = np.linspace(lower, 0.0, bin_count + 1)
        else:
            upper = float(np.max(side_values))
            if upper == 0.0:
                upper = overall_scale
            edges = np.linspace(0.0, upper, bin_count + 1)

        counts, _ = np.histogram(side_values, bins=edges)
        widths = np.diff(edges)
        density = counts / (total * widths)
        for index, count in enumerate(counts):
            records.append(
                {
                    "center_psi": float((edges[index] + edges[index + 1]) / 2.0),
                    "lower_psi": float(edges[index]),
                    "upper_psi": float(edges[index + 1]),
                    "density": float(density[index]),
                    "sample_count": int(count),
                    "outcome": label,
                }
            )
    return records


def classroom_interpretation(probability_of_failure: float) -> tuple[str, str]:
    """Return a deliberately illustrative, non-code-based learning prompt."""

    if probability_of_failure < 1e-4:
        return "Lower relative result", "Monitor the assumptions and compare future ILI results."
    if probability_of_failure < 1e-3:
        return "Intermediate relative result", "Review the inputs and consider targeted inspection."
    return "Elevated relative result", "Escalate for engineering assessment and compare mitigation options."
