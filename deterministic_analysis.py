"""Deterministic FPR workflow with selectable measured defect visualizations."""
import hashlib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from education.pof_model import POFInputs
from deterministic_model import analyze_deterministic_profiles
from profile_data import (ProfileFormatError,parse_profile_workbook,summary_for_defect_type,
                          synthetic_sample_workbook,summary_xlsx)
from profile_visuals import render_linked_measured_profile,measured_profile_on_pipe_figure


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
    prepared = st.session_state.get('prepared_profile_workbook')
    options = ['Sample crack profiles','Upload a profile workbook']
    if prepared is not None:
        options.insert(0,'Profiles from Data Exploration')
    source = st.radio('Deterministic data source',options,horizontal=True,key='det_source')
    content = None
    if source=='Sample crack profiles':
        content = synthetic_sample_workbook()
        st.caption('Sample crack-profile data.')
    elif source=='Profiles from Data Exploration':
        content = prepared
    else:
        upload = st.file_uploader('Crack/corrosion profile workbook',type=['xlsx','xlsm'],key='det_workbook')
        if upload is not None:
            content = upload.getvalue()
    if content is None:
        st.info('Upload a measured profile workbook to calculate FPR and inspect the 3D profiles.')
        return
    prepared_type = st.session_state.get('prepared_profile_defect_type','Crack')
    defect_type = st.selectbox('Deterministic profile type',['Crack','Corrosion / metal loss'],
        index=1 if source=='Profiles from Data Exploration' and prepared_type!='Crack' else 0,key='det_type')
    try:
        summary,profiles = parse_profile_workbook(content)
        summary = summary_for_defect_type(summary,defect_type)
    except (ProfileFormatError,ValueError) as error:
        st.error(str(error))
        return
    st.caption('Crack resistance uses the existing CorLAS model. Corrosion can be visualized, '
               'but FPR is marked unavailable until a corrosion-specific resistance model is selected.')
    with st.form('deterministic_parameters'):
        a,b,c = st.columns(3)
        yield_strength = a.number_input('Deterministic yield strength (psi)',1000.,200000.,57200.)
        ultimate = b.number_input('Deterministic ultimate strength (psi)',1001.,250000.,73920.)
        pressure = c.number_input('Deterministic operating pressure (psi)',1.,10000.,936.)
        elastic = a.number_input('Deterministic elastic modulus (GPa)',1.,500.,210.)
        charpy = b.number_input('Deterministic Charpy energy (model units)',1.,500.,85.)
        origin = c.number_input('Route start chainage (m)',value=0.,step=100.)
        run = st.form_submit_button('Run Deterministic Analysis',type='primary')
    base = POFInputs(yield_strength_psi=yield_strength,ultimate_strength_psi=ultimate,
        operating_pressure_psi=pressure,elastic_modulus_gpa=elastic,charpy_energy=charpy)
    signature = hashlib.sha256(content+repr((defect_type,base,origin)).encode()).hexdigest()
    if run:
        try:
            if ultimate<=yield_strength:
                raise ValueError('Ultimate strength must exceed yield strength.')
            result = analyze_deterministic_profiles(summary,base)
            distances = pd.to_numeric(result['Feature location (m)'],errors='coerce')-origin
            if distances.isna().any() or (distances<0).any():
                raise ValueError('Feature locations must be valid and not before the selected route start.')
            result['Distance from start (km)'] = distances/1000
            result['Section ID'] = (distances//1000).astype(int)+1
            st.session_state.deterministic_output = (signature,result)
        except (ValueError,KeyError,TypeError) as error:
            st.error(str(error))
    saved = st.session_state.get('deterministic_output')
    if saved and saved[0]!=signature:
        st.info('Inputs changed. Run Deterministic Analysis again to update the FPR results.')
    result = saved[1] if saved and saved[0]==signature else None
    if result is not None:
        st.markdown('**FPR for each defect**')
        st.caption('FPR = unadjusted burst resistance pressure / operating pressure. '
                   'Click a row or a point below to open that measured defect in 3D. '
                   'An FPR above 1 alone does not establish code compliance or asset safety.')
        table_key = 'det_result_table_'+signature
        st.dataframe(result,hide_index=True,width='stretch',key=table_key,
            on_select=lambda:_select_table(table_key,result['Profile ID'].astype(str).tolist()),
            selection_mode='single-row',column_config={'FPR':st.column_config.NumberColumn(format='%.3f')})
        calculated = result[result.Status=='Calculated'].copy()
        if not calculated.empty:
            figure = go.Figure(go.Scatter(x=calculated['Distance from start (km)'],y=calculated.FPR,
                customdata=calculated[['Profile ID']].astype(str).to_numpy(),mode='markers',
                marker=dict(size=10,color=calculated.FPR,colorscale='RdYlGn',showscale=True),
                hovertemplate='Profile %{customdata[0]}<br>%{x:.3f} km<br>FPR %{y:.3f}<extra></extra>'))
            figure.add_hline(y=1,line_dash='dash',annotation_text='FPR = 1')
            figure.update_layout(template='plotly_white',xaxis_title='Distance from route start (km)',
                yaxis_title='FPR',height=330,clickmode='event+select')
            chart_key = 'det_result_chart_'+signature
            st.plotly_chart(figure,width='stretch',key=chart_key,on_select=lambda:_select_chart(chart_key),selection_mode='points')
            sections = result.groupby('Section ID',as_index=False).agg(
                **{'Lowest calculated FPR':('FPR','min'),'Recorded defects':('Profile ID','size'),
                   'Calculated defects':('FPR','count')})
            sections['Section start (km)'] = sections['Section ID']-1
            sections['Section end (km)'] = sections['Section ID']
            st.markdown('**Lowest calculated defect FPR in each represented 1 km section**')
            st.caption('This is the minimum defect FPR, not a segment reliability calculation. '
                       'Sections with unrecorded defects are not assessed; unavailable FPR values are excluded from the minimum.')
            st.dataframe(sections,hide_index=True,width='stretch')
            st.download_button('Download section FPR summary',sections.to_csv(index=False),'section_fpr.csv','text/csv')
        st.download_button('Download deterministic results CSV',result.to_csv(index=False),'deterministic_fpr.csv','text/csv')
        st.download_button('Download deterministic results Excel',summary_xlsx(result),'deterministic_fpr.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        st.info('Set the material and pressure inputs, then run the deterministic calculation.')
    # Keep measured geometry available even when resistance is unsupported/invalid.
    ids = summary['Profile ID'].astype(str).tolist()
    if st.session_state.get('det_selected_profile') not in ids:
        st.session_state.det_selected_profile = ids[0]
    selected = st.selectbox('Selected defect — 2D/3D view',ids,key='det_selected_profile')
    row = summary.loc[summary['Profile ID'].astype(str)==selected].iloc[0]
    st.markdown('**Selected defect on the pipe**')
    if result is not None:
        chosen = result.loc[result['Profile ID'].astype(str)==selected].iloc[0]
        st.write(f'Profile {selected} · {defect_type} · '+
            (f'FPR {chosen.FPR:.3f}' if pd.notna(chosen.FPR) else str(chosen.Status)))
    try:
        st.plotly_chart(measured_profile_on_pipe_figure(profiles[selected],row['Wall thickness (mm)'],
            row['Outside diameter (mm)'],selected,defect_type),width='stretch',key='det_pipe_'+signature+'_'+selected)
        st.caption('The pipe view uses the same measured-profile renderer as Data Exploration. '
                   'Surface depression is visually enlarged; colours and tooltips retain the measured depth.')
        with st.expander('Linked measured 2D and 3D profile'):
            render_linked_measured_profile(profiles[selected],row['Wall thickness (mm)'],selected)
    except ValueError as error:
        st.error(str(error))
