"""Preliminary deterministic and probabilistic analysis of crack profiles."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from education.pof_model import (
    POFInputs,
    UncertaintyInputs,
    corlas_failure_pressure,
    simulate_probability_of_failure,
)


MM_PER_INCH = 25.4

RESULT_COLUMNS = [
    "Profile ID",
    "Feature ID",
    "Feature location (m)",
    "Crack depth (mm)",
    "Crack length (mm)",
    "Wall thickness (mm)",
    "Outside diameter (mm)",
    "Burst resistance pressure (psi)",
    "FPR",
    "POF",
    "Monte Carlo failures",
    "Monte Carlo samples",
    "Status",
]


def _finite_number(value: object) -> float | None:
    """Return a finite float or ``None`` for an unavailable cell value."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def analyze_crack_profiles(
    summary: pd.DataFrame,
    base_inputs: POFInputs,
    uncertainty: UncertaintyInputs,
    *,
    samples: int = 1000,
    seed: int = 7,
    deterministic_only: bool = False,
) -> pd.DataFrame:
    """Calculate burst pressure, FPR, and POF for every valid crack profile.

    Geometry and crack dimensions come from each prepared profile. Material,
    pressure, model-factor, and uncertainty inputs are shared across profiles.
    Rows with missing or invalid geometry remain in the result with a clear
    status instead of stopping the entire analysis.
    """

    required_columns = {
        "Profile ID",
        "Feature ID",
        "Feature location (m)",
        "Maximum depth (mm)",
        "Profile length (mm)",
        "Wall thickness (mm)",
        "Outside diameter (mm)",
    }
    missing_columns = sorted(required_columns - set(summary.columns))
    if missing_columns:
        raise ValueError(
            "The prepared profile table is missing: " + ", ".join(missing_columns)
        )
    if summary.empty:
        raise ValueError("At least one prepared crack profile is required.")

    records: list[dict[str, object]] = []
    for row_number, (_, row) in enumerate(summary.iterrows()):
        depth_mm = _finite_number(row["Maximum depth (mm)"])
        length_mm = _finite_number(row["Profile length (mm)"])
        wall_mm = _finite_number(row["Wall thickness (mm)"])
        diameter_mm = _finite_number(row["Outside diameter (mm)"])

        record: dict[str, object] = {
            "Profile ID": str(row["Profile ID"]),
            "Feature ID": str(row["Feature ID"]),
            "Feature location (m)": _finite_number(row["Feature location (m)"]),
            "Crack depth (mm)": depth_mm,
            "Crack length (mm)": length_mm,
            "Wall thickness (mm)": wall_mm,
            "Outside diameter (mm)": diameter_mm,
            "Burst resistance pressure (psi)": None,
            "FPR": None,
            "POF": None,
            "Monte Carlo failures": None,
            "Monte Carlo samples": samples,
            "Status": "Not calculated",
        }
        if deterministic_only and row.get('Defect type','Crack') != 'Crack':
            record['Status'] = 'Not calculated: a corrosion-specific resistance model is required'
            records.append(record)
            continue

        missing_values = [
            label
            for label, value in (
                ("crack depth", depth_mm),
                ("crack length", length_mm),
                ("wall thickness", wall_mm),
                ("outside diameter", diameter_mm),
            )
            if value is None
        ]
        if missing_values:
            record["Status"] = "Missing " + ", ".join(missing_values)
            records.append(record)
            continue
        if any(value <= 0.0 for value in (depth_mm, length_mm, wall_mm, diameter_mm)):
            record["Status"] = "Geometry values must be positive"
            records.append(record)
            continue
        if depth_mm >= wall_mm:
            record["Status"] = "Crack depth must be below wall thickness"
            records.append(record)
            continue

        profile_inputs = replace(
            base_inputs,
            diameter_in=diameter_mm / MM_PER_INCH,
            wall_thickness_mm=wall_mm,
            flaw_length_mm=length_mm,
            flaw_depth_mm=depth_mm,
        )
        try:
            deterministic = corlas_failure_pressure(profile_inputs)
            probability = (None if deterministic_only else simulate_probability_of_failure(
                profile_inputs,uncertainty,samples=samples,seed=seed + row_number))
        except ValueError as error:
            record["Status"] = str(error)
            records.append(record)
            continue

        burst_pressure = float(deterministic["failure_pressure_psi"])
        record.update(
            {
                "Burst resistance pressure (psi)": burst_pressure,
                "FPR": burst_pressure / profile_inputs.operating_pressure_psi,
                "POF": float(probability["probability_of_failure"]) if probability else None,
                "Monte Carlo failures": int(probability["failures"]) if probability else None,
                "Status": "Calculated",
            }
        )
        records.append(record)

    return pd.DataFrame.from_records(records, columns=RESULT_COLUMNS)


def analyze_deterministic_profiles(summary: pd.DataFrame,base_inputs: POFInputs) -> pd.DataFrame:
    """Resistance/FPR only; never calls the Monte Carlo simulation."""
    result = analyze_crack_profiles(summary,base_inputs,UncertaintyInputs(),deterministic_only=True)
    result = result.drop(columns=['POF','Monte Carlo failures','Monte Carlo samples'])
    result['Defect type'] = summary.get('Defect type',pd.Series('Crack',index=summary.index)).to_numpy()
    return result.rename(columns={'Crack depth (mm)':'Defect depth (mm)','Crack length (mm)':'Defect length (mm)'})
