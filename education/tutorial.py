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


render_project_hero(
    "Educational tutorial",
    "From ILI Data to a Maintenance Decision",
    "A guided classroom exercise for learning how crack measurements, uncertainty, failure pressure, and probability of failure support pipeline-integrity decisions.",
)

st.markdown(
    """
    <div class="notice"><strong>Learning use only.</strong> The thresholds and maintenance
    prompts on this page are illustrative. They do not replace applicable codes, validated
    operator models, engineering review, or integrity-management procedures.</div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Learning path")
st.markdown("**Learn → Calculate → Visualize → Decide → Check your understanding**")
st.caption(
    "Learning objectives: explain a simple limit state, estimate POF from uncertain inputs, "
    "interpret a probability-density plot, and connect the result to a maintenance discussion."
)

with st.sidebar:
    st.header("Classroom case")
    st.caption("Change one input at a time and observe how the result responds.")
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
            if parameter_distribution in {"Normal", "Lognormal"}:
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
            else:
                variable_specs[parameter_name] = DistributionSpec()

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
