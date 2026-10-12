"""Guided educational tutorial for the ALIRIM platform."""

from __future__ import annotations

import csv
import io

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from education.pof_model import (
    DistributionSpec,
    POFInputs,
    SUPPORTED_DISTRIBUTIONS,
    classroom_interpretation,
    corlas_failure_pressure,
    deterministic_fpr_boundary,
    deterministic_pressure_sweep,
    evaluate_deterministic_cracks,
    failure_pressure_ratio,
    limit_state_density_curve,
    recommended_distribution_specs,
    simulate_probability_of_failure,
)
from platform_ui import render_project_hero


PARAMETER_UI = (
    ("diameter_in", "Pipe diameter", "in"),
    ("wall_thickness_mm", "Wall thickness", "mm"),
    ("flaw_length_mm", "Crack length", "mm"),
    ("flaw_depth_mm", "Crack depth", "mm"),
    ("yield_strength_psi", "Yield strength", "psi"),
    ("ultimate_strength_psi", "Ultimate strength", "psi"),
    ("elastic_modulus_gpa", "Elastic modulus", "GPa"),
    ("charpy_energy", "Charpy energy", "energy unit"),
    ("operating_pressure_psi", "Operating pressure", "psi"),
    ("model_factor", "Model factor, θ", "–"),
    ("safety_factor", "Safety factor", "–"),
)
PARAMETER_LABELS = {name: label for name, label, _ in PARAMETER_UI}
PARAMETER_UNITS = {name: unit for name, _, unit in PARAMETER_UI}
DETERMINISTIC_MODULE = "1 · Deterministic FPR"
PROBABILISTIC_MODULE = "2 · Probabilistic POF"


def _distribution_detail(spec: DistributionSpec, unit: str) -> str:
    unit_suffix = "" if unit == "–" else f" {unit}"
    if spec.distribution == "Deterministic":
        return "Fixed value"
    if spec.distribution in {"Normal", "Lognormal"}:
        return f"SD {spec.standard_deviation:,.3g}{unit_suffix}"
    if spec.distribution == "Uniform":
        return f"{spec.minimum:,.3g} to {spec.maximum:,.3g}{unit_suffix}"
    return (
        f"{spec.minimum:,.3g} / {spec.mode:,.3g} / "
        f"{spec.maximum:,.3g}{unit_suffix}"
    )


def _suggest_column_index(
    columns: list[object], keywords: tuple[str, ...], fallback: int
) -> int:
    """Choose a likely crack-data column while keeping manual selection available."""

    for index, column in enumerate(columns):
        normalized = str(column).strip().lower().replace("_", " ")
        if any(keyword in normalized for keyword in keywords):
            return index
    return min(fallback, max(len(columns) - 1, 0))


@st.cache_data(show_spinner=False)
def _deterministic_chart_data(
    inputs: POFInputs, maximum_length_mm: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calculate reusable deterministic boundary and sensitivity data."""

    boundaries: list[dict[str, float | str]] = []
    for target_fpr, label in (
        (
            1.0,
            f"FPR = 1.00 · Pf = {inputs.operating_pressure_psi:,.0f} psi",
        ),
        (
            1.25,
            f"FPR = 1.25 · Pf = {1.25 * inputs.operating_pressure_psi:,.0f} psi",
        ),
    ):
        for record in deterministic_fpr_boundary(
            inputs,
            target_fpr,
            maximum_length_mm=maximum_length_mm,
            length_points=81,
        ):
            boundaries.append({**record, "Boundary": label})

    depth_values = np.linspace(0.05, 0.95 * inputs.wall_thickness_mm, 100)
    length_values = np.linspace(1.0, maximum_length_mm, 100)
    depth_sweep = pd.DataFrame(
        deterministic_pressure_sweep(inputs, "flaw_depth_mm", depth_values)
    ).rename(columns={"parameter_value": "Crack dimension (mm)"})
    length_sweep = pd.DataFrame(
        deterministic_pressure_sweep(inputs, "flaw_length_mm", length_values)
    ).rename(columns={"parameter_value": "Crack dimension (mm)"})
    return pd.DataFrame(boundaries), depth_sweep, length_sweep


def _sensitivity_chart(
    data: pd.DataFrame,
    *,
    dimension_title: str,
    selected_dimension: float,
    selected_pressure: float,
    operating_pressure: float,
) -> alt.LayerChart:
    """Build one failure-pressure sensitivity curve with the selected case."""

    response = (
        alt.Chart(data)
        .mark_line(color="#276749", strokeWidth=3)
        .encode(
            x=alt.X("Crack dimension (mm):Q", title=dimension_title),
            y=alt.Y(
                "failure_pressure_psi:Q",
                title="Predicted failure pressure (psi)",
                axis=alt.Axis(format=",.0f"),
            ),
            tooltip=[
                alt.Tooltip("Crack dimension (mm):Q", format=".2f"),
                alt.Tooltip(
                    "failure_pressure_psi:Q",
                    title="Failure pressure (psi)",
                    format=",.1f",
                ),
                alt.Tooltip("fpr:Q", title="FPR", format=".3f"),
            ],
        )
    )
    operating_line = (
        alt.Chart(pd.DataFrame({"Operating pressure": [operating_pressure]}))
        .mark_rule(color="#c62828", strokeDash=[7, 5], strokeWidth=2)
        .encode(y="Operating pressure:Q")
    )
    selected_point = (
        alt.Chart(
            pd.DataFrame(
                {
                    "Crack dimension (mm)": [selected_dimension],
                    "failure_pressure_psi": [selected_pressure],
                }
            )
        )
        .mark_point(color="#0f426d", filled=True, size=130, stroke="white", strokeWidth=2)
        .encode(
            x="Crack dimension (mm):Q",
            y="failure_pressure_psi:Q",
            tooltip=[
                alt.Tooltip("Crack dimension (mm):Q", format=".2f"),
                alt.Tooltip("failure_pressure_psi:Q", format=",.1f"),
            ],
        )
    )
    return (response + operating_line + selected_point).properties(height=300)


render_project_hero(
    "Educational tutorial",
    "From ILI Data to a Maintenance Decision",
    "Two guided classroom modules for exploring deterministic failure-pressure ratio and probabilistic failure analysis for pipeline cracks.",
)

st.markdown(
    """
    <div class="notice"><strong>Learning use only.</strong> The thresholds and maintenance
    prompts on this page are illustrative. They do not replace applicable codes, validated
    operator models, engineering review, or integrity-management procedures.</div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Choose a learning module")
learning_module = st.radio(
    "Learning module",
    [DETERMINISTIC_MODULE, PROBABILISTIC_MODULE],
    horizontal=True,
    label_visibility="collapsed",
    help=(
        "Begin with deterministic crack-size effects, then continue to the "
        "probabilistic model when you are ready to represent uncertainty."
    ),
)

st.subheader("Learning path")
if learning_module == DETERMINISTIC_MODULE:
    st.markdown("**Choose a crack → Calculate FPR → Read the boundary → Explore sensitivity**")
    st.caption(
        "Learning objectives: calculate deterministic FPR, identify the FPR = 1 boundary, "
        "and observe how crack depth and length change predicted failure pressure."
    )
else:
    st.markdown("**Learn → Calculate → Visualize → Decide → Check your understanding**")
    st.caption(
        "Learning objectives: explain a simple limit state, estimate POF from uncertain inputs, "
        "interpret a probability-density plot, and connect the result to a maintenance discussion."
    )

with st.sidebar:
    st.header("Classroom case")
    st.caption(
        "These deterministic pipe, material, crack, and pressure inputs are shared by both modules."
    )
    diameter = st.number_input("Pipe diameter (in)", 4.0, 60.0, 20.0, 1.0)
    wall = st.number_input("Wall thickness (mm)", 2.0, 30.0, 6.35, 0.05)
    length = st.number_input("Crack length (mm)", 1.0, 500.0, 40.0, 1.0)
    depth_limit = max(0.2, wall - 0.05)
    depth_default = min(4.0, depth_limit)
    depth = st.number_input("Crack depth (mm)", 0.05, depth_limit, depth_default, 0.05)
    pressure = st.number_input("Operating pressure (psi)", 100.0, 3000.0, 936.0, 10.0)

    with st.expander("Material inputs"):
        yield_strength = st.number_input("Yield strength (psi)", 10000.0, 150000.0, 57200.0, 500.0)
        ultimate_strength = st.number_input(
            "Ultimate strength (psi)", 10001.0, 180000.0, 73920.0, 500.0
        )
        elastic_modulus = st.number_input("Elastic modulus (GPa)", 50.0, 300.0, 210.0, 1.0)
        charpy = st.number_input("Charpy energy", 1.0, 300.0, 85.0, 1.0)
        model_factor = st.number_input("Model factor, θ", 0.1, 3.0, 1.27, 0.01)
        safety_factor = st.number_input("Safety factor", 1.0, 5.0, 2.0, 0.05)

    inputs = POFInputs(
        diameter_in=diameter,
        wall_thickness_mm=wall,
        flaw_length_mm=length,
        flaw_depth_mm=depth,
        yield_strength_psi=yield_strength,
        ultimate_strength_psi=ultimate_strength,
        elastic_modulus_gpa=elastic_modulus,
        charpy_energy=charpy,
        operating_pressure_psi=pressure,
        model_factor=model_factor,
        safety_factor=safety_factor,
    )

    if learning_module == PROBABILISTIC_MODULE:
      with st.expander("Random-variable setup", expanded=True):
        st.caption(
            "Choose whether each input is fixed or random. The classroom value above "
            "is used as the mean for Normal and Lognormal distributions."
        )
        recommended_specs = recommended_distribution_specs(inputs)
        variable_specs: dict[str, DistributionSpec] = {}
        for parameter_name, parameter_label, parameter_unit in PARAMETER_UI:
            parameter_prefix = f"education_rv_v2_{parameter_name}"
            center = float(getattr(inputs, parameter_name))
            default_spec = recommended_specs[parameter_name]
            default_sd = default_spec.standard_deviation or max(center * 0.05, 0.01)
            default_span = max(2.0 * default_sd, center * 0.10, 0.02)
            st.markdown(f"**{parameter_label}**")
            parameter_distribution = st.selectbox(
                f"Treatment for {parameter_label}",
                SUPPORTED_DISTRIBUTIONS,
                index=SUPPORTED_DISTRIBUTIONS.index(default_spec.distribution),
                key=f"{parameter_prefix}_distribution",
                label_visibility="collapsed",
                help=(
                    "Deterministic uses one fixed value. The other choices sample "
                    "a probability distribution."
                ),
            )
            input_step = max(abs(float(getattr(inputs, parameter_name))) * 0.01, 0.001)
            unit_suffix = "" if parameter_unit == "–" else f" {parameter_unit}"
            if parameter_distribution in {"Normal", "Lognormal"}:
                st.caption(
                    f"Mean: **{center:,.6g}{unit_suffix}** · classroom value above"
                )
                standard_deviation = st.number_input(
                    f"{parameter_label} standard deviation ({parameter_unit})",
                    min_value=0.000001,
                    value=float(default_sd),
                    step=float(input_step),
                    format="%.6g",
                    key=f"{parameter_prefix}_sd",
                )
                variable_specs[parameter_name] = DistributionSpec(
                    parameter_distribution,
                    standard_deviation=float(standard_deviation),
                )
            elif parameter_distribution in {"Uniform", "Triangular"}:
                minimum = st.number_input(
                    f"{parameter_label} minimum ({parameter_unit})",
                    min_value=0.000001,
                    value=float(max(center - default_span, center * 0.05)),
                    step=float(input_step),
                    format="%.6g",
                    key=f"{parameter_prefix}_minimum",
                )
                if parameter_distribution == "Triangular":
                    mode = st.number_input(
                        f"{parameter_label} most likely ({parameter_unit})",
                        min_value=0.000001,
                        value=float(center),
                        step=float(input_step),
                        format="%.6g",
                        key=f"{parameter_prefix}_mode",
                    )
                else:
                    mode = None
                maximum = st.number_input(
                    f"{parameter_label} maximum ({parameter_unit})",
                    min_value=0.000001,
                    value=float(center + default_span),
                    step=float(input_step),
                    format="%.6g",
                    key=f"{parameter_prefix}_maximum",
                )
                variable_specs[parameter_name] = DistributionSpec(
                    parameter_distribution,
                    minimum=float(minimum),
                    maximum=float(maximum),
                    mode=None if mode is None else float(mode),
                )
                distribution_mean = (
                    (float(minimum) + float(maximum)) / 2.0
                    if mode is None
                    else (float(minimum) + float(mode) + float(maximum)) / 3.0
                )
                st.caption(
                    f"Calculated mean: **{distribution_mean:,.6g}{unit_suffix}**"
                )
            else:
                variable_specs[parameter_name] = DistributionSpec()
                st.caption(f"Fixed value: **{center:,.6g}{unit_suffix}**")

        configured_random_count = sum(
            spec.distribution != "Deterministic" for spec in variable_specs.values()
        )
        st.success(
            f"Current model: {configured_random_count} random and "
            f"{len(variable_specs) - configured_random_count} deterministic parameters."
        )
        st.caption(
            "Physical checks keep sampled values positive, crack depth below wall thickness, "
            "and ultimate strength above yield strength. Safety factor affects allowable "
            "pressure, but it is not part of the tutorial limit state g."
        )

try:
    deterministic = corlas_failure_pressure(inputs)
except ValueError as error:
    st.error(str(error))
    st.stop()

if learning_module == DETERMINISTIC_MODULE:
    fpr = failure_pressure_ratio(inputs)
    st.subheader("Deterministic crack-size and FPR module")
    st.markdown(
        "**Failure Pressure Ratio (FPR) = predicted failure pressure ÷ operating pressure.** "
        "The FPR = 1 curve contains crack sizes whose predicted failure pressure equals "
        f"the selected operating pressure of **{pressure:,.0f} psi**."
    )

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric(
        "Selected crack",
        f"{length:,.1f} × {depth:,.2f} mm",
        help="Crack length × crack depth",
    )
    metric_2.metric(
        "Failure pressure", f"{deterministic['failure_pressure_psi']:,.0f} psi"
    )
    metric_3.metric("Operating pressure", f"{pressure:,.0f} psi")
    metric_4.metric("FPR", f"{fpr:.3f}")

    if fpr < 1.0:
        st.error(
            "For this classroom case, FPR < 1: predicted failure pressure is below "
            "the selected operating pressure."
        )
    elif fpr < 1.25:
        st.warning(
            "For this classroom case, FPR is between 1.00 and the illustrative "
            "1.25 comparison line."
        )
    else:
        st.success(
            "For this classroom case, FPR is at or above the illustrative "
            "1.25 comparison line."
        )

    maximum_length_mm = max(300.0, float(length))
    with st.spinner("Calculating deterministic crack-size boundaries..."):
        boundary_frame, depth_sweep, length_sweep = _deterministic_chart_data(
            inputs, maximum_length_mm
        )

    uploaded_crack_frame = pd.DataFrame()
    st.markdown("#### Compare a crack list")
    with st.expander("Upload CSV or Excel crack data", expanded=False):
        st.markdown(
            "Upload one row per crack and choose the columns containing **crack length "
            "in mm** and **crack depth in mm**. All uploaded cracks use the pipe, material, "
            "and operating-pressure inputs currently shown in the sidebar."
        )
        example_cracks = pd.DataFrame(
            {
                "Crack ID": [f"C-{index:02d}" for index in range(1, 11)],
                "Crack Length (mm)": [20, 35, 50, 65, 80, 100, 125, 150, 180, 220],
                "Crack Depth (mm)": [1.2, 1.5, 1.8, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0, 4.4],
            }
        )
        st.download_button(
            "Download 10-crack CSV template",
            example_cracks.to_csv(index=False),
            file_name="alirim_crack_list_template.csv",
            mime="text/csv",
        )
        uploaded_crack_file = st.file_uploader(
            "Crack data file",
            type=["csv", "xlsx"],
            help="Accepted formats: CSV and Excel .xlsx files.",
            key="deterministic_crack_inventory",
        )
        if uploaded_crack_file is not None:
            try:
                if uploaded_crack_file.name.lower().endswith(".csv"):
                    uploaded_table = pd.read_csv(uploaded_crack_file)
                else:
                    uploaded_table = pd.read_excel(uploaded_crack_file)

                if len(uploaded_table.columns) < 2:
                    st.error("The file needs at least two columns: crack length and crack depth.")
                elif uploaded_table.empty:
                    st.error("The uploaded file does not contain any crack rows.")
                else:
                    uploaded_columns = list(uploaded_table.columns)
                    length_column = st.selectbox(
                        "Crack length column (mm)",
                        uploaded_columns,
                        index=_suggest_column_index(uploaded_columns, ("length",), 0),
                        format_func=str,
                    )
                    depth_column = st.selectbox(
                        "Crack depth column (mm)",
                        uploaded_columns,
                        index=_suggest_column_index(uploaded_columns, ("depth",), 1),
                        format_func=str,
                    )
                    if length_column == depth_column:
                        st.error("Choose different columns for crack length and crack depth.")
                    else:
                        crack_lengths = pd.to_numeric(
                            uploaded_table[length_column], errors="coerce"
                        )
                        crack_depths = pd.to_numeric(
                            uploaded_table[depth_column], errors="coerce"
                        )
                        valid_mask = (
                            crack_lengths.notna()
                            & crack_depths.notna()
                            & (crack_lengths > 0.0)
                            & (crack_depths > 0.0)
                            & (crack_depths < wall)
                        )
                        invalid_count = int((~valid_mask).sum())
                        if invalid_count:
                            st.warning(
                                f"Skipped {invalid_count} row(s) with missing/non-positive values "
                                "or crack depth greater than or equal to wall thickness."
                            )

                        valid_lengths = crack_lengths[valid_mask].to_numpy(dtype=float)
                        valid_depths = crack_depths[valid_mask].to_numpy(dtype=float)
                        if valid_lengths.size == 0:
                            st.error("No valid crack rows remain after checking the selected columns.")
                        else:
                            uploaded_crack_frame = pd.DataFrame(
                                evaluate_deterministic_cracks(
                                    inputs, valid_lengths, valid_depths
                                )
                            )
                            uploaded_crack_frame["Source row"] = (
                                np.flatnonzero(valid_mask.to_numpy()) + 2
                            )
                            uploaded_crack_frame["Crack"] = [
                                f"Crack {number}"
                                for number in uploaded_crack_frame["crack_number"]
                            ]
                            uploaded_crack_frame["FPR band"] = np.select(
                                [
                                    uploaded_crack_frame["fpr"] < 1.0,
                                    uploaded_crack_frame["fpr"] < 1.25,
                                ],
                                ["FPR < 1.00", "1.00 ≤ FPR < 1.25"],
                                default="FPR ≥ 1.25",
                            )

                            list_1, list_2, list_3, list_4 = st.columns(4)
                            list_1.metric("Valid cracks", f"{len(uploaded_crack_frame):,}")
                            list_2.metric(
                                "FPR < 1",
                                int((uploaded_crack_frame["fpr"] < 1.0).sum()),
                            )
                            list_3.metric(
                                "FPR 1–1.25",
                                int(
                                    (
                                        (uploaded_crack_frame["fpr"] >= 1.0)
                                        & (uploaded_crack_frame["fpr"] < 1.25)
                                    ).sum()
                                ),
                            )
                            list_4.metric(
                                "FPR ≥ 1.25",
                                int((uploaded_crack_frame["fpr"] >= 1.25).sum()),
                            )

                            uploaded_results = uploaded_crack_frame[
                                [
                                    "Source row",
                                    "Crack",
                                    "crack_length_mm",
                                    "crack_depth_mm",
                                    "depth_percent_wall",
                                    "failure_pressure_psi",
                                    "fpr",
                                    "FPR band",
                                ]
                            ].rename(
                                columns={
                                    "crack_length_mm": "Crack length (mm)",
                                    "crack_depth_mm": "Crack depth (mm)",
                                    "depth_percent_wall": "Depth (%WT)",
                                    "failure_pressure_psi": "Failure pressure (psi)",
                                    "fpr": "FPR",
                                }
                            )
                            st.dataframe(
                                uploaded_results.round(
                                    {
                                        "Crack length (mm)": 2,
                                        "Crack depth (mm)": 3,
                                        "Depth (%WT)": 1,
                                        "Failure pressure (psi)": 1,
                                        "FPR": 3,
                                    }
                                ),
                                hide_index=True,
                                width="stretch",
                            )
                            st.download_button(
                                "Download evaluated crack results",
                                uploaded_results.to_csv(index=False),
                                file_name="alirim_deterministic_crack_results.csv",
                                mime="text/csv",
                            )
            except (ImportError, OSError, TypeError, ValueError) as error:
                st.error(f"The crack file could not be read: {error}")

    if not uploaded_crack_frame.empty:
        uploaded_maximum_length = float(
            uploaded_crack_frame["crack_length_mm"].max()
        )
        required_maximum_length = max(
            maximum_length_mm, 1.05 * uploaded_maximum_length
        )
        if required_maximum_length > maximum_length_mm:
            maximum_length_mm = required_maximum_length
            with st.spinner("Extending the curves to include every uploaded crack..."):
                boundary_frame, depth_sweep, length_sweep = _deterministic_chart_data(
                    inputs, maximum_length_mm
                )

    st.markdown("#### Crack depth–length interaction")
    st.caption(
        "Each curve connects crack sizes with the same FPR. The blue diamond is the "
        "sidebar crack; uploaded cracks appear as color-coded circles."
    )
    selected_point_frame = pd.DataFrame(
        {
            "crack_length_mm": [length],
            "crack_depth_mm": [depth],
            "FPR": [fpr],
            "Failure pressure (psi)": [deterministic["failure_pressure_psi"]],
        }
    )
    chart_layers: list[alt.Chart] = []
    if boundary_frame.empty:
        st.warning(
            "No FPR boundary falls inside the displayed crack-depth range for these inputs. "
            "Try a different operating pressure or material case."
        )
    else:
        boundary_labels = list(boundary_frame["Boundary"].drop_duplicates())
        boundary_lines = (
            alt.Chart(boundary_frame)
            .mark_line(strokeWidth=3)
            .encode(
                x=alt.X(
                    "crack_length_mm:Q",
                    title="Crack length (mm)",
                    scale=alt.Scale(domain=[0.0, maximum_length_mm]),
                ),
                y=alt.Y(
                    "crack_depth_mm:Q",
                    title="Crack depth (mm)",
                    scale=alt.Scale(domain=[0.0, wall]),
                ),
                color=alt.Color(
                    "Boundary:N",
                    scale=alt.Scale(
                        domain=boundary_labels,
                        range=["#c62828", "#ed8936"],
                    ),
                    legend=alt.Legend(orient="bottom", title=None),
                ),
                tooltip=[
                    alt.Tooltip("Boundary:N"),
                    alt.Tooltip("crack_length_mm:Q", title="Length (mm)", format=".1f"),
                    alt.Tooltip("crack_depth_mm:Q", title="Depth (mm)", format=".3f"),
                    alt.Tooltip(
                        "depth_percent_wall:Q", title="Depth (%WT)", format=".1f"
                    ),
                ],
            )
        )
        chart_layers.append(boundary_lines)

    if not uploaded_crack_frame.empty:
        uploaded_points = (
            alt.Chart(uploaded_crack_frame)
            .mark_point(
                shape="circle",
                filled=True,
                size=115,
                opacity=0.9,
                stroke="white",
                strokeWidth=1.5,
            )
            .encode(
                x=alt.X(
                    "crack_length_mm:Q",
                    title="Crack length (mm)",
                    scale=alt.Scale(domain=[0.0, maximum_length_mm]),
                ),
                y=alt.Y(
                    "crack_depth_mm:Q",
                    title="Crack depth (mm)",
                    scale=alt.Scale(domain=[0.0, wall]),
                ),
                color=alt.Color(
                    "FPR band:N",
                    title="Uploaded crack result",
                    scale=alt.Scale(
                        domain=[
                            "FPR < 1.00",
                            "1.00 ≤ FPR < 1.25",
                            "FPR ≥ 1.25",
                        ],
                        range=["#c62828", "#ed8936", "#2e7d32"],
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("Crack:N"),
                    alt.Tooltip("Source row:Q", format=".0f"),
                    alt.Tooltip("crack_length_mm:Q", title="Length (mm)", format=".1f"),
                    alt.Tooltip("crack_depth_mm:Q", title="Depth (mm)", format=".3f"),
                    alt.Tooltip(
                        "depth_percent_wall:Q", title="Depth (%WT)", format=".1f"
                    ),
                    alt.Tooltip(
                        "failure_pressure_psi:Q",
                        title="Failure pressure (psi)",
                        format=",.1f",
                    ),
                    alt.Tooltip("fpr:Q", title="FPR", format=".3f"),
                    alt.Tooltip("FPR band:N"),
                ],
            )
        )
        chart_layers.append(uploaded_points)

    selected_point = (
        alt.Chart(selected_point_frame)
        .mark_point(
            shape="diamond",
            color="#0f426d",
            filled=True,
            size=190,
            stroke="white",
            strokeWidth=2,
        )
        .encode(
            x=alt.X(
                "crack_length_mm:Q",
                title="Crack length (mm)",
                scale=alt.Scale(domain=[0.0, maximum_length_mm]),
            ),
            y=alt.Y(
                "crack_depth_mm:Q",
                title="Crack depth (mm)",
                scale=alt.Scale(domain=[0.0, wall]),
            ),
            tooltip=[
                alt.Tooltip("crack_length_mm:Q", title="Length (mm)", format=".1f"),
                alt.Tooltip("crack_depth_mm:Q", title="Depth (mm)", format=".2f"),
                alt.Tooltip("Failure pressure (psi):Q", format=",.1f"),
                alt.Tooltip("FPR:Q", format=".3f"),
            ],
        )
    )
    chart_layers.append(selected_point)
    interaction_chart = (
        alt.layer(*chart_layers)
        .resolve_scale(color="independent")
        .properties(height=430)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(interaction_chart, width="stretch")
    st.caption(
        "Boundary lines — red: FPR = 1; orange: illustrative FPR = 1.25. "
        "Uploaded points — red: FPR < 1; orange: FPR from 1 to 1.25; green: FPR ≥ 1.25. "
        "These are learning comparisons, not operator acceptance criteria."
    )

    st.markdown("#### How each crack dimension changes failure pressure")
    depth_column, length_column = st.columns(2)
    with depth_column:
        st.markdown(f"**Vary depth at a fixed length of {length:,.1f} mm**")
        depth_chart = _sensitivity_chart(
            depth_sweep,
            dimension_title="Crack depth (mm)",
            selected_dimension=depth,
            selected_pressure=deterministic["failure_pressure_psi"],
            operating_pressure=pressure,
        )
        st.altair_chart(depth_chart, width="stretch")
    with length_column:
        st.markdown(f"**Vary length at a fixed depth of {depth:,.2f} mm**")
        length_chart = _sensitivity_chart(
            length_sweep,
            dimension_title="Crack length (mm)",
            selected_dimension=length,
            selected_pressure=deterministic["failure_pressure_psi"],
            operating_pressure=pressure,
        )
        st.altair_chart(length_chart, width="stretch")
    st.caption(
        f"The dashed red line is the selected operating pressure ({pressure:,.0f} psi); "
        "the blue point is the current crack. Change depth or length in the sidebar and "
        "observe how the point and FPR move."
    )

    with st.expander("View the selected deterministic calculation"):
        st.dataframe(
            pd.DataFrame(
                {
                    "Output": [
                        "Flow-stress pressure",
                        "Fracture-toughness pressure",
                        "Controlling failure pressure",
                        "Operating pressure",
                        "Failure Pressure Ratio (FPR)",
                        "Crack depth / wall thickness",
                    ],
                    "Value": [
                        f"{deterministic['flow_pressure_psi']:,.1f} psi",
                        f"{deterministic['toughness_pressure_psi']:,.1f} psi",
                        f"{deterministic['failure_pressure_psi']:,.1f} psi",
                        f"{pressure:,.1f} psi",
                        f"{fpr:.4f}",
                        f"{100.0 * depth / wall:.1f}%",
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )
    st.stop()

learn_tab, calculate_tab, visualize_tab, decision_tab = st.tabs(
    ["1 · Learn", "2 · Calculate", "3 · Visualize POF", "4 · Decide & quiz"]
)

with learn_tab:
    st.subheader("What is being calculated?")
    st.markdown(
        """
        ILI provides measured crack dimensions. A failure-pressure model combines those
        measurements with pipe geometry and material properties. Because measurements and
        model inputs are uncertain, they are represented by probability distributions.

        The tutorial uses the limit state:

        **g = θ × failure pressure − operating pressure**

        - **g > 0:** the sampled case does not fail.
        - **g ≤ 0:** the sampled case is counted as a failure.
        - **POF:** number of failed samples ÷ total number of samples.
        """
    )
    st.info(
        "Try this: increase crack depth in the sidebar, then compare the failure pressure "
        "and POF. State the direction of change before viewing the result."
    )

with calculate_tab:
    st.subheader("Deterministic failure-pressure check")
    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Failure pressure", f"{deterministic['failure_pressure_psi']:,.0f} psi")
    metric_2.metric("Operating pressure", f"{pressure:,.0f} psi")
    metric_3.metric("Limit-state margin", f"{deterministic['limit_state_margin_psi']:,.0f} psi")
    st.markdown(
        "The model calculates both a **flow-stress pressure** and a "
        "**fracture-toughness pressure**. The lower value controls."
    )
    details = pd.DataFrame(
        {
            "Teaching output": [
                "Flow-stress pressure",
                "Fracture-toughness pressure",
                "Controlling failure pressure",
                "Folias factor",
            ],
            "Value": [
                f"{deterministic['flow_pressure_psi']:,.1f} psi",
                f"{deterministic['toughness_pressure_psi']:,.1f} psi",
                f"{deterministic['failure_pressure_psi']:,.1f} psi",
                f"{deterministic['folias_factor']:.3f}",
            ],
        }
    )
    st.dataframe(details, hide_index=True, width="stretch")

with visualize_tab:
    st.subheader("Represent uncertainty and estimate POF")
    random_count = sum(
        spec.distribution != "Deterministic" for spec in variable_specs.values()
    )
    setup_1, setup_2 = st.columns(2)
    setup_1.metric("Random parameters", f"{random_count} of {len(variable_specs)}")
    samples = setup_2.select_slider(
        "Monte Carlo samples", [250, 500, 1000, 2000], value=1000
    )
    st.caption(
        "Configure every parameter in the left sidebar. Deterministic inputs stay fixed; "
        "random inputs are sampled independently for each Monte Carlo case."
    )
    distribution_summary = pd.DataFrame(
        [
            {
                "Parameter": label,
                "Base value": f"{getattr(inputs, name):,.4g} {unit if unit != '–' else ''}".strip(),
                "Distribution": variable_specs[name].distribution,
                "Definition": _distribution_detail(variable_specs[name], unit),
            }
            for name, label, unit in PARAMETER_UI
        ]
    )
    with st.expander("Review the complete probability model"):
        st.dataframe(distribution_summary, hide_index=True, width="stretch")

    current_configuration = (
        inputs,
        tuple((name, variable_specs[name]) for name, _, _ in PARAMETER_UI),
        samples,
    )
    if st.button("Run the POF simulation", type="primary", width="stretch"):
        with st.spinner("Sampling uncertain inputs and evaluating the limit state..."):
            try:
                st.session_state["education_pof_result"] = simulate_probability_of_failure(
                    inputs,
                    variable_specs=variable_specs,
                    samples=samples,
                    seed=7,
                )
                st.session_state["education_pof_configuration"] = current_configuration
            except ValueError as error:
                st.session_state.pop("education_pof_result", None)
                st.session_state.pop("education_pof_configuration", None)
                st.error(str(error))

    result = st.session_state.get("education_pof_result")
    if result and st.session_state.get("education_pof_configuration") != current_configuration:
        st.info("The inputs or distributions changed. Run the simulation again to update the result.")
        result = None
    if result:
        pof = float(result["probability_of_failure"])
        pof_1, pof_2, pof_3 = st.columns(3)
        pof_1.metric("Estimated POF", f"{pof:.3e}")
        pof_2.metric("Failure samples", f"{result['failures']:,}")
        pof_3.metric("Total samples", f"{result['samples']:,}")
        st.markdown("#### Limit-state POF curve")
        st.markdown(
            f"**POF = failed samples ÷ all samples = "
            f"{result['failures']:,} ÷ {result['samples']:,} = {pof:.3e}.** "
            "The red part is the area where **g ≤ 0**."
        )
        density_frame = pd.DataFrame(
            limit_state_density_curve(result["margins_psi"])
        )
        failure_label = "Failed sample (g ≤ 0)"
        non_failure_label = "Non-failed sample (g > 0)"
        minimum_margin = min(float(density_frame["lower_psi"].min()), 0.0)
        failure_region = (
            alt.Chart(
                pd.DataFrame(
                    {"start": [minimum_margin], "failure_boundary": [0.0]}
                )
            )
            .mark_rect(color="#ffebee", opacity=0.7)
            .encode(
                x=alt.X("start:Q", title="Limit-state margin, g (psi)"),
                x2="failure_boundary:Q",
            )
        )
        density_area = (
            alt.Chart(density_frame)
            .mark_area(opacity=0.62, interpolate="monotone", line={"strokeWidth": 2})
            .encode(
                x=alt.X(
                    "center_psi:Q",
                    title="Limit-state margin, g (psi)",
                    axis=alt.Axis(format=",.0f"),
                ),
                y=alt.Y("density:Q", title="Estimated probability density"),
                color=alt.Color(
                    "outcome:N",
                    title="Monte Carlo outcome",
                    scale=alt.Scale(
                        domain=[failure_label, non_failure_label],
                        range=["#c62828", "#2e7d32"],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("outcome:N", title="Outcome"),
                    alt.Tooltip("lower_psi:Q", title="Bin start (psi)", format=",.1f"),
                    alt.Tooltip("upper_psi:Q", title="Bin end (psi)", format=",.1f"),
                    alt.Tooltip("sample_count:Q", title="Samples", format=","),
                ],
            )
        )
        failure_boundary = (
            alt.Chart(pd.DataFrame({"g": [0.0]}))
            .mark_rule(color="#111827", strokeDash=[7, 5], strokeWidth=3)
            .encode(
                x=alt.X("g:Q"),
                tooltip=[alt.Tooltip("g:Q", title="Failure boundary")],
            )
        )
        failure_region_label = (
            alt.Chart(
                pd.DataFrame(
                    {
                        "g": [minimum_margin / 2.0],
                        "density": [float(density_frame["density"].max()) * 0.9],
                        "label": ["FAILED REGION\ng ≤ 0"],
                    }
                )
            )
            .mark_text(
                color="#b91c1c",
                fontSize=13,
                fontWeight="bold",
                lineBreak="\n",
            )
            .encode(x="g:Q", y="density:Q", text="label:N")
        )
        result_curve = (
            (failure_region + density_area + failure_boundary + failure_region_label)
            .properties(height=350)
            .configure_view(strokeWidth=0)
            .configure_legend(orient="bottom")
        )
        st.altair_chart(result_curve, width="stretch")
        st.caption(
            "Red area: failed Monte Carlo samples with g ≤ 0. Green area: non-failed "
            "samples with g > 0. The dashed vertical line is the failure boundary g = 0."
        )
        if result.get("samples", 0) < 1000:
            st.caption("Use more samples for a more stable classroom estimate.")
    else:
        st.info("Run the simulation to calculate the classroom POF estimate.")

    st.markdown("#### Selected input distribution")
    distribution_variable_label = st.selectbox(
        "Choose a pipeline parameter",
        [label for _, label, _ in PARAMETER_UI],
    )
    distribution_variable = next(
        name
        for name, label, _ in PARAMETER_UI
        if label == distribution_variable_label
    )
    selected_spec = variable_specs[distribution_variable]
    selected_unit = PARAMETER_UNITS[distribution_variable]
    if selected_spec.distribution == "Deterministic":
        st.info(
            f"{distribution_variable_label} is deterministic and remains fixed at "
            f"{getattr(inputs, distribution_variable):,.4g} {selected_unit}."
        )
    elif result:
        sampled_values = np.asarray(result["sampled_inputs"][distribution_variable])
        bin_count = min(30, max(10, int(np.sqrt(sampled_values.size))))
        density, edges = np.histogram(sampled_values, bins=bin_count, density=True)
        distribution_frame = pd.DataFrame(
            {
                "Value": (edges[:-1] + edges[1:]) / 2.0,
                "Density": density,
            }
        )
        distribution_chart = (
            alt.Chart(distribution_frame)
            .mark_area(
                color="#3b6f5a",
                opacity=0.55,
                interpolate="monotone",
                line={"color": "#214c3b", "strokeWidth": 2},
            )
            .encode(
                x=alt.X("Value:Q", title=f"{distribution_variable_label} ({selected_unit})"),
                y=alt.Y("Density:Q", title="Estimated probability density"),
                tooltip=[
                    alt.Tooltip("Value:Q", format=",.3g"),
                    alt.Tooltip("Density:Q", format=".3e"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(distribution_chart, width="stretch")
        st.caption(
            f"Empirical {selected_spec.distribution} distribution after applying the "
            "tutorial's simple physical bounds."
        )
    else:
        st.info("Run the POF simulation to view samples from this distribution.")

with decision_tab:
    st.subheader("Interpret the result before choosing an action")
    result = st.session_state.get("education_pof_result")
    if result and st.session_state.get("education_pof_configuration") != current_configuration:
        result = None
    if result:
        pof = float(result["probability_of_failure"])
        label, prompt = classroom_interpretation(pof)
        st.success(f"Classroom interpretation: **{label}**")
        st.write(prompt)
        st.caption(
            "This band is an educational prompt only. A real decision must use the operator's "
            "approved criteria, codes, consequence assessment, and engineering review."
        )

        report_buffer = io.StringIO()
        writer = csv.writer(report_buffer)
        writer.writerow(["ALIRIM educational case", "Value"])
        writer.writerow(["Crack length (mm)", length])
        writer.writerow(["Crack depth (mm)", depth])
        writer.writerow(["Wall thickness (mm)", wall])
        writer.writerow(["Operating pressure (psi)", pressure])
        writer.writerow(["Failure pressure (psi)", deterministic["failure_pressure_psi"]])
        writer.writerow(["Estimated POF", pof])
        writer.writerow(["Classroom interpretation", label])
        writer.writerow([])
        writer.writerow(["Parameter", "Distribution"])
        for name, parameter_label, _ in PARAMETER_UI:
            writer.writerow([parameter_label, variable_specs[name].distribution])
        st.download_button(
            "Download this classroom result",
            report_buffer.getvalue(),
            file_name="alirim_educational_case.csv",
            mime="text/csv",
        )
    else:
        st.warning("Complete Step 3 and run the POF simulation before interpreting the result.")

    st.markdown("#### Three-question knowledge check")
    answer_1 = st.radio(
        "1. In this tutorial, when is a sample counted as a failure?",
        ["When g ≤ 0", "When g > 0", "Whenever crack depth is measured"],
        index=None,
    )
    answer_2 = st.radio(
        "2. Why are probability distributions used?",
        [
            "To represent uncertainty in measurements and model inputs",
            "To remove the need for engineering judgment",
            "To guarantee the correct maintenance action",
        ],
        index=None,
    )
    answer_3 = st.radio(
        "3. With other inputs unchanged, what usually happens as crack depth increases?",
        ["POF tends to increase", "POF always becomes zero", "Uncertainty disappears"],
        index=None,
    )
    if st.button("Check my answers"):
        correct = sum(
            [
                answer_1 == "When g ≤ 0",
                answer_2 == "To represent uncertainty in measurements and model inputs",
                answer_3 == "POF tends to increase",
            ]
        )
        if correct == 3:
            st.success("3/3 — You connected the measurements, uncertainty, and POF correctly.")
        else:
            st.info(f"{correct}/3 — Review the Learn and Visualize steps, then try again.")
