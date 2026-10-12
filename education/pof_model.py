"""Small, transparent POF model used by the ALIRIM teaching tutorial.

The failure-pressure calculation is adapted from ``CorlasP.py`` in the
``pipeline-inspection-app`` repository.  The wrapper below adds validation and
keeps the classroom simulation deliberately small.  It is not a replacement
for an operator's verified engineering model or applicable codes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

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


@dataclass(frozen=True)
class DistributionSpec:
    """Student-selected probability model for one pipeline parameter."""

    distribution: str = "Deterministic"
    standard_deviation: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    mode: float | None = None


SUPPORTED_DISTRIBUTIONS = (
    "Deterministic",
    "Normal",
    "Lognormal",
    "Uniform",
    "Triangular",
)


def recommended_distribution_specs(
    inputs: POFInputs,
    uncertainty: UncertaintyInputs | None = None,
) -> dict[str, DistributionSpec]:
    """Return the tutorial's recommended starting probability models.

    These defaults reproduce the uncertainty assumptions used by the original
    classroom exercise while making every ``POFInputs`` parameter configurable.
    """

    uncertainty = uncertainty or UncertaintyInputs()
    return {
        "diameter_in": DistributionSpec(),
        "wall_thickness_mm": DistributionSpec(
            "Normal", standard_deviation=uncertainty.wall_thickness_mm
        ),
        "flaw_length_mm": DistributionSpec(
            "Normal", standard_deviation=uncertainty.flaw_length_mm
        ),
        "flaw_depth_mm": DistributionSpec(
            "Normal", standard_deviation=uncertainty.flaw_depth_mm
        ),
        "yield_strength_psi": DistributionSpec(
            "Normal", standard_deviation=0.035 * inputs.yield_strength_psi
        ),
        "ultimate_strength_psi": DistributionSpec(
            "Normal", standard_deviation=0.035 * inputs.ultimate_strength_psi
        ),
        "elastic_modulus_gpa": DistributionSpec(
            "Normal", standard_deviation=0.04 * inputs.elastic_modulus_gpa
        ),
        "charpy_energy": DistributionSpec(
            "Normal", standard_deviation=0.0223 * inputs.charpy_energy**1.46
        ),
        "operating_pressure_psi": DistributionSpec(
            "Normal", standard_deviation=uncertainty.operating_pressure_psi
        ),
        "model_factor": DistributionSpec(
            "Normal", standard_deviation=uncertainty.model_factor
        ),
        "safety_factor": DistributionSpec(),
    }


def _sample_distribution(
    rng: np.random.Generator,
    center: float,
    spec: DistributionSpec,
    samples: int,
    *,
    name: str,
) -> np.ndarray:
    """Sample one supported distribution and enforce a positive physical value."""

    distribution = spec.distribution
    if distribution not in SUPPORTED_DISTRIBUTIONS:
        raise ValueError(f"Unsupported distribution for {name}: {distribution}.")
    _positive(name, center)

    if distribution == "Deterministic":
        values = np.full(samples, center, dtype=float)
    elif distribution in {"Normal", "Lognormal"}:
        standard_deviation = float(spec.standard_deviation)
        _positive(f"{name} standard deviation", standard_deviation)
        if distribution == "Normal":
            values = rng.normal(center, standard_deviation, samples)
        else:
            variance_ratio = (standard_deviation / center) ** 2
            sigma = np.sqrt(np.log1p(variance_ratio))
            mu = np.log(center) - 0.5 * sigma**2
            values = rng.lognormal(mu, sigma, samples)
    elif distribution == "Uniform":
        if spec.minimum is None or spec.maximum is None:
            raise ValueError(f"{name} uniform distribution needs minimum and maximum values.")
        minimum = float(spec.minimum)
        maximum = float(spec.maximum)
        if not np.isfinite(minimum) or not np.isfinite(maximum) or minimum >= maximum:
            raise ValueError(f"{name} minimum must be smaller than its maximum.")
        values = rng.uniform(minimum, maximum, samples)
    else:
        if spec.minimum is None or spec.maximum is None or spec.mode is None:
            raise ValueError(
                f"{name} triangular distribution needs minimum, most likely, and maximum values."
            )
        minimum = float(spec.minimum)
        maximum = float(spec.maximum)
        mode = float(spec.mode)
        if (
            not np.isfinite(minimum)
            or not np.isfinite(maximum)
            or not np.isfinite(mode)
            or minimum >= maximum
            or mode < minimum
            or mode > maximum
        ):
            raise ValueError(
                f"{name} must satisfy minimum ≤ most likely ≤ maximum."
            )
        values = rng.triangular(minimum, mode, maximum, samples)

    return np.maximum(values, 1e-9)


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


def failure_pressure_ratio(inputs: POFInputs) -> float:
    """Return deterministic FPR = predicted failure pressure / operating pressure."""

    result = corlas_failure_pressure(inputs)
    return result["failure_pressure_psi"] / inputs.operating_pressure_psi


def deterministic_pressure_sweep(
    inputs: POFInputs,
    parameter: str,
    values: Iterable[float],
) -> list[dict[str, float]]:
    """Evaluate deterministic pressure and FPR while changing one crack dimension."""

    if parameter not in {"flaw_depth_mm", "flaw_length_mm"}:
        raise ValueError("The deterministic sweep supports crack depth or crack length.")

    parameter_values = np.asarray(list(values), dtype=float)
    if parameter_values.ndim != 1 or parameter_values.size < 2:
        raise ValueError("A deterministic sweep needs at least two values.")
    if not np.all(np.isfinite(parameter_values)) or np.any(parameter_values <= 0.0):
        raise ValueError("Deterministic sweep values must be positive and finite.")
    if parameter == "flaw_depth_mm" and np.any(
        parameter_values >= inputs.wall_thickness_mm
    ):
        raise ValueError("Crack-depth sweep values must remain below wall thickness.")

    records: list[dict[str, float]] = []
    for value in parameter_values:
        trial_inputs = replace(inputs, **{parameter: float(value)})
        result = corlas_failure_pressure(trial_inputs)
        records.append(
            {
                "parameter_value": float(value),
                "failure_pressure_psi": result["failure_pressure_psi"],
                "fpr": result["failure_pressure_psi"]
                / trial_inputs.operating_pressure_psi,
            }
        )
    return records


def evaluate_deterministic_cracks(
    inputs: POFInputs,
    crack_lengths_mm: Iterable[float],
    crack_depths_mm: Iterable[float],
) -> list[dict[str, float | int]]:
    """Evaluate failure pressure and FPR for an uploaded list of cracks."""

    lengths = np.asarray(list(crack_lengths_mm), dtype=float)
    depths = np.asarray(list(crack_depths_mm), dtype=float)
    if lengths.ndim != 1 or depths.ndim != 1 or lengths.size != depths.size:
        raise ValueError("Crack length and depth must be one-dimensional, equal-size lists.")
    if lengths.size == 0:
        raise ValueError("At least one crack is required.")
    if lengths.size > 1000:
        raise ValueError("Upload no more than 1,000 cracks at a time.")
    if not np.all(np.isfinite(lengths)) or np.any(lengths <= 0.0):
        raise ValueError("Every crack length must be positive and finite.")
    if not np.all(np.isfinite(depths)) or np.any(depths <= 0.0):
        raise ValueError("Every crack depth must be positive and finite.")
    if np.any(depths >= inputs.wall_thickness_mm):
        raise ValueError("Every crack depth must be smaller than wall thickness.")

    records: list[dict[str, float | int]] = []
    for index, (length_mm, depth_mm) in enumerate(zip(lengths, depths), start=1):
        trial = replace(
            inputs,
            flaw_length_mm=float(length_mm),
            flaw_depth_mm=float(depth_mm),
        )
        result = corlas_failure_pressure(trial)
        records.append(
            {
                "crack_number": index,
                "crack_length_mm": float(length_mm),
                "crack_depth_mm": float(depth_mm),
                "depth_percent_wall": float(
                    100.0 * depth_mm / inputs.wall_thickness_mm
                ),
                "failure_pressure_psi": result["failure_pressure_psi"],
                "fpr": result["failure_pressure_psi"]
                / inputs.operating_pressure_psi,
            }
        )
    return records


def deterministic_fpr_boundary(
    inputs: POFInputs,
    target_fpr: float,
    *,
    minimum_length_mm: float = 1.0,
    maximum_length_mm: float = 300.0,
    length_points: int = 81,
    minimum_depth_mm: float = 0.05,
    maximum_depth_ratio: float = 0.95,
) -> list[dict[str, float]]:
    """Return the crack depth/length curve at a selected deterministic FPR.

    For every crack length, bisection finds the crack depth where predicted
    failure pressure divided by operating pressure equals ``target_fpr``.
    Lengths without a boundary inside the plotted depth range are omitted.
    """

    _positive("target FPR", target_fpr)
    _positive("minimum crack length", minimum_length_mm)
    _positive("maximum crack length", maximum_length_mm)
    _positive("minimum crack depth", minimum_depth_mm)
    if maximum_length_mm <= minimum_length_mm:
        raise ValueError("Maximum crack length must exceed minimum crack length.")
    if length_points < 2 or length_points > 501:
        raise ValueError("Boundary resolution must be between 2 and 501 points.")
    if not 0.0 < maximum_depth_ratio < 1.0:
        raise ValueError("Maximum depth ratio must be between zero and one.")

    maximum_depth_mm = maximum_depth_ratio * inputs.wall_thickness_mm
    if minimum_depth_mm >= maximum_depth_mm:
        raise ValueError("Minimum crack depth must be below the plotted maximum depth.")

    target_pressure = target_fpr * inputs.operating_pressure_psi
    length_values = np.linspace(
        minimum_length_mm, maximum_length_mm, length_points
    )
    records: list[dict[str, float]] = []

    for length_mm in length_values:
        def residual(depth_mm: float) -> float:
            trial = replace(
                inputs,
                flaw_length_mm=float(length_mm),
                flaw_depth_mm=float(depth_mm),
            )
            return corlas_failure_pressure(trial)["failure_pressure_psi"] - target_pressure

        lower_depth = minimum_depth_mm
        upper_depth = maximum_depth_mm
        lower_residual = residual(lower_depth)
        upper_residual = residual(upper_depth)
        if lower_residual * upper_residual > 0.0:
            continue

        for _ in range(45):
            middle_depth = (lower_depth + upper_depth) / 2.0
            middle_residual = residual(middle_depth)
            if middle_residual > 0.0:
                lower_depth = middle_depth
            else:
                upper_depth = middle_depth

        boundary_depth = (lower_depth + upper_depth) / 2.0
        records.append(
            {
                "crack_length_mm": float(length_mm),
                "crack_depth_mm": float(boundary_depth),
                "depth_percent_wall": float(
                    100.0 * boundary_depth / inputs.wall_thickness_mm
                ),
                "target_fpr": float(target_fpr),
                "target_failure_pressure_psi": float(target_pressure),
            }
        )

    return records


def simulate_probability_of_failure(
    inputs: POFInputs,
    uncertainty: UncertaintyInputs | None = None,
    *,
    variable_specs: Mapping[str, DistributionSpec] | None = None,
    samples: int = 1000,
    seed: int = 7,
) -> dict[str, object]:
    """Estimate POF with user-selected distributions for every model input."""

    if samples < 100 or samples > 10000:
        raise ValueError("Samples must be between 100 and 10,000.")
    if uncertainty is not None and variable_specs is not None:
        raise ValueError("Use either uncertainty or variable_specs, not both.")
    if uncertainty is not None:
        for name, value in uncertainty.__dict__.items():
            if value < 0 or not np.isfinite(value):
                raise ValueError(f"{name} uncertainty cannot be negative.")

    rng = np.random.default_rng(seed)
    if variable_specs is None:
        specs = recommended_distribution_specs(inputs, uncertainty)
    else:
        unknown_names = set(variable_specs) - set(inputs.__dict__)
        if unknown_names:
            raise ValueError(f"Unknown pipeline parameter: {sorted(unknown_names)[0]}.")
        specs = {
            name: variable_specs.get(name, DistributionSpec())
            for name in inputs.__dict__
        }

    sampled_inputs = {
        name: _sample_distribution(
            rng,
            float(value),
            specs[name],
            samples,
            name=name.replace("_", " "),
        )
        for name, value in inputs.__dict__.items()
    }

    # Keep sampled cases inside simple physical bounds used by the teaching model.
    sampled_inputs["diameter_in"] = np.maximum(sampled_inputs["diameter_in"], 0.1)
    sampled_inputs["wall_thickness_mm"] = np.maximum(
        sampled_inputs["wall_thickness_mm"], 0.5
    )
    sampled_inputs["flaw_length_mm"] = np.maximum(sampled_inputs["flaw_length_mm"], 0.1)
    sampled_inputs["flaw_depth_mm"] = np.clip(
        sampled_inputs["flaw_depth_mm"],
        0.02,
        0.95 * sampled_inputs["wall_thickness_mm"],
    )
    sampled_inputs["yield_strength_psi"] = np.maximum(
        sampled_inputs["yield_strength_psi"], 1000.0
    )
    sampled_inputs["ultimate_strength_psi"] = np.maximum(
        sampled_inputs["ultimate_strength_psi"],
        sampled_inputs["yield_strength_psi"] * 1.01,
    )
    sampled_inputs["elastic_modulus_gpa"] = np.maximum(
        sampled_inputs["elastic_modulus_gpa"], 1.0
    )
    sampled_inputs["charpy_energy"] = np.maximum(sampled_inputs["charpy_energy"], 1.0)
    sampled_inputs["operating_pressure_psi"] = np.maximum(
        sampled_inputs["operating_pressure_psi"], 1.0
    )
    sampled_inputs["model_factor"] = np.maximum(sampled_inputs["model_factor"], 0.05)
    sampled_inputs["safety_factor"] = np.maximum(sampled_inputs["safety_factor"], 0.1)

    failure_pressures = np.empty(samples, dtype=float)
    margins = np.empty(samples, dtype=float)
    for index in range(samples):
        sampled = POFInputs(
            **{
                name: float(values[index])
                for name, values in sampled_inputs.items()
            }
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
        "sampled_inputs": sampled_inputs,
        "variable_specs": specs,
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
