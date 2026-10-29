"""Standalone reliability page: feature Pf and sliding-section map."""
import hashlib
import html
import io
import json
import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium
from education.pof_model import POFInputs, UncertaintyInputs
from platform_ui import render_project_hero
from profile_map import route_length_km, point_at_chainage, latest_route_from_drawings
from profile_data import parse_profile_workbook
from reliability_model import (demo_data, calculate_crack_reliability,
                               import_feature_reliability, sliding_sections)


def result_map(route, features, spatial):
    colors = {'High':'#dc2626','Medium':'#eab308','Low':'#16a34a'}
    m = folium.Map(location=route[0],tiles='OpenStreetMap')
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri World Imagery',name='Satellite').add_to(m)
    vertices = [route_length_km(route[:i+1]) for i in range(1,len(route))]
    for _,group in spatial.groupby((spatial.category != spatial.category.shift()).cumsum()):
        start,end = group.start_km.iloc[0],group.end_km.iloc[-1]
        points = [start]+[d for d in vertices if start<d<end]+[end]
        category = group.category.iloc[0]
        folium.PolyLine([point_at_chainage(route,float(d)) for d in points],weight=7,
            color=colors[category],tooltip=f'{category}: {start:.3f}–{end:.3f} km (worst enclosing window)').add_to(m)
    for row in features.itertuples():
        joint = spatial.iloc[int(row.joint_number)-1]
        folium.CircleMarker(point_at_chainage(route,row.chainage_km),radius=6,
            color=colors[joint.category],fill=True,fill_opacity=.9,
            tooltip=f'{html.escape(str(row.feature_id))}: {row.defect_type}',
            popup=f'{html.escape(str(row.feature_id))}<br>Joint {row.joint_number}<br>'
                  f'Feature burst Pf: {row.burst_pf:.3g}<br>Feature leakage Pf: {row.leak_pf:.3g}<br>'
                  f'Critical window: {joint.critical_start_km:.3f}–{joint.critical_end_km:.3f} km<br>'
                  f'Window burst Pf: {joint.window_burst_pf:.3g}<br>Window leakage Pf: {joint.window_leak_pf:.3g}').add_to(m)
    folium.LayerControl().add_to(m)
    m.fit_bounds(route)
    return m


render_project_hero('Maintenance Planning (Cracks/Corrosion)','Reliability Analysis',
    'Calculate feature failure probabilities and locate critical sliding 1 km sections—without inspection or maintenance planning.')
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
                               burst_limit,leak_limit,base,uncertainty,samples,seed)).encode()).hexdigest()
if st.button('Run Reliability Analysis',type='primary'):
    try:
        if basis.startswith('UNKNOWN') or (mode == 'Import crack/corrosion Pf' and not period.strip()):
            raise ValueError('Specify the imported probability basis and assessment period/condition.')
        with st.spinner('Calculating feature probabilities and sliding 1 km sections…'):
            if mode == 'Calculate crack Pf':
                assessed,joints = calculate_crack_reliability(features,route,joint_length,base,uncertainty,int(samples),int(seed))
            else:
                assessed,joints = import_feature_reliability(features,route,joint_length)
            windows,spatial = sliding_sections(route,assessed,joints,joint_length,burst_limit,leak_limit)
            st.session_state.reliability_output = (signature,assessed,joints,windows,spatial)
    except (ValueError,KeyError,TypeError) as error:
        st.error(str(error))
saved = st.session_state.get('reliability_output')
if saved and saved[0] != signature:
    st.info('Inputs changed. Run Reliability Analysis again to update the map.')
elif saved:
    _,assessed,joints,windows,spatial = saved
    st.subheader('Reliability map and critical sections')
    st.caption(f'Probability basis: {basis}. {period}. Red: above either limit; yellow: 50–100%; green: below 50%. '
               'Colours show the worst enclosing 1 km window. Windows advance one joint; boundary joints are included in full conservatively. '
               'Short routes use their actual length. These are failure-likelihood categories, without consequences. '
               'Unlisted defects and failure mechanisms are not modeled. Zero observed Monte Carlo failures do not prove zero Pf.')
    st_folium(result_map(route,assessed,spatial),height=500,width=1100,returned_objects=[],key=f'reliability_output_{signature}')
    st.markdown('**Each crack/corrosion feature**')
    st.dataframe(assessed,hide_index=True,width='stretch')
    st.markdown('**Critical sliding 1 km sections**')
    st.dataframe(windows.sort_values('limit_ratio',ascending=False),hide_index=True,width='stretch')
    for label,table,name in [('Feature results',assessed,'feature_reliability.csv'),
                             ('Joint results',joints,'joint_reliability.csv'),
                             ('Sliding sections',windows,'sliding_1km_reliability.csv')]:
        export = table.assign(probability_basis=basis,assessment_period=period)
        st.download_button(f'Download {label}',export.to_csv(index=False),name,'text/csv')
