"""Standalone fixed-section reliability, consequence and risk profiles."""
import hashlib
import html
import io
import json
import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Draw
from streamlit_folium import st_folium
from education.pof_model import POFInputs, UncertaintyInputs
from platform_ui import render_project_hero
from profile_map import route_length_km, point_at_chainage, latest_route_from_drawings
from profile_data import parse_profile_workbook
from reliability_model import (demo_data, calculate_crack_reliability,
                               import_feature_reliability, consequence_template, fixed_section_risk)
from consequence_assessment import render_consequence_assessment


def result_map(route, features, sections, column, label, pof_limit=None):
    m = folium.Map(location=route[0],tiles='OpenStreetMap')
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri World Imagery',name='Satellite').add_to(m)
    vertices = [route_length_km(route[:i+1]) for i in range(1,len(route))]
    maximum = float(sections[column].max())
    scale = LinearColormap(['#16a34a','#eab308','#dc2626'],vmin=0,
                          vmax=pof_limit if pof_limit is not None else maximum if maximum>0 else 1,
                          caption=label+(' — selected Pf limit' if pof_limit is not None else ' — relative colour scale'))
    scale.add_to(m)
    for row in sections.itertuples():
        start,end = row.start_km,row.end_km
        points = [start]+[d for d in vertices if start<d<end]+[end]
        value = float(getattr(row,column))
        folium.PolyLine([point_at_chainage(route,float(d)) for d in points],weight=7,
            color=scale(value),tooltip=f'Section {row.section_id}: {start:.3f}–{end:.3f} km; {label}: {value:.4g}',
            popup=f'Section {row.section_id}<br>{start:.3f}–{end:.3f} km<br>'
                  f'Burst Pf: {row.burst_pf:.4g}<br>Leakage Pf: {row.leak_pf:.4g}<br>'
                  f'Burst consequence: {row.burst_consequence:,.2f}<br>Leakage consequence: {row.leak_consequence:,.2f}<br>'
                  f'Total expected consequence: {row.total_risk:,.4g}').add_to(m)
    for row in features.itertuples():
        section = sections.iloc[int(row.section_id)-1]
        folium.CircleMarker(point_at_chainage(route,row.chainage_km),radius=6,
            color=scale(float(section[column])),fill=True,fill_opacity=.9,
            tooltip=f'{html.escape(str(row.feature_id))}: {row.defect_type}',
            popup=f'{html.escape(str(row.feature_id))}<br>Joint {row.joint_number}<br>'
                  f'Feature burst Pf: {row.burst_pf:.3g}<br>Feature leakage Pf: {row.leak_pf:.3g}<br>'
                  f'Section {row.section_id}: {section.start_km:.3f}–{section.end_km:.3f} km<br>'
                  f'{label}: {float(section[column]):.4g}').add_to(m)
    folium.LayerControl().add_to(m)
    m.fit_bounds(route)
    return m


def profile_figure(sections, columns, title, y_label):
    figure = go.Figure()
    x = sections.start_km.tolist()+[float(sections.end_km.iloc[-1])]
    for column,label in columns:
        y = sections[column].tolist()+[float(sections[column].iloc[-1])]
        figure.add_trace(go.Scatter(x=x,y=y,name=label,mode='lines',line_shape='hv',
            hovertemplate='%{x:.3f} km<br>%{y:.5g}<extra>'+label+'</extra>'))
    figure.update_layout(title=title,xaxis_title='Distance from route start (km)',
        yaxis_title=y_label,template='plotly_white',height=320,hovermode='x unified',
        margin=dict(l=50,r=20,t=50,b=45),legend=dict(orientation='h'))
    return figure


render_project_hero('Maintenance Planning (Cracks/Corrosion)','Reliability Analysis',
    'Map probability of failure, consequences and risk in fixed 1 km sections—without inspection or maintenance planning.')
st.caption('Crack calculation: CorLAS screening at the entered assessment condition. '
           'Corrosion: upload probabilities from your selected corrosion model. '
           'No growth, crack initiation, inspections, repairs or cost optimization are applied.')
demo_route,demo_features = demo_data()
if 'reliability_route' not in st.session_state:
    st.session_state.reliability_route = demo_route
if 'reliability_revision' not in st.session_state:
    st.session_state.reliability_revision = 0

st.subheader('Pipeline route')
if st.button('Load 100 km Alberta sample route'):
    st.session_state.reliability_route = demo_route
    st.session_state.reliability_revision += 1
    st.rerun()
st.caption('Fictional route west of Edmonton. Draw a line with bends, upload GeoJSON, or use a route from Data Exploration.')
if st.session_state.get('prepared_profile_route') and st.button('Use route from Data Exploration'):
    st.session_state.reliability_route = st.session_state.prepared_profile_route
    st.session_state.reliability_revision += 1
    st.rerun()
upload = st.file_uploader('Route GeoJSON (LineString or LineString Feature)',type=['geojson','json'])
if upload and st.button('Apply route upload'):
    try:
        doc = json.loads(upload.getvalue())
        geometry = doc.get('geometry',doc)
        if geometry['type'] != 'LineString':
            raise ValueError('Provide a LineString.')
        route = [[float(lat),float(lon)] for lon,lat in geometry['coordinates']]
        if route_length_km(route)<=0:
            raise ValueError('Route must have positive length.')
        st.session_state.reliability_route = route
        st.session_state.reliability_revision += 1
        st.rerun()
    except (ValueError,KeyError,TypeError) as error:
        st.error(str(error))
route = st.session_state.reliability_route
m = folium.Map(location=route[0],tiles='OpenStreetMap')
folium.PolyLine(route,color='#2563a8',weight=5).add_to(m)
Draw(draw_options={'polyline':True,'polygon':False,'rectangle':False,'circle':False,
                   'circlemarker':False,'marker':False},edit_options={'edit':False,'remove':False}).add_to(m)
m.fit_bounds(route)
drawn = st_folium(m,height=300,width=1100,key=f'reliability_input_{st.session_state.reliability_revision}',returned_objects=['all_drawings'])
new_route = latest_route_from_drawings((drawn or {}).get('all_drawings'))
if new_route and new_route != route:
    st.session_state.reliability_route = new_route
    st.session_state.reliability_revision += 1
    st.rerun()
st.write(f'Route length: **{route_length_km(route):.3f} km**')
workspace = st.radio('Reliability workspace',['Reliability and Risk','Consequence Assessment'],horizontal=True)
if workspace=='Consequence Assessment':
    render_consequence_assessment(route)
    st.stop()

st.subheader('Defects and analysis inputs')
mode = st.radio('Analysis method',['Calculate crack Pf','Import crack/corrosion Pf'],horizontal=True)
st.download_button('Download sample defect CSV',demo_features.to_csv(index=False),'reliability_sample_cracks.csv','text/csv')
st.download_button('Download sample route',json.dumps({'type':'LineString','coordinates':[[lon,lat] for lat,lon in demo_route]}),
                   'reliability_sample_route.geojson','application/geo+json')
st.caption('Chainage is distance in km from the first route point. Multiple defects in one nominal joint remain in that joint.')
sources = ['Sample defects','Upload CSV']
if st.session_state.get('prepared_profile_workbook'):
    sources.append('Profiles from Data Exploration')
source = st.selectbox('Defect source',sources)
features = demo_features.copy()
if mode == 'Import crack/corrosion Pf':
    features['burst_pf'],features['leak_pf'] = float('nan'),float('nan')
    st.download_button('Download Pf import template',features.to_csv(index=False),
                       'reliability_pf_template.csv','text/csv')
    st.warning('Fill the blank Pf columns with assessed values. Missing probabilities cannot be analyzed. '
               'Imported features are assumed independent, including within a joint.')
    basis = st.selectbox('Imported probability basis',['UNKNOWN — specify before running','Annual Pf','Pf at a specified condition / over a stated period'])
    period = st.text_input('Condition or period description',placeholder='For example: annual probability in assessment year 2027')
else:
    basis,period = 'Assessment-condition Pf','Entered geometry and load; no time evolution'
    st.info('Calculated Pf is for the entered condition, not an annual failure probability. '
            'The colour thresholds are screening settings; this is not a CSA compliance assessment.')
if source == 'Upload CSV':
    uploaded = st.file_uploader('Defect CSV',type='csv')
    if not uploaded:
        st.stop()
    try:
        features = pd.read_csv(io.BytesIO(uploaded.getvalue()))
    except (ValueError,pd.errors.ParserError) as error:
        st.error(str(error)); st.stop()
elif source == 'Profiles from Data Exploration':
    summary,_ = parse_profile_workbook(st.session_state.prepared_profile_workbook)
    features = summary.rename(columns={'Profile ID':'feature_id','Defect type':'defect_type',
        'Maximum depth (mm)':'depth_mm','Profile length (mm)':'length_mm'}).copy()
    features['chainage_km'] = pd.to_numeric(summary['Feature location (m)'])/1000
    features = features[['feature_id','defect_type','chainage_km','depth_mm','length_mm']]
    st.caption('Review distances relative to this route start. Shared pipe geometry below is used; set it to match your profiles.')
if mode == 'Import crack/corrosion Pf':
    for column in ('burst_pf','leak_pf'):
        if column not in features:
            features[column] = float('nan')
features = st.data_editor(features,num_rows='dynamic',hide_index=True,width='stretch',key=f'reliability_features_{source}_{mode}')
joint_length = st.number_input('Nominal joint length (m)',1.,100.,12.,1.)
c1,c2 = st.columns(2)
burst_limit = c1.number_input('High likelihood: burst Pf above',min_value=1e-10,max_value=1.,value=.001,format='%.6g')
leak_limit = c2.number_input('High likelihood: leakage Pf above',min_value=1e-10,max_value=1.,value=.01,format='%.6g')
st.subheader('Consequences for each kilometre')
st.caption('Section 1 = 0–1 km, section 2 = 1–2 km, and so on. The final section may be shorter. '
           'Enter the conditional loss if a burst or leakage event occurs in each section, not an already probability-weighted loss. '
           'Use one common unit for both modes, such as CAD; environmental or life-safety effects require your own consistent valuation.')
modeled = st.session_state.get('modeled_consequences')
consequence_options = ['Illustrative sample','Upload CSV or Excel','Enter section values']
if modeled and modeled['route']==route:
    consequence_options.append('Use Consequence Assessment')
consequence_source = st.radio('Consequence data',consequence_options,horizontal=True)
if consequence_source=='Use Consequence Assessment':
    unit = modeled['unit']
    st.write('Consequence unit: **'+unit+'**')
    st.caption('Using '+modeled['measure']+' from Consequence Assessment. Reassess the scenario there if assumptions change.')
else:
    unit = st.text_input('Common consequence unit',value='CAD')
template = consequence_template(route)
st.download_button('Download consequence template CSV',template.to_csv(index=False),'section_consequences_template.csv','text/csv')
consequences = consequence_template(route,sample=consequence_source=='Illustrative sample')
if consequence_source=='Illustrative sample':
    st.caption('Sample costs are invented to demonstrate spatial variation. They are not estimates for these Alberta locations.')
elif consequence_source=='Use Consequence Assessment':
    consequences = modeled['table'].copy()
elif consequence_source=='Upload CSV or Excel':
    consequence_upload = st.file_uploader('Section consequences (section_id, burst_consequence, leak_consequence)',type=['csv','xlsx'])
    if consequence_upload is not None:
        try:
            consequences = (pd.read_csv(io.BytesIO(consequence_upload.getvalue())) if consequence_upload.name.lower().endswith('.csv')
                            else pd.read_excel(io.BytesIO(consequence_upload.getvalue())))
        except (ValueError,TypeError,OSError) as error:
            st.error(str(error))
if consequence_source=='Enter section values':
    consequences = st.data_editor(consequences,hide_index=True,width='stretch',
        disabled=['section_id','start_km','end_km'],key=f'section_consequences_{hashlib.sha256(repr(route).encode()).hexdigest()}')
else:
    with st.expander('Review consequence values'):
        st.dataframe(consequences,hide_index=True,width='stretch')
base,uncertainty,samples,seed = POFInputs(),UncertaintyInputs(),1000,7
if mode == 'Calculate crack Pf':
    with st.expander('Pipe, pressure, material and uncertainty',expanded=True):
        a,b,c = st.columns(3)
        diameter = a.number_input('Outside diameter (in)',1.,100.,20.)
        wall = b.number_input('Wall thickness (mm)',.1,100.,6.35)
        pressure = c.number_input('Operating pressure (psi)',1.,10000.,936.)
        yield_strength = a.number_input('Yield strength (psi)',1000.,200000.,57200.)
        ultimate = b.number_input('Ultimate strength (psi)',1000.,250000.,73920.)
        charpy = c.number_input('Charpy energy (model units)',1.,500.,85.)
        elastic = a.number_input('Elastic modulus (GPa)',1.,500.,210.)
        factor = b.number_input('Model factor mean',.01,10.,1.27)
        depth_sd = c.number_input('Depth SD (mm)',0.,20.,.74)
        length_sd = a.number_input('Length SD (mm)',0.,500.,15.6)
        wall_sd = b.number_input('Wall thickness SD (mm)',0.,20.,.6)
        pressure_sd = c.number_input('Pressure SD (psi)',0.,1000.,20.)
        factor_sd = a.number_input('Model factor SD',0.,5.,.21)
        samples = b.number_input('Samples per feature',100,10000,1000,100)
        seed = c.number_input('Random seed',0,1000000,7)
        base = POFInputs(diameter_in=diameter,wall_thickness_mm=wall,
            flaw_depth_mm=min(1.,wall/2),operating_pressure_psi=pressure,yield_strength_psi=yield_strength,
            ultimate_strength_psi=ultimate,charpy_energy=charpy,elastic_modulus_gpa=elastic,model_factor=factor)
        uncertainty = UncertaintyInputs(length_sd,depth_sd,wall_sd,pressure_sd,factor_sd)
        st.caption('Positive truncated normal distributions for depth, length, WT, pressure and model factor. '
                   'Other material properties are fixed. WT, pressure and model factor are shared within a joint. '
                   'Burst is assessed for non-through-wall samples; depth ≥ WT is leakage.')
signature = hashlib.sha256(repr((route,features.to_csv(index=False),mode,basis,period,joint_length,
                               burst_limit,leak_limit,base,uncertainty,samples,seed,
                               consequences.to_csv(index=False),unit,
                               modeled['source_signature'] if consequence_source=='Use Consequence Assessment' else consequence_source)).encode()).hexdigest()
if st.button('Run Reliability Analysis',type='primary'):
    try:
        if basis.startswith('UNKNOWN') or (mode == 'Import crack/corrosion Pf' and not period.strip()):
            raise ValueError('Specify the imported probability basis and assessment period/condition.')
        if not unit.strip():
            raise ValueError('Specify a common consequence unit.')
        # Reject incomplete consequence values before Monte Carlo.
        required = {'section_id','burst_consequence','leak_consequence'}
        if not required.issubset(consequences.columns) or consequences[list(required)].isna().any().any():
            raise ValueError('Fill both consequence values for every section. Missing values are UNKNOWN, not zero.')
        with st.spinner('Calculating failure probabilities and risk in fixed 1 km sections…'):
            if mode == 'Calculate crack Pf':
                assessed,joints = calculate_crack_reliability(features,route,joint_length,base,uncertainty,int(samples),int(seed))
            else:
                assessed,joints = import_feature_reliability(features,route,joint_length)
            sections = fixed_section_risk(route,assessed,consequences,burst_limit,leak_limit)
            st.session_state.reliability_output = (signature,assessed,joints,sections)
    except (ValueError,KeyError,TypeError) as error:
        st.error(str(error))
saved = st.session_state.get('reliability_output')
if saved and saved[0] != signature:
    st.info('Inputs changed. Run Reliability Analysis again to update the map.')
elif saved:
    _,assessed,joints,sections = saved
    risk_unit = unit+'/year' if basis=='Annual Pf' else unit+' per stated assessment'
    st.subheader('POF, consequence and risk profiles')
    st.caption(f'Probability basis: {basis}. {period}. '
               'Risk = burst Pf × burst consequence + leakage Pf × leakage consequence, in '+risk_unit+'. '
               'Mode consequences must be additive without double-counting shared losses. '
               'Fixed sections do not overlap; each feature belongs to one section by its location. '
               'Unlisted defects are not modeled. Zero Monte Carlo failures do not prove zero Pf.')
    st.plotly_chart(profile_figure(sections,[('burst_pf','Burst'),('leak_pf','Leakage')],
        'POF versus distance','Probability of failure'),width='stretch')
    st.plotly_chart(profile_figure(sections,[('burst_consequence','Burst'),('leak_consequence','Leakage')],
        'Consequence versus distance','Conditional consequence ('+unit+')'),width='stretch')
    st.plotly_chart(profile_figure(sections,[('burst_risk','Burst'),('leak_risk','Leakage'),('total_risk','Total')],
        'Risk versus distance','Expected consequence ('+risk_unit+')'),width='stretch')
    view = st.radio('Map view',['POF','Consequence','Risk'],horizontal=True)
    mode_options = ['Burst','Leakage','Total'] if view=='Risk' else ['Burst','Leakage']
    map_mode = st.selectbox('Map failure mode',mode_options,index=2 if view=='Risk' else 0)
    prefix = {'Burst':'burst','Leakage':'leak','Total':'total'}[map_mode]
    suffix = {'POF':'pf','Consequence':'consequence','Risk':'risk'}[view]
    column = prefix+'_'+suffix
    label = map_mode+' '+view+(' ('+unit+')' if view=='Consequence' else ' ('+risk_unit+')' if view=='Risk' else '')
    st.caption('POF colours run from zero (green) to the selected Pf limit (red); values above it remain red. '
               'Consequence and risk use a relative green–yellow–red scale, not regulatory risk categories. '
               'Click a section or a defect for details. The table retains POF-limit categories separately.')
    selected_limit = (burst_limit if map_mode=='Burst' else leak_limit) if view=='POF' else None
    st_folium(result_map(route,assessed,sections,column,label,selected_limit),height=500,width=1100,returned_objects=[],key=f'reliability_output_{signature}_{column}')
    st.markdown('**Each crack/corrosion feature**')
    st.dataframe(assessed,hide_index=True,width='stretch')
    st.markdown('**Fixed 1 km sections — highest expected consequence first**')
    st.dataframe(sections.sort_values('total_risk',ascending=False),hide_index=True,width='stretch')
    for label,table,name in [('Feature results',assessed,'feature_reliability.csv'),
                             ('Joint results',joints,'joint_reliability.csv'),
                             ('Section risk results',sections,'fixed_1km_risk.csv')]:
        consequence_basis = (modeled['measure']+'; scenario '+modeled['source_signature']
                             if consequence_source=='Use Consequence Assessment' else consequence_source)
        export = table.assign(probability_basis=basis,assessment_period=period,consequence_unit=unit,
                              risk_unit=risk_unit,consequence_source=consequence_basis)
        st.download_button(f'Download {label}',export.to_csv(index=False),name,'text/csv')
