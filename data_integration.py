"""Explore crack and corrosion profiles for inspection-planning modules."""

from __future__ import annotations

import altair as alt
import json
import pandas as pd
import streamlit as st

from platform_ui import render_project_hero
from exploration_map import render_exploration_map
from project_editor import render_project_editor,publish_project
from assessment_project import validate_project,assessment_geometry
from profile_map import route_length_km
from profile_data import (
    ProfileFormatError,
    maximum_depth_envelope,
    parse_profile_workbook,
    summary_csv,
    summary_for_defect_type,
    summary_xlsx,
    synthetic_sample_workbook,
)
from profile_visuals import (
    measured_profile_on_pipe_figure,
    render_linked_measured_profile,
)


@st.cache_data(show_spinner=False)
def _read_profiles(content: bytes) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    return parse_profile_workbook(content)


render_project_hero(
    "Maintenance Planning (Cracks/Corrosion)",
    "Data Exploration",
    "Define the pipeline route, defects, segment properties and uncertainties once, then use the same saved dataset for preliminary assessment.",
)

st.markdown(
    """
    <div class="notice"><strong>What this module does.</strong> It reads the profile
    sheets without changing the source workbook. Link each feature to its route chainage
    and pipe-property segment, review its measured profile, and save the common assessment dataset.</div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Choose a data source")
data_source = st.radio(
    "Data source",
    ["Sample crack profiles", "Upload your workbook"],
    horizontal=True,
    label_visibility="collapsed",
)

if data_source == "Sample crack profiles":
    source_content = synthetic_sample_workbook()
    source_name = "sample_crack_profiles.xlsx"
    st.info("Sample data for crack profiles.")
    st.download_button(
        "Download the sample crack profiles",
        data=source_content,
        file_name=source_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    uploaded_file = st.file_uploader(
        "Upload a profile workbook",
        type=["xlsm", "xlsx"],
        help=(
            "Use a TCAT/Psqr-style workbook in which each feature sheet contains "
            "longitudinal coordinates, circumferential coordinates, and a depth grid."
        ),
    )
    source_content = uploaded_file.getvalue() if uploaded_file is not None else None
    source_name = uploaded_file.name if uploaded_file is not None else ""

if source_content is None:
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
        summary, profiles = _read_profiles(source_content)
except ProfileFormatError as error:
    st.error(str(error))
    st.stop()

if data_source == "Sample crack profiles":
    st.success(f"Loaded {len(summary):,} sample crack profiles.")
else:
    st.success(f"Detected {len(summary):,} feature profiles in {source_name}.")
defect_type = 'Crack' if data_source == 'Sample crack profiles' else 'Corrosion / metal loss'
summary = summary_for_defect_type(summary, defect_type)
st.session_state["prepared_profile_workbook"] = source_content
st.session_state["prepared_profile_source_name"] = source_name
st.session_state["prepared_profile_defect_type"] = defect_type
with st.expander('Define shared defects, pipe segments and uncertainties',expanded=False):
    draft=render_project_editor(summary,profiles,source_content,data_source=='Sample crack profiles')
summary=draft['summary']

profile_ids = summary["Profile ID"].astype(str).tolist()
selection_key='exploration_selected_profile'
if st.session_state.get(selection_key) not in profile_ids:
    st.session_state[selection_key]=profile_ids[0]
st.subheader('Pipeline and defect locations')
st.write('Start with the pipeline map. Click a defect marker or choose a profile below to inspect its 3D shape on the pipe and its measured depth profile.')
with st.expander('Upload a pipeline centreline (GeoJSON)'):
    route_upload=st.file_uploader('Route LineString or LineString Feature',type=['geojson','json'],key='shared_route_upload')
    if route_upload is not None and st.button('Apply uploaded centreline'):
        try:
            document=json.loads(route_upload.getvalue())
            geometry=document.get('geometry',document)
            if geometry['type']!='LineString': raise ValueError('Use a single GeoJSON LineString.')
            route=[[float(lat),float(lon)] for lon,lat in geometry['coordinates']]
            if route_length_km(route)<=0: raise ValueError('The route must have positive length.')
            st.session_state.data_exploration_map_route=route
            st.session_state.data_exploration_map_revision=st.session_state.get('data_exploration_map_revision',0)+1
            st.rerun()
        except (ValueError,TypeError,KeyError) as error:
            st.error('Route not applied: '+str(error))
render_exploration_map(summary,st.session_state[selection_key],selection_key=selection_key,shared_project=True)
publish_project(draft)
selected_profile_id = st.selectbox(
    "Feature profile",
    profile_ids,
    key=selection_key,
    format_func=lambda profile_id: (
        f"Profile {profile_id} · Feature "
        f"{summary.loc[summary['Profile ID'].astype(str) == profile_id, 'Feature ID'].iloc[0]}"
    ),
)
selected_row = summary.loc[
    summary["Profile ID"].astype(str) == selected_profile_id
].iloc[0]
selected_profile = profiles[selected_profile_id]
defect_type=str(selected_row['Defect type'])
try:
    display_summary,display_profiles=assessment_geometry(validate_project(draft))
    selected_row=display_summary.loc[display_summary['Profile ID'].astype(str)==selected_profile_id].iloc[0]
    selected_profile=display_profiles[selected_profile_id]
    st.caption(f'3D preview: property segment {int(selected_row["Segment ID"])} · '
        f'WT {selected_row["Wall thickness (mm)"]:.3f} mm · '
        f'outside diameter {selected_row["Outside diameter (mm)"]:.1f} mm. '
        'Measured depth in mm is unchanged; workbook %WT refers to its original inspection WT. Save drafts before analysis.')
except (ValueError,KeyError,TypeError):
    st.caption('Showing inspection-workbook geometry until the draft segment register is valid.')

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

st.caption(
    "Profile axes show position in millimetres. When wall thickness is available, "
    "colour and tooltips show depth in millimetres; otherwise they show %WT."
)

st.markdown("#### 3D pipe and selected defect")
st.caption(
    "This view places the measured grid on a pipe for context. The surface "
    "depression is enlarged so it can be seen; colour and tooltips retain the "
    "measured depth."
)
st.plotly_chart(
    measured_profile_on_pipe_figure(
        selected_profile,
        selected_row["Wall thickness (mm)"],
        selected_row["Outside diameter (mm)"],
        selected_profile_id,
        defect_type,
    ),
    width="stretch",
)

st.markdown("#### Measured 2D and 3D profile")
st.write(
    "Move the pointer over either figure to inspect the same measured cell in both "
    "views. Colour and the readout show the recorded depth; the 3D vertical scale is "
    "enlarged only to make the shape visible."
)
render_linked_measured_profile(
    selected_profile,
    selected_row["Wall thickness (mm)"],
    selected_profile_id,
)

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
if defect_type == "Crack":
    st.caption(
        "Maximum crack depth is calculated from the profile grid. Depth in millimetres uses "
        "the recorded wall thickness. Crack outputs report depth and length; width is not included."
    )
else:
    st.caption(
        "Maximum depth is calculated from the profile grid. Depth in millimetres uses the "
        "recorded wall thickness. Profile length and width follow the workbook values when available."
    )
st.dataframe(summary, width="stretch", hide_index=True)

output_stem = (
    "crack_size_location_summary"
    if defect_type == "Crack"
    else "corrosion_size_location_summary"
)
download_columns = st.columns(2)
download_columns[0].download_button(
    "Download Excel summary",
    data=summary_xlsx(summary),
    file_name=f"{output_stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
download_columns[1].download_button(
    "Download CSV summary",
    data=summary_csv(summary),
    file_name=f"{output_stem}.csv",
    mime="text/csv",
    use_container_width=True,
)

st.markdown(
    '<div class="notice"><strong>Review before use.</strong> Confirm the detected units, '
    'feature identifiers, and profile boundaries before passing the summary to an inspection-planning model.</div>',
    unsafe_allow_html=True,
)

st.subheader("Next: Preliminary Analysis")
st.write(
    "Use the explored crack dimensions to estimate burst resistance pressure, "
    "failure pressure ratio (FPR), and probability of failure (POF) for each profile."
)
if st.button('Open Preliminary Analysis'):
    st.switch_page('preliminary_analysis.py')
