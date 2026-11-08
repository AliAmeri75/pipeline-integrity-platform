"""Isolated published benchmarks; never writes the user's shared project."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from platform_ui import render_project_hero
from academic_figures import academic_style
from marshall_validation_model import compare_marshall,load_marshall,PUBLISHED_CONSTANTS,TABLE_I_URL,TABLE_II_URL,REPORT_URL

render_project_hero('Research Resources','Validation Examples',
    'Compare ALIRIM calculations with published reference calculations and inspect the assumptions.')
preliminary, planning = st.tabs([
    'Preliminary Analysis Validation',
    'Planning Validation',
])
with preliminary:
    st.caption('Published benchmarks for deterministic resistance and preliminary analysis.')
    st.subheader('Marshall Burst Resistance')
    st.caption('Enbridge Line 6B · Marshall, Michigan')
    st.write('NTSB Attachment I, Table I: 16 fitness-for-service calculation scenarios prepared by Enbridge '
             'at NTSB’s request after the July 25, 2010 rupture.')
    st.info('This is a reproduction of published calculations, not a prediction of the accident. The rows are '
            'alternative crack/corrosion effective-depth scenarios, not 16 independent defects or failure tests. '
            'The example does not determine an inspection interval or demonstrate accident prevention.')
    st.markdown(f'[NTSB Table I — input scenarios and reference pressures]({TABLE_I_URL}) · '
                f'[Table II — historical inspection observations]({TABLE_II_URL}) · [Final report PAR-12/01]({REPORT_URL})')
    with st.expander('Published inputs and declared assumptions',expanded=True):
        constants=pd.DataFrame([
            ['Outside diameter','30 in','Table I'],
            ['Flaw length','51.6 in','Table I; use CorLAS length, not the different FlawCheck length'],
            ['UTS / flow stress','66,000 / 59,000 psi','Table I; explicit flow stress used for rectangular comparison'],
            ['Charpy energy','20 ft-lbf','Table I; legacy CorLAS J correlation uses this imperial convention'],
            ['Flaw shape / location','Rectangular / External','Table I'],
            ['MOP / 1.25 MOP','624 / 780 psi','Table I; comparison levels, not the actual rupture pressure'],
            ['Yield strength used','52,000 psi','X52 SMYS in final report p.1, footnote 4; using SMYS as model yield is an assumption'],
            ['Elastic modulus','30,000,000 psi','Analyst assumption; not specified in Table I'],
            ['Pressure bias / safety factors','1 / 1','Nominal predicted failure pressure; no 1.27 model multiplier or design safety reduction'],
        ],columns=['Parameter','Default value','Basis'])
        st.dataframe(constants,hide_index=True,width='stretch')
        st.caption('The production wrapper’s default uses elliptical area πLd/4. The NTSB comparison explicitly '
            'uses rectangular area Ld, while effective depth remains d. Existing default analyses retain their original geometry. '
            'This reproduces the source’s effective-depth approximation, not a general crack–corrosion interaction model.')
    with st.expander('Sensitivity controls — defaults are not fitted to the reference'):
        modulus=st.number_input('Assumed elastic modulus (psi)',20_000_000.,40_000_000.,30_000_000.,100_000.,key='marshall_modulus')
        yield_strength=st.number_input('Assumed model yield strength (psi)',10_000.,65_000.,52_000.,1000.,key='marshall_yield')
        tolerance=st.number_input('Selected comparison tolerance (%)',.01,20.,1.,.1,key='marshall_tolerance')
        st.caption('This tolerance is a user-selected numerical comparison rule, not an NTSB requirement or '
                   'field-validation criterion. Changing yield/modulus is a sensitivity study; published pressures stay fixed. '
                   'The rectangular flow stress remains the published 59,000 psi.')
    try:
        result=compare_marshall(modulus,yield_strength,tolerance)
    except (ValueError,TypeError) as error:
        st.error(str(error));st.stop()
    maximum=result.difference_percent.abs().max()
    cols=st.columns(3)
    cols[0].metric('Scenarios within selected tolerance',f'{result.comparison_status.eq("Within selected tolerance").sum()} / {len(result)}')
    cols[1].metric('Maximum absolute pressure difference',f'{result.difference_psi.abs().max():.3f} psi')
    cols[2].metric('Maximum absolute percentage difference',f'{maximum:.3f}%')
    st.caption(f'Selected numerical comparison tolerance: ±{tolerance:g}%. Agreement means the implemented equation reproduces these reference calculations under '
               'the listed assumptions. It does not independently establish accuracy for an operating pipeline.')
    show_ellipse=st.checkbox('Also show the existing elliptical-default comparison',key='marshall_show_ellipse')
    fig=go.Figure()
    fig.add_scatter(x=result.scenario_id,y=result.ntsb_failure_pressure_psi,mode='lines+markers',name='NTSB published')
    fig.add_scatter(x=result.scenario_id,y=result.alirim_rectangular_psi,mode='markers',name='ALIRIM · rectangular',marker=dict(symbol='x',size=11))
    if show_ellipse:
        fig.add_scatter(x=result.scenario_id,y=result.alirim_elliptical_psi,mode='lines+markers',name='ALIRIM · existing elliptical default',line=dict(dash='dot'))
    fig.add_hline(y=624,line_dash='dash',annotation_text='Published MOP = 624 psi',annotation_position='top left')
    fig.add_hline(y=780,line_dash='dot',annotation_text='Published 1.25 MOP = 780 psi',annotation_position='top left')
    fig.update_layout(title='Published and calculated failure pressures',xaxis_title='Published reconstruction scenario',
                      yaxis_title='Nominal predicted failure pressure (psi)',height=520)
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(academic_style(fig),width='stretch',theme=None)
    shown=['scenario_id','analysis_year','published_run_label','wall_thickness_in','effective_depth_in',
           'ntsb_failure_pressure_psi','alirim_rectangular_psi','difference_psi','difference_percent','comparison_status']
    if show_ellipse:shown+=['alirim_elliptical_psi','elliptical_difference_percent']
    labels={'scenario_id':'Scenario','analysis_year':'Source year','published_run_label':'Source run label',
        'wall_thickness_in':'WT (in)','effective_depth_in':'Effective depth (in)','ntsb_failure_pressure_psi':'NTSB (psi)',
        'alirim_rectangular_psi':'ALIRIM rectangular (psi)','difference_psi':'Difference (psi)',
        'difference_percent':'Difference (%)','comparison_status':'Numerical comparison',
        'alirim_elliptical_psi':'Existing elliptical (psi)','elliptical_difference_percent':'Elliptical difference (%)'}
    st.dataframe(result[shown].round(3).rename(columns=labels),hide_index=True,width='stretch')
    selected=st.selectbox('Inspect a scenario',result.scenario_id,key='marshall_selected')
    row=result.loc[result.scenario_id==selected].iloc[0]
    with st.expander('Selected-scenario calculation details',expanded=True):
        st.write(f'{selected}: controlling check = **{row.controlling_check}**. '
                 f'Flow-stress pressure = **{row.rectangular_flow_psi:.3f} psi**; '
                 f'fracture-toughness pressure = **{row.rectangular_toughness_psi:.3f} psi**.')
        st.write(f'ALIRIM FPR at the published MOP: **{row.alirim_fpr_at_mop:.4f}**; '
                 f'NTSB reference FPR: **{row.ntsb_fpr_at_mop:.4f}**.')
        if row.source_notes:st.warning(row.source_notes)
        st.caption('Difference = ALIRIM − NTSB. These are alternative source calculation scenarios; '
                   'do not interpret their sequence as crack growth over time.')
    with st.expander('Source transcription notes and scope'):
        st.write('Source row 8 has an inconsistent text description of the component depths. The numerical '
                 'effective-depth column (0.178 in) is retained. Several 2007 rows repeat run label 12; '
                 'unique scenario IDs preserve every row without changing the published labels.')
        st.write('The source table gives integer-psi reference pressures and rounded inputs. Small residual '
                 'differences cannot be assigned to rounding alone without the original full-precision inputs '
                 'and implementation. Neither elastic modulus nor measured yield strength is specified in Table I.')
        st.write('Historical ILI data in Table II are linked as context; they are not mixed into these '
                 'Table I calculations or used to infer growth rates. A future retrospective scheduling study '
                 'must separate information available before failure from post-accident reconstruction.')
    export=result.assign(elastic_modulus_psi=modulus,yield_strength_psi=yield_strength,
        diameter_in=30.,ultimate_strength_psi=66000.,rectangular_flow_stress_psi=59000.,charpy_ft_lbf=20.,
        mop_psi=624.,comparison_tolerance_percent=tolerance,model_factor=1.,safety_factor=1.,
        reference_source_url=TABLE_I_URL,comparison_basis='Post-accident Table I calculation reproduction; not accident prediction')
    st.download_button('Download complete comparison and assumptions',export.to_csv(index=False),
        'marshall_corlas_comparison.csv','text/csv',key='marshall_results_download')
    published=load_marshall().assign(**PUBLISHED_CONSTANTS,reference_source_url=TABLE_I_URL)
    st.download_button('Download transcribed published inputs',published.to_csv(index=False),
        'marshall_ntsb_published_inputs.csv','text/csv',key='marshall_source_download')

with planning:
    st.subheader('Planning Validation')
    st.info('Under construction — inspection and maintenance planning benchmarks will be added here.')
    st.write('This section will compare inspection intervals, repair decisions and lifecycle costs '
             'with published reference cases using matched inputs and assumptions.')
    st.caption('No planning-validation results are available yet. The Marshall burst-resistance '
               'comparison is in Preliminary Analysis Validation.')
