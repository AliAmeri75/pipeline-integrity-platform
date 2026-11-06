"""Pressure-history upload and dent fatigue, separate from geometric strain screening."""
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from academic_figures import academic_style
from dent_assessment_model import dent_geometry
from dent_fatigue_model import read_scada,pressure_history,count_cycles,automatic_scf,fatigue_curve,A_MEAN

SAMPLE=Path(__file__).parent/'samples'/'ALIRIM_Synthetic_SCADA_7_Days.csv'


def render_dent_fatigue(project):
    st.subheader('SCADA Pressure Cycles & Dent Fatigue')
    st.caption('Research model: rainflow counting → API 1156 S–N curve → Miner damage → He–Zhou lognormal fatigue reliability. '
               'This is not the withdrawn API RP 1183 Table 6 method. Fatigue-limit-state probability is not burst or leakage POF.')
    st.markdown('[He & Zhou (2021), equations 10, 15–23](https://doi.org/10.1016/j.jpse.2021.08.004)')
    source=st.radio('Pressure history source',['Synthetic SCADA sample','Upload SCADA CSV / Excel'],key='fatigue_source')
    sample=SAMPLE.read_bytes()
    st.download_button('Download synthetic SCADA sample',sample,SAMPLE.name,'text/csv',key='fatigue_sample_download')
    if source=='Synthetic SCADA sample':
        content=sample;name=SAMPLE.name
        st.info('Fictional liquid-pipeline data: 7 days at 1-minute intervals, including a shutdown/restart. '
                'These pressures are not measured on the saved route and do not validate service life.')
    else:
        file=st.file_uploader('SCADA pressure history',type=['csv','xlsx'],key='fatigue_upload')
        st.caption('One row per observation. Include a timestamp and numeric pressure. Units are selected below. '
                   'Excel: first worksheet. Remove invalid/quality-flagged observations upstream without bridging gaps.')
        if file is None:return
        content=file.getvalue();name=file.name
    try:data=read_scada(content,name)
    except ValueError as error:st.error(str(error));return
    if 'pipeline_id' in data:
        ids=data.pipeline_id.dropna().unique().tolist()
        if not ids:st.error('pipeline_id is entirely missing.');return
        pid=st.selectbox('SCADA pipeline ID',ids,key='fatigue_pipeline')
        data=data.loc[data.pipeline_id==pid].copy()
    columns=list(data.columns)
    time=st.selectbox('Timestamp column',columns,index=columns.index('timestamp_utc') if 'timestamp_utc' in columns else 0,key='fatigue_time')
    preferred='upstream_pressure_MPa_gauge'
    pressure=st.selectbox('Pressure column at the assessed dent',columns,index=columns.index(preferred) if preferred in columns else min(1,len(columns)-1),key='fatigue_pressure')
    unit=st.selectbox('Pressure unit',['MPa','bar','psi'],key='fatigue_unit')
    st.caption('Use internal-minus-external pressure at the dent. No route interpolation is assumed. '
               'Timestamps with offsets are converted to UTC; timestamps without offsets are assumed UTC. '
               'Rows must be complete, unique, chronological and regularly sampled. Observation duration includes one sample interval.')
    try:
        history,exposure,cadence=pressure_history(data,time,pressure,unit)
        minimum=st.number_input('Ignore cycles below pressure range (MPa)',0.,10.,0.,.001,key='fatigue_min_range')
        cycles=count_cycles(history.pressure_MPa,minimum)
    except (ValueError,KeyError,TypeError) as error:st.error(str(error));return
    st.write(f'{len(history):,} readings · {exposure*365.25:.3f} days · {cadence:g}-second sampling · {cycles["count"].sum():g} equivalent cycles retained')
    st.plotly_chart(academic_style(px.line(history,x='timestamp_utc',y='pressure_MPa',labels={'timestamp_utc':'Time (UTC)','pressure_MPa':'Pressure (MPa)'},title='Selected pressure history')),width='stretch',theme=None)
    if cycles.empty:st.info('No nonzero pressure cycles remain. No cyclic damage is accumulated by this model.')
    else:
        edges=np.linspace(0,cycles.range_MPa.max()*1.000001,21)
        histogram=cycles.groupby(pd.cut(cycles.range_MPa,edges,include_lowest=True),observed=False)['count'].sum()
        bars=pd.DataFrame({'Pressure-range bin (MPa)':histogram.index.astype(str),'Equivalent cycles':histogram.to_numpy()})
        st.plotly_chart(academic_style(px.bar(bars,x=bars.columns[0],y=bars.columns[1],title='Rainflow pressure-range spectrum')),width='stretch',theme=None)
    st.download_button('Download counted pressure cycles',cycles.to_csv(index=False),'scada_rainflow_cycles.csv','text/csv',key='fatigue_cycles_download')
    with st.expander('Counted cycles and uploaded records'):
        st.dataframe(cycles,hide_index=True);st.dataframe(data.head(100),hide_index=True)
        st.caption('Half cycles at the record boundaries are retained. Damage uses individual ranges, not the displayed histogram bins. No denoising is automatic; the range cutoff affects damage.')
    try:dents=dent_geometry(project)
    except ValueError as error:st.error(str(error));return
    if dents.empty:st.info('Save dents in Data Exploration to use their geometry here.');return
    dent_id=st.selectbox('Dent to assess',dents.dent_id,key='fatigue_dent')
    row=dents.loc[dents.dent_id==dent_id].iloc[0]
    st.write(f'Saved pipe: OD {row.diameter_mm:.2f} mm · WT {row.wall_thickness_mm:.2f} mm · dent depth {row.dent_depth_mm:.2f} mm · D/t {row.diameter_mm/row.wall_thickness_mm:.2f}')
    if row.associated_crack_or_metal_loss:
        st.error('Dent–crack/metal-loss interaction is unsupported by this plain-dent fatigue model.');return
    method=st.radio('Dent stress-concentration factor (SCF)',['Pinheiro (2019) equation','Reviewed user-supplied SCF'],key='fatigue_scf_method')
    scf=None
    if method=='Pinheiro (2019) equation':
        try:
            scf=automatic_scf(row.diameter_mm,row.wall_thickness_mm,row.dent_depth_mm)
            st.metric('Calculated SCF',f'{scf:.3f}')
        except ValueError as error:st.warning(str(error))
    else:
        scf=st.number_input('Reviewed SCF (dimensionless)',1.,100.,6.,.1,key='fatigue_scf')
        provenance=st.text_input('SCF source / justification',key='fatigue_scf_source')
        st.caption('The starting value 6 is illustrative, not calibrated to this dent. Supply an applicable '
                   'engineering assessment or validated model. An entered factor is not automatically validated.')
        if not provenance.strip():scf=None
    years=st.number_input('Future assessment horizon (years)',1,100,10,key='fatigue_years')
    age=st.number_input('Years of prior exposure to this same pressure spectrum',0.,100.,0.,.5,key='fatigue_age')
    st.caption('Zero prior exposure means a new-dent / zero-accrued-fatigue scenario. Existing dents need a justified '
               'loading history. This control assumes the selected spectrum also represents all prior years; no damage is inferred from dent depth.')
    a_cov=st.number_input('S–N coefficient A COV',0.,2.,.45,.01,key='fatigue_a_cov')
    dc_cov=st.number_input('Critical Miner damage COV',0.,2.,.30,.01,key='fatigue_dc_cov')
    st.caption(f'Literature example defaults: independent lognormal A (mean {A_MEAN:.4g}, MPa-based, exponent m=2.971) '
               'and critical damage (mean 1). Geometry, SCF and spectrum are fixed. These are not operator-calibrated distributions. '
               'SCF uncertainty, re-rounding, mean-stress correction and load-sequence effects are not modeled.')
    reviewed=st.checkbox('I confirm this is a plain, smooth, unrestrained dent away from interacting damage/welds, '
        'the selected pressure represents its location, and SCF, data quality and exposure assumptions have been reviewed.',key='fatigue_reviewed')
    repeat=st.checkbox('Use this record as a stationary repeating pressure spectrum for past/future years (an assumption, not measured future loading).',key='fatigue_stationary')
    # Gate behind the button on every rerun: changed data can never leave stale results visible.
    if st.button('Run Dent Fatigue & Reliability',disabled=not reviewed or not repeat or scf is None,key='fatigue_run'):
        try:
            total=np.arange(0,int(years)+1,dtype=float)+age
            result,rate=fatigue_curve(cycles,exposure,row.diameter_mm,row.wall_thickness_mm,scf,total,a_cov=a_cov,critical_cov=dc_cov)
            result['future_year']=np.arange(int(years)+1)
            # Unconditional probability of fatigue-limit crossing in each future interval.
            result['interval_fatigue_probability']=result.cumulative_fatigue_probability.diff()
            result.loc[0,'interval_fatigue_probability']=np.nan
            result['dent_id']=dent_id
            result['probability_basis']='Cumulative fatigue limit state since assumed dent initiation; not burst/leakage'
            result['pressure_source']=name;result['pressure_column']=pressure;result['scf']=scf
            result['scf_basis']=method;result['record_days']=exposure*365.25
            result['data_origin']='SYNTHETIC' if source=='Synthetic SCADA sample' else 'USER UPLOAD (not independently verified)'
            result['a_cov']=a_cov;result['critical_damage_cov']=dc_cov
            result['scf_reference']=provenance if method=='Reviewed user-supplied SCF' else 'He–Zhou Eq15; Pinheiro2019'
            st.metric('Cumulative fatigue probability at horizon',f'{result.cumulative_fatigue_probability.iloc[-1]:.3e}')
            st.metric('Projected annual Miner damage at mean A',f'{rate/A_MEAN:.3e}')
            st.plotly_chart(academic_style(px.line(result,x='future_year',y='cumulative_fatigue_probability',markers=True,
                labels={'future_year':'Years from assessment','cumulative_fatigue_probability':'Cumulative fatigue-limit probability'},title='Dent fatigue reliability over time')),width='stretch',theme=None)
            st.dataframe(result,hide_index=True,width='stretch')
            st.caption('Interval probabilities are differences between cumulative values, not probabilities conditional '
                       'on survival. This does not optimize an inspection schedule or model an inspection benefit. '
                       'No burst/leakage consequences are automatically attached to fatigue-limit crossing.')
            st.download_button('Download dent fatigue results',result.to_csv(index=False),'dent_fatigue_reliability.csv','text/csv',key='fatigue_results_download',on_click='ignore')
        except (ValueError,TypeError,OverflowError) as error:st.error(str(error))
