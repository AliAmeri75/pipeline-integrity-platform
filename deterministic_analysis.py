"""Deterministic FPR workflow with selectable measured defect visualizations."""
import pandas as pd
import streamlit as st
from deterministic_flags import flag_profiles,fpr_distance_figure,SEVERE_LABEL
from profile_data import summary_xlsx
from profile_visuals import render_linked_measured_profile,measured_profile_on_pipe_figure
from corlas_profile_map import evaluate_profile_grid,minimum_grid_result,corlas_depth_pressure_figure
from project_editor import get_project
from assessment_project import (deterministic_project,project_signature,segment_inputs,assessment_geometry)


@st.cache_data(show_spinner=False)
def _corlas_measured_grid(profile,base,wall,diameter,length):
    return evaluate_profile_grid(profile,base,wall,diameter,length)


def _select_table(key,profile_ids):
    selection = st.session_state[key]['selection']['rows']
    if selection:
        st.session_state.det_selected_profile = profile_ids[int(selection[0])]


def _select_chart(key):
    points = st.session_state[key]['selection']['points']
    if points:
        custom = points[0].get('customdata')
        if custom is not None:
            st.session_state.det_selected_profile = str(custom[0] if isinstance(custom,list) else custom)


def render_deterministic_analysis():
    st.subheader('Deterministic Analysis')
    st.write('Calculate burst resistance and FPR for each crack, then inspect its measured 2D/3D shape on the pipe.')
    project=get_project()
    summary,profiles=assessment_geometry(project)
    st.info('Using the saved Data Exploration dataset: '+project['source']+'. '
            'Edit the route, defects, segment properties and uncertainties in Data Exploration—not here.')
    st.caption('Crack resistance uses the existing CorLAS model. Corrosion can be visualized, '
               'but FPR is marked unavailable until a corrosion-specific resistance model is selected.')
    with st.expander('Review shared segment properties'):
        st.dataframe(project['segments'],hide_index=True,width='stretch')
    run=st.button('Run Deterministic Analysis',type='primary')
    signature=project_signature(project)
    if run:
        try:
            result=deterministic_project(project)
            st.session_state.deterministic_output = (signature,result)
        except (ValueError,KeyError,TypeError) as error:
            st.error(str(error))
    saved = st.session_state.get('deterministic_output')
    if saved and saved[0]!=signature:
        st.info('Inputs changed. Run Deterministic Analysis again to update the FPR results.')
    result = saved[1] if saved and saved[0]==signature else None
    if result is not None:
        result = flag_profiles(result)
        st.markdown('**FPR for each defect**')
        st.caption('FPR = unadjusted burst resistance pressure / operating pressure. '
                   'Click a row or a point below to open that measured defect in 3D. '
                   'An FPR above 1 alone does not establish code compliance or asset safety.')
        st.caption('User-selected screening flags: FPR < 1.1 OR maximum depth > 50% of wall thickness. '
                   'Red circles mark Severe → immediate action! These flags are not a code-compliance or repair assessment.')
        table_key = 'det_result_table_'+signature
        st.dataframe(result,hide_index=True,width='stretch',key=table_key,
            on_select=lambda:_select_table(table_key,result['Profile ID'].astype(str).tolist()),
            selection_mode='single-row',column_config={'FPR':st.column_config.NumberColumn(format='%.3f')})
        calculated = result[result.Status=='Calculated'].copy()
        if not calculated.empty:
            figure = fpr_distance_figure(result)
            chart_key = 'det_result_chart_'+signature
            st.plotly_chart(figure,width='stretch',theme=None,key=chart_key,on_select=lambda:_select_chart(chart_key),selection_mode='points')
            sections = result.groupby('Segment ID',as_index=False).agg(
                **{'Lowest calculated FPR':('FPR','min'),'Recorded defects':('Profile ID','size'),
                   'Calculated defects':('FPR','count')})
            sections=sections.merge(project['segments'][['section_id','start_km','end_km']],
                left_on='Segment ID',right_on='section_id').drop(columns='section_id')
            st.markdown('**Lowest calculated defect FPR in each represented property segment**')
            st.caption('This is the minimum defect FPR, not a segment reliability calculation. '
                       'Sections with unrecorded defects are not assessed; unavailable FPR values are excluded from the minimum.')
            st.dataframe(sections,hide_index=True,width='stretch')
            st.download_button('Download section FPR summary',sections.to_csv(index=False),'section_fpr.csv','text/csv')
        st.download_button('Download deterministic results CSV',result.to_csv(index=False),'deterministic_fpr.csv','text/csv')
        st.download_button('Download deterministic results Excel',summary_xlsx(result),'deterministic_fpr.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        st.info('Run Deterministic Analysis to calculate the full profile and section tables. '
                'For crack profiles, the selected-profile CorLAS heatmaps are already available below.')
    # Keep measured geometry available even when resistance is unsupported/invalid.
    ids = summary['Profile ID'].astype(str).tolist()
    if st.session_state.get('det_selected_profile') not in ids:
        st.session_state.det_selected_profile = ids[0]
    selected = st.selectbox('Selected defect — 2D/3D view',ids,key='det_selected_profile')
    row = summary.loc[summary['Profile ID'].astype(str)==selected].iloc[0]
    defect_type=str(row['Defect type'])
    base=segment_inputs(project,int(row['Segment ID']))
    st.markdown('**Selected defect on the pipe**')
    if result is not None:
        chosen = result.loc[result['Profile ID'].astype(str)==selected].iloc[0]
        st.write(f'Profile {selected} · {defect_type} · '+
            (f'FPR {chosen.FPR:.3f}' if pd.notna(chosen.FPR) else str(chosen.Status)))
        if chosen['Severe']:
            st.error(SEVERE_LABEL+' '+chosen['Screening reason'])
    if defect_type=='Crack':
        st.subheader('Measured depth and CorLAS burst pressure')
        st.caption('Uses the saved properties of this defect’s segment. Absolute measured depths are '
                   'preserved when assessment wall thickness differs from the inspection workbook.')
        try:
            with st.spinner('Evaluating CorLAS at the measured depths…'):
                cells=_corlas_measured_grid(profiles[selected],base,row['Wall thickness (mm)'],
                    row['Outside diameter (mm)'],row['Profile length (mm)'])
            lowest=minimum_grid_result(cells)
            cards=st.columns(3)
            cards[0].metric('Minimum calculated FPR · '+selected,
                f'{lowest["FPR"]:.3f}' if lowest else 'Unavailable',border=True)
            cards[1].metric('Minimum CorLAS burst pressure',
                f'{lowest["Burst resistance pressure (psi)"]:,.1f} psi' if lowest else 'Unavailable',border=True)
            cards[2].metric('Grid cells evaluated',f'{int((cells.Status=="Calculated").sum())} / {len(cells)}',border=True)
            st.caption('Every calculated cell uses its measured depth, the full profile length '
                f'({row["Profile length (mm)"]:.2f} mm), and the same pipe/material inputs. '
                'This is a depth-sensitivity screening map, not a set of independent cell-sized cracks or a profile-interaction analysis. '
                'Black crosses mark the minimum calculated FPR.')
            unsupported=cells[~cells.Status.isin(['Calculated','Zero depth: no crack resistance calculated'])]
            if not unsupported.empty:
                st.warning(f'{len(unsupported)} cells could not be evaluated by CorLAS and are excluded from the minimum. '
                    'Through-wall depths are not assigned a burst resistance. Review the point results before interpreting the minimum.')
            st.plotly_chart(corlas_depth_pressure_figure(cells,selected),width='stretch',key='det_corlas_'+signature+'_'+selected)
            st.download_button('Download pointwise CorLAS results',
                cells.assign(profile_id=selected,wall_thickness_mm=row['Wall thickness (mm)'],
                    outside_diameter_mm=row['Outside diameter (mm)']).to_csv(index=False),
                f'{selected}_corlas_pressure_map.csv','text/csv')
            with st.expander('Pointwise depth, burst pressure and FPR values'):
                st.dataframe(cells,hide_index=True,width='stretch')
        except (ValueError,TypeError) as error:
            st.error(str(error))
    try:
        st.plotly_chart(measured_profile_on_pipe_figure(profiles[selected],row['Wall thickness (mm)'],
            row['Outside diameter (mm)'],selected,defect_type),width='stretch',key='det_pipe_'+signature+'_'+selected)
        st.caption('The pipe view uses the same measured-profile renderer as Data Exploration. '
                   'Surface depression is visually enlarged; colours and tooltips retain the measured depth.')
        with st.expander('Linked measured 2D and 3D profile'):
            render_linked_measured_profile(profiles[selected],row['Wall thickness (mm)'],selected)
    except ValueError as error:
        st.error(str(error))
