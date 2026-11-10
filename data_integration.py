"""Explore crack and corrosion profiles for inspection-planning modules."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from platform_ui import render_project_hero
from exploration_map import render_exploration_map
from project_editor import get_project,render_project_editor,publish_project
from exploration_input_ui import render_route_inputs,add_map_defect,set_route
from assessment_project import validate_project,assessment_geometry
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
    "Maintenance Planning (Cracks/Corrosion/Dents)",
    "Data Exploration",
    "Define the pipeline route, defects, segment properties and uncertainties once, then use the same saved dataset for preliminary assessment and crack inspection planning.",
)

st.markdown(
    """
    <div class="notice"><strong>Start here.</strong> Enter or edit defect sizes in a table,
    upload a CSV/Excel size register, or load measured profile sheets. Draw, enter or upload
    the pipeline route, then save this dataset for all analyses.</div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Choose a data source")
st.caption('Choosing a source creates a separate draft, not an appended dataset. '
    'The active analysis dataset changes only when you click Save shared dataset for all analyses.')
data_source = st.radio(
    "Data source",
    ["Enter / edit defects", "Sample crack profiles", "Sample corrosion profiles", "Sample dent data",
     "Upload your workbook", "Upload dent CSV / Excel"],
    horizontal=True,
    label_visibility="collapsed",
)

if data_source in ('Sample dent data','Upload dent CSV / Excel'):
    from dent_exploration import render_dent_exploration
    render_dent_exploration(is_sample=data_source=='Sample dent data')
    st.stop()

if data_source == "Enter / edit defects":
    current=get_project()
    source_content=current.get('workbook',b'')
    source_name=current['source']
    summary,profiles=current['summary'].copy(),current['profiles']
    st.info('Edit the defect register below, upload a size table, or add defects by distance or map pin. '
        'The editor starts from your saved dataset.')
elif data_source == "Sample crack profiles":
    source_content = synthetic_sample_workbook()
    source_name = "sample_crack_profiles.xlsx"
    st.info("Sample data for crack profiles.")
    st.download_button(
        "Download the sample crack profiles",
        data=source_content,
        file_name=source_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
elif data_source=='Sample corrosion profiles':
    from exploration_datasets import sample_corrosion_workbook
    source_content=sample_corrosion_workbook()
    source_name='sample_corrosion_profiles.xlsx'
    st.info('Sample data for corrosion profiles. Three synthetic metal-loss profiles on a 10 km pipe.')
    st.download_button('Download the sample corrosion profiles',source_content,source_name,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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
    uploaded_defect_type=st.selectbox('Defect type in this workbook',['Corrosion / metal loss','Crack'])
    st.caption('Upload measured crack/corrosion depth grids here. Dent displacements use Upload dent CSV / Excel.')

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

if data_source != 'Enter / edit defects':
    try:
        with st.spinner("Reading profile grids…"):
            summary, profiles = _read_profiles(source_content)
    except ProfileFormatError as error:
        st.error(str(error))
        st.stop()

if data_source in ('Sample crack profiles','Sample corrosion profiles'):
    st.success(f"Loaded {len(summary):,} sample {'crack' if data_source=='Sample crack profiles' else 'corrosion'} profiles.")
elif data_source != 'Enter / edit defects':
    st.success(f"Detected {len(summary):,} feature profiles in {source_name}.")
if data_source != 'Enter / edit defects':
    defect_type = ('Crack' if data_source=='Sample crack profiles' else
        'Corrosion / metal loss' if data_source=='Sample corrosion profiles' else uploaded_defect_type)
    summary = summary_for_defect_type(summary, defect_type)
else:
    defect_type='Crack'
st.session_state["prepared_profile_workbook"] = source_content
st.session_state["prepared_profile_source_name"] = source_name
st.session_state["prepared_profile_defect_type"] = defect_type
with st.expander('Define shared defects, pipe segments and uncertainties',expanded=True):
    if data_source=='Enter / edit defects':
        draft=render_project_editor(summary,profiles,source_content,True,
            initial_project=current,source_token='editable-defect-register-v1')
    elif data_source=='Sample corrosion profiles':
        from exploration_datasets import corrosion_project
        draft=render_project_editor(summary,profiles,source_content,True,initial_project=corrosion_project(source_content))
    else:
        draft=render_project_editor(summary,profiles,source_content,data_source=='Sample crack profiles',
            source_type=defect_type)
summary=draft['summary']
profiles=draft['profiles']

profile_ids = summary["Profile ID"].astype(str).tolist()
selection_key='exploration_selected_profile'
if st.session_state.get(selection_key) not in profile_ids:
    st.session_state[selection_key]=profile_ids[0] if profile_ids else ''
st.subheader('Pipeline and defect locations')
st.write('Draw the pipeline or enter/upload its coordinates. Use the pin tool to add a defect with the dimensions '
    'entered above. Click an existing defect marker to inspect its shape below.')
render_route_inputs(draft)
render_exploration_map(summary,st.session_state[selection_key],selection_key=selection_key,shared_project=True,
    on_add_defect=lambda lat,lon:add_map_defect(draft,lat,lon),
    on_route_change=lambda route:set_route(draft,route))
publish_project(draft)
if not profile_ids:
    st.info('Add a defect in the table, by distance, by map pin or by CSV/Excel upload to see its profile.')
    st.stop()
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
        'Depth in mm is unchanged; profile %WT refers to its original input WT. Save drafts before analysis.')
except (ValueError,KeyError,TypeError):
    st.caption('Showing inspection-workbook geometry until the draft segment register is valid.')

st.subheader("Selected profile")
illustrative=bool(selected_profile.attrs.get('illustrative'))
if illustrative:
    st.info('Illustrative shape from entered depth and length. No measured profile grid was supplied for this defect. '
        'The analyses use the entered dimensions and the saved segment properties.')
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
    "This view places the profile on a pipe for context. The surface "
    "depression is enlarged so it can be seen; colour and tooltips retain the input depth."
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

st.markdown('#### '+('Illustrative' if illustrative else 'Measured')+' 2D and 3D profile')
st.write(
    "Move the pointer over either figure to inspect the same location in both "
    "views. Colour and the readout show depth; the 3D vertical scale is "
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
if illustrative:
    st.caption('Size-only records use the entered maximum depth and length. '
        'Their displayed shapes are illustrative; unchanged measured profiles retain their original grids.')
elif defect_type == "Crack":
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
    "Save the shared dataset above, then choose Crack or Corrosion in Preliminary Analysis. "
    "Each workspace uses its own resistance and reliability model with the same saved pipe and defects."
)
if st.button('Open Preliminary Analysis'):
    st.session_state['preliminary_threat']='Crack' if defect_type=='Crack' else 'Corrosion'
    st.switch_page('preliminary_analysis.py')
