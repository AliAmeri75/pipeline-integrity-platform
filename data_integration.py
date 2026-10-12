"""Prepare crack and corrosion profiles for inspection-planning modules."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from platform_ui import render_project_hero
from profile_data import (
    ProfileFormatError,
    maximum_depth_envelope,
    parse_profile_workbook,
    summary_csv,
    summary_xlsx,
)


@st.cache_data(show_spinner=False)
def _read_profiles(content: bytes) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    return parse_profile_workbook(content)


render_project_hero(
    "Data preparation",
    "Data Integration",
    "Upload crack or corrosion grid profiles, inspect each depth map, and prepare feature size and location inputs for inspection planning.",
)

st.markdown(
    """
    <div class="notice"><strong>What this module does.</strong> It reads the profile
    sheets without changing the source workbook, plots each measured depth profile, and
    creates one summary row per feature with its location, maximum depth, length, and width.</div>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader(
    "Upload a profile workbook",
    type=["xlsm", "xlsx"],
    help=(
        "Use a TCAT/Psqr-style workbook in which each feature sheet contains "
        "longitudinal coordinates, circumferential coordinates, and a depth grid."
    ),
)

if uploaded_file is None:
    st.subheader("Simple workflow")
    st.markdown(
        """
        1. Upload the Excel or macro-enabled Excel profile workbook.
        2. Select a detected feature and review its 2D depth map and axial profile.
        3. Download the complete size-and-location table as Excel or CSV.
        """
    )
    st.info(
        "The uploaded workbook stays unchanged. Macros are not run; only stored cell values are read."
    )
    st.stop()

try:
    with st.spinner("Reading profile grids…"):
        summary, profiles = _read_profiles(uploaded_file.getvalue())
except ProfileFormatError as error:
    st.error(str(error))
    st.stop()

st.success(f"Detected {len(summary):,} feature profiles in {uploaded_file.name}.")
defect_type = st.selectbox(
    "Profile type",
    ["Corrosion / metal loss", "Crack"],
    help="This label is included in the downloaded size-and-location table.",
)
summary = summary.copy()
summary["Defect type"] = defect_type

profile_ids = summary["Profile ID"].astype(str).tolist()
selected_profile_id = st.selectbox(
    "Feature profile",
    profile_ids,
    format_func=lambda profile_id: (
        f"Profile {profile_id} · Feature "
        f"{summary.loc[summary['Profile ID'].astype(str) == profile_id, 'Feature ID'].iloc[0]}"
    ),
)
selected_row = summary.loc[
    summary["Profile ID"].astype(str) == selected_profile_id
].iloc[0]
selected_profile = profiles[selected_profile_id]

st.subheader("Selected profile")
metric_columns = st.columns(4)
metric_columns[0].metric("Feature location", f"{selected_row['Feature location (m)']:,.3f} m")
metric_columns[1].metric("Maximum depth", f"{selected_row['Maximum depth (%WT)']:,.1f}% WT")
maximum_depth_mm = selected_row["Maximum depth (mm)"]
metric_columns[2].metric(
    "Maximum depth",
    "Unavailable" if pd.isna(maximum_depth_mm) else f"{maximum_depth_mm:,.3f} mm",
)
metric_columns[3].metric("Profile length", f"{selected_row['Profile length (mm)']:,.1f} mm")

depth_domain = [0.0, max(float(selected_row["Maximum depth (%WT)"]), 1.0)]
heatmap = (
    alt.Chart(selected_profile)
    .mark_rect()
    .encode(
        x=alt.X("Axial cell start (mm):Q", title="Axial distance from profile start (mm)"),
        x2="Axial cell end (mm):Q",
        y=alt.Y("Circumferential cell start (mm):Q", title="Circumferential distance (mm)"),
        y2="Circumferential cell end (mm):Q",
        color=alt.Color(
            "Depth (%WT):Q",
            title="Depth (%WT)",
            scale=alt.Scale(domain=depth_domain, scheme="yelloworangered"),
        ),
        tooltip=[
            alt.Tooltip("Axial offset (mm):Q", format=".2f"),
            alt.Tooltip("Circumferential offset (mm):Q", format=".2f"),
            alt.Tooltip("Depth (%WT):Q", format=".2f"),
        ],
    )
    .properties(height=390, title=f"Depth map · profile {selected_profile_id}")
)

max_depth_rows = selected_profile[
    selected_profile["Depth (%WT)"] == selected_profile["Depth (%WT)"].max()
]
maximum_marker = (
    alt.Chart(max_depth_rows)
    .mark_point(filled=True, color="#155987", size=95, stroke="white", strokeWidth=1.5)
    .encode(
        x="Axial offset (mm):Q",
        y="Circumferential offset (mm):Q",
        tooltip=[alt.Tooltip("Depth (%WT):Q", title="Maximum depth (%WT)", format=".2f")],
    )
)
st.altair_chart(heatmap + maximum_marker, width="stretch")

envelope = maximum_depth_envelope(selected_profile)
profile_area = (
    alt.Chart(envelope)
    .mark_area(line={"color": "#275d38", "strokeWidth": 3}, color="#b9d4c0", opacity=0.72)
    .encode(
        x=alt.X("Axial offset (mm):Q", title="Axial distance from profile start (mm)"),
        y=alt.Y("Maximum depth (%WT):Q", title="Maximum depth across profile (%WT)"),
        tooltip=[
            alt.Tooltip("Axial offset (mm):Q", format=".2f"),
            alt.Tooltip("Maximum depth (%WT):Q", format=".2f"),
        ],
    )
    .properties(height=275, title="Maximum-depth profile along feature length")
)
st.altair_chart(profile_area, width="stretch")

st.subheader("Size and location output")
st.caption(
    "Maximum depth is calculated from the profile grid. Depth in millimetres uses the "
    "recorded wall thickness. Profile length and width follow the workbook values when available."
)
st.dataframe(summary, width="stretch", hide_index=True)

download_columns = st.columns(2)
download_columns[0].download_button(
    "Download Excel summary",
    data=summary_xlsx(summary),
    file_name="crack_corrosion_size_location_summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
download_columns[1].download_button(
    "Download CSV summary",
    data=summary_csv(summary),
    file_name="crack_corrosion_size_location_summary.csv",
    mime="text/csv",
    use_container_width=True,
)

st.markdown(
    '<div class="notice"><strong>Review before use.</strong> Confirm the detected units, '
    'feature identifiers, and profile boundaries before passing the summary to an inspection-planning model.</div>',
    unsafe_allow_html=True,
)
