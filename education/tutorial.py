"""Guided educational tutorial for the ALIRIM platform."""

from __future__ import annotations

import csv
import io

import pandas as pd
import streamlit as st

from education.pof_model import (
    POFInputs,
    UncertaintyInputs,
    classroom_interpretation,
    corlas_failure_pressure,
    normal_pdf_curve,
    simulate_probability_of_failure,
)
from platform_ui import render_project_hero


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
    left, right = st.columns(2)
    with left:
        depth_sd = st.number_input("Crack-depth standard deviation (mm)", 0.01, 5.0, 0.74, 0.05)
        length_sd = st.number_input("Crack-length standard deviation (mm)", 0.01, 100.0, 15.6, 0.5)
        wall_sd = st.number_input("Wall-thickness standard deviation (mm)", 0.01, 5.0, 0.60, 0.05)
    with right:
        pressure_sd = st.number_input("Pressure standard deviation (psi)", 0.1, 500.0, 20.0, 1.0)
        factor_sd = st.number_input("Model-factor standard deviation", 0.01, 1.0, 0.21, 0.01)
        samples = st.select_slider("Monte Carlo samples", [250, 500, 1000, 2000], value=1000)

    uncertainty = UncertaintyInputs(
        flaw_length_mm=length_sd,
        flaw_depth_mm=depth_sd,
        wall_thickness_mm=wall_sd,
        operating_pressure_psi=pressure_sd,
        model_factor=factor_sd,
    )
    if st.button("Run the POF simulation", type="primary", width="stretch"):
        with st.spinner("Sampling uncertain inputs and evaluating the limit state..."):
            st.session_state["education_pof_result"] = simulate_probability_of_failure(
                inputs, uncertainty, samples=samples, seed=7
            )
            st.session_state["education_pof_case"] = inputs

    result = st.session_state.get("education_pof_result")
    if result:
        pof = float(result["probability_of_failure"])
        pof_1, pof_2, pof_3 = st.columns(3)
        pof_1.metric("Estimated POF", f"{pof:.3e}")
        pof_2.metric("Failure samples", f"{result['failures']:,}")
        pof_3.metric("Total samples", f"{result['samples']:,}")
        if result.get("samples", 0) < 1000:
            st.caption("Use more samples for a more stable classroom estimate.")
    else:
        st.info("Run the simulation to calculate the classroom POF estimate.")

    st.markdown("#### Probability-density plot")
    variable = st.selectbox(
        "Choose an uncertain input",
        ["Crack depth", "Crack length", "Wall thickness", "Operating pressure"],
    )
    pdf_options = {
        "Crack depth": (depth, depth_sd, "mm"),
        "Crack length": (length, length_sd, "mm"),
        "Wall thickness": (wall, wall_sd, "mm"),
        "Operating pressure": (pressure, pressure_sd, "psi"),
    }
    pdf_mean, pdf_sd, pdf_unit = pdf_options[variable]
    x_values, density = normal_pdf_curve(pdf_mean, pdf_sd)
    pdf_frame = pd.DataFrame({f"Value ({pdf_unit})": x_values, "Probability density": density})
    st.line_chart(pdf_frame, x=f"Value ({pdf_unit})", y="Probability density")
    st.caption(
        "The curve shows which input values are more or less likely. Its total area equals 1; "
        "the vertical value is density, not probability at a single point."
    )

with decision_tab:
    st.subheader("Interpret the result before choosing an action")
    result = st.session_state.get("education_pof_result")
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
