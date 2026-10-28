"""Preliminary failure analysis for prepared crack profiles."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from education.pof_model import POFInputs, UncertaintyInputs
from platform_ui import render_project_hero
from preliminary_analysis_model import analyze_crack_profiles
from profile_data import (
    ProfileFormatError,
    parse_profile_workbook,
    summary_for_defect_type,
    summary_xlsx,
    synthetic_sample_workbook,
)


@st.cache_data(show_spinner=False)
def _read_profiles(content: bytes) -> pd.DataFrame:
    summary, _ = parse_profile_workbook(content)
    return summary_for_defect_type(summary, "Crack")


@st.cache_data(show_spinner=False)
def _run_analysis(
    summary: pd.DataFrame,
    base_inputs: POFInputs,
    uncertainty: UncertaintyInputs,
    samples: int,
    seed: int,
) -> pd.DataFrame:
    return analyze_crack_profiles(
        summary,
        base_inputs,
        uncertainty,
        samples=samples,
        seed=seed,
    )


render_project_hero(
    "Data Preparation",
    "Preliminary Analysis",
    "Estimate burst resistance pressure, failure pressure ratio (FPR), and probability of failure (POF) for each prepared crack profile.",
)

st.markdown(
    """
    <div class="notice"><strong>Preliminary screening only.</strong> The crack calculations
    use the platform's CorLAS-based teaching model. They require engineering review and do
    not replace validated operator models, applicable codes, or regulatory requirements.</div>
    """,
    unsafe_allow_html=True,
)

st.subheader("1. Choose crack-profile data")
prepared_content = st.session_state.get("prepared_profile_workbook")
prepared_type = st.session_state.get("prepared_profile_defect_type")
prepared_name = st.session_state.get("prepared_profile_source_name", "prepared workbook")
source_options = ["Sample crack profiles", "Upload your workbook"]
if prepared_content is not None and prepared_type == "Crack":
    source_options.insert(0, "Use profiles from Data Preparation")
elif prepared_content is not None:
    st.info(
        "The profiles currently prepared in this session are labelled as corrosion. "
        "This preliminary analysis currently uses a crack-specific model."
    )
data_source = st.radio(
    "Data source",
    source_options,
    horizontal=True,
    label_visibility="collapsed",
)

if data_source == "Use profiles from Data Preparation":
    source_content = prepared_content
    st.info(f"Using {prepared_name} from the Data Preparation Module.")
elif data_source == "Sample crack profiles":
    source_content = synthetic_sample_workbook()
    st.info("Sample data for crack profiles.")
else:
    uploaded_file = st.file_uploader(
        "Upload a crack-profile workbook",
        type=["xlsm", "xlsx"],
        help=(
            "Use the same TCAT/Psqr-style profile workbook accepted by the "
            "Data Preparation Module."
        ),
    )
    source_content = uploaded_file.getvalue() if uploaded_file is not None else None

if source_content is None:
    st.info("Upload a workbook to begin the preliminary analysis.")
    st.stop()

try:
    with st.spinner("Reading crack profiles…"):
        crack_summary = _read_profiles(source_content)
except ProfileFormatError as error:
    st.error(str(error))
    st.stop()

st.success(f"Prepared {len(crack_summary):,} crack profiles for analysis.")
st.dataframe(
    crack_summary[
        [
            "Profile ID",
            "Feature ID",
            "Feature location (m)",
            "Maximum depth (mm)",
            "Profile length (mm)",
            "Wall thickness (mm)",
            "Outside diameter (mm)",
        ]
    ],
    width="stretch",
    hide_index=True,
)

st.subheader("2. Define shared analysis inputs")
st.caption(
    "Pipe geometry and crack dimensions come from each profile. The material, pressure, "
    "and uncertainty values below are applied to all profiles."
)

with st.form("preliminary_analysis_inputs"):
    material_column, pressure_column = st.columns(2)
    with material_column:
        st.markdown("**Material model**")
        yield_strength = st.number_input(
            "Yield strength (psi)", 10000.0, 150000.0, 57200.0, 500.0
        )
        ultimate_strength = st.number_input(
            "Ultimate strength (psi)", 10001.0, 180000.0, 73920.0, 500.0
        )
        elastic_modulus = st.number_input(
            "Elastic modulus (GPa)", 50.0, 300.0, 210.0, 1.0
        )
        charpy_energy = st.number_input("Charpy energy", 1.0, 300.0, 85.0, 1.0)
    with pressure_column:
        st.markdown("**Pressure and model**")
        operating_pressure = st.number_input(
            "Operating pressure (psi)", 100.0, 3000.0, 936.0, 10.0
        )
        model_factor = st.number_input("Model factor, θ", 0.1, 3.0, 1.27, 0.01)
        safety_factor = st.number_input("Safety factor", 1.0, 5.0, 2.0, 0.05)

    with st.expander("POF uncertainty inputs", expanded=False):
        uncertainty_columns = st.columns(3)
        length_sd = uncertainty_columns[0].number_input(
            "Crack length SD (mm)", 0.001, 200.0, 15.6, 0.1
        )
        depth_sd = uncertainty_columns[1].number_input(
            "Crack depth SD (mm)", 0.001, 20.0, 0.74, 0.01
        )
        wall_sd = uncertainty_columns[2].number_input(
            "Wall thickness SD (mm)", 0.001, 20.0, 0.60, 0.01
        )
        pressure_sd = uncertainty_columns[0].number_input(
            "Operating pressure SD (psi)", 0.001, 1000.0, 20.0, 1.0
        )
        model_factor_sd = uncertainty_columns[1].number_input(
            "Model factor SD", 0.001, 2.0, 0.21, 0.01
        )
        samples = uncertainty_columns[2].number_input(
            "Monte Carlo samples per profile", 100, 10000, 1000, 100
        )
        seed = st.number_input("Random seed", 0, 1000000, 7, 1)

    run_analysis = st.form_submit_button(
        "Run Preliminary Analysis", type="primary", use_container_width=True
    )

if not run_analysis:
    st.info("Set the shared inputs, then run the analysis.")
    st.stop()

if ultimate_strength <= yield_strength:
    st.error("Ultimate strength must exceed yield strength.")
    st.stop()

base_inputs = POFInputs(
    yield_strength_psi=yield_strength,
    ultimate_strength_psi=ultimate_strength,
    elastic_modulus_gpa=elastic_modulus,
    charpy_energy=charpy_energy,
    operating_pressure_psi=operating_pressure,
    model_factor=model_factor,
    safety_factor=safety_factor,
)
uncertainty = UncertaintyInputs(
    flaw_length_mm=length_sd,
    flaw_depth_mm=depth_sd,
    wall_thickness_mm=wall_sd,
    operating_pressure_psi=pressure_sd,
    model_factor=model_factor_sd,
)

workload = len(crack_summary) * int(samples)
if workload > 250000:
    st.warning(
        f"This run evaluates approximately {workload:,} Monte Carlo cases and may take time."
    )

with st.spinner("Calculating deterministic results and POF for each crack profile…"):
    results = _run_analysis(
        crack_summary,
        base_inputs,
        uncertainty,
        int(samples),
        int(seed),
    )

st.subheader("3. Preliminary results")
st.caption(
    "Burst resistance pressure is the model-predicted failure pressure. "
    "FPR = burst resistance pressure ÷ operating pressure. POF is the fraction of "
    "Monte Carlo samples with limit-state margin g ≤ 0."
)
st.dataframe(
    results,
    width="stretch",
    hide_index=True,
    column_config={
        "Burst resistance pressure (psi)": st.column_config.NumberColumn(format="%.1f"),
        "FPR": st.column_config.NumberColumn(format="%.3f"),
        "POF": st.column_config.NumberColumn(format="%.3e"),
    },
)

calculated = results[results["Status"] == "Calculated"].copy()
if calculated.empty:
    st.error("No crack profile could be calculated. Review the geometry and material inputs.")
else:
    highest_pof_row = calculated.loc[calculated["POF"].astype(float).idxmax()]
    lowest_fpr_row = calculated.loc[calculated["FPR"].astype(float).idxmin()]
    metric_columns = st.columns(3)
    metric_columns[0].metric("Profiles calculated", f"{len(calculated):,}")
    metric_columns[1].metric(
        "Highest estimated POF",
        f"{float(highest_pof_row['POF']):.3e}",
        help=f"Profile {highest_pof_row['Profile ID']}",
    )
    metric_columns[2].metric(
        "Lowest FPR",
        f"{float(lowest_fpr_row['FPR']):.3f}",
        help=f"Profile {lowest_fpr_row['Profile ID']}",
    )

    pof_chart = (
        alt.Chart(calculated)
        .mark_bar(color="#275d38")
        .encode(
            x=alt.X("Profile ID:N", title="Crack profile", sort=None),
            y=alt.Y("POF:Q", title="Estimated probability of failure"),
            tooltip=[
                "Profile ID:N",
                alt.Tooltip("POF:Q", format=".3e"),
                alt.Tooltip("FPR:Q", format=".3f"),
                alt.Tooltip("Burst resistance pressure (psi):Q", format=",.1f"),
            ],
        )
        .properties(height=320, title="Estimated POF by crack profile")
    )
    st.altair_chart(pof_chart, width="stretch")

download_columns = st.columns(2)
download_columns[0].download_button(
    "Download Preliminary Analysis as Excel",
    data=summary_xlsx(results),
    file_name="crack_preliminary_analysis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
download_columns[1].download_button(
    "Download Preliminary Analysis as CSV",
    data=results.to_csv(index=False, float_format="%.8g").encode("utf-8-sig"),
    file_name="crack_preliminary_analysis.csv",
    mime="text/csv",
    use_container_width=True,
)

st.info(
    "Corrosion profiles require a corrosion-specific resistance model. This preliminary "
    "page currently applies only to crack profiles."
)
