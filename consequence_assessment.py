"""Consequence workspace embedded in Reliability Analysis."""
import hashlib
import io
import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium
from map_presentation import readable_map_overlays
from profile_map import point_at_chainage,route_length_km
from reliability_model import consequence_template
from consequence_model import (HazardScenario,PIR,THERMAL,RADIUS,PIR_SOURCE,THERMAL_SOURCE,
                               assess_consequences,consequence_risk_inputs)


def hazard_controls(mode,natural_gas,shared_geometry=False):
    title = 'Burst / rupture' if mode=='burst' else 'Leakage'
    with st.expander(title+' scenario',expanded=True):
        options = [PIR,THERMAL,RADIUS] if mode=='burst' and natural_gas else [THERMAL,RADIUS]
        model = st.selectbox('Radius model',options,key=f'ca_{mode}_model')
        values = dict(model=model,natural_gas=natural_gas)
        if model==PIR:
            st.caption('r(m) = 0.3048 × 0.69 × nominal diameter(in) × √MAOP(psi). Natural gas only.')
            if shared_geometry:
                st.caption('MAOP and nominal pipe diameter come from each saved property segment in Data Exploration.')
            else:
                values['maop_psi'] = st.number_input('MAOP (psi)',1.,10000.,936.,key=f'ca_{mode}_maop')
                values['diameter_in'] = st.number_input('Nominal diameter (in)',.1,100.,20.,key=f'ca_{mode}_diameter')
        elif model==THERMAL:
            st.caption('r = √[χ × heat-release rate / (4π × heat-flux threshold)], with compatible kW and metre units. '
                       'Steady point-source approximation; supply the scenario heat-release rate. No leak-size, blowdown or dispersion solver is used.')
            values['heat_release_mw'] = st.number_input('Total fire heat-release rate (MW)',0.,100000.,
                100. if mode=='burst' else 10.,key=f'ca_{mode}_heat')
            values['radiant_fraction'] = st.number_input('Radiant fraction χ',0.,1.,.2,key=f'ca_{mode}_chi')
            values['threshold_kw_m2'] = st.number_input('Heat-flux threshold (kW/m²)',.01,1000.,5.,key=f'ca_{mode}_flux')
            st.caption('The 5 kW/m² default is illustrative. Effects depend on exposure duration, shielding and scenario; it is not a fatality threshold. '
                       'The point-source model is a far-field screening approximation, not a validated pipeline jet-fire model.')
        else:
            values['radius_m'] = st.number_input('Impact radius (m)',0.,100000.,50. if mode=='burst' else 20.,key=f'ca_{mode}_radius')
            st.caption('Use a radius from a separate assessment. This app does not infer its physical validity.')
        values['ignition_probability'] = st.number_input('Ignition/scenario probability given this failure mode',
            0.,1.,1.,key=f'ca_{mode}_ignition')
        values['damage_fraction'] = st.number_input('Asset damage fraction within footprint',0.,1.,1.,key=f'ca_{mode}_damage')
        st.caption('1.0 represents the assumed scenario occurring every time. Enter a justified conditional probability for your failure-mode Pf. '
                   'No ignition model or damage-vulnerability curve is inferred.')
    return HazardScenario(**values)


def render_consequence_assessment(route,segment_table=None):
    st.subheader('Consequence Assessment')
    if st.session_state.pop('ca_transfer_notice',False):
        st.success('Saved to the shared segment register. Run Risk & Reliability again to update risk.')
    st.write('Estimate impact radius and people potentially exposed for a representative event in each shared pipe segment.')
    st.info('Exposure is not a prediction of injuries or fatalities. This screening assumes uniform local population density '
            'inside each impact circle. The circle is centred at the section midpoint; it does not cover every possible release point.')
    natural_gas = st.selectbox('Pipeline product',['Natural gas','Other flammable product'])=='Natural gas'
    left,right = st.columns(2)
    with left:
        burst = hazard_controls('burst',natural_gas,segment_table is not None)
    with right:
        leak = hazard_controls('leak',natural_gas,segment_table is not None)
    st.markdown('**Population and assets by section**')
    st.caption('Download the template and vary population or asset values by shared segment. '
               'Optional overrides can be added as burst_maop_psi, burst_diameter_in, burst_heat_release_mw, '
               'leak_heat_release_mw, burst_radius_m or leak_radius_m (only the selected model uses its relevant fields). '
               'Missing values are UNKNOWN; explicit zero population means an assumed unpopulated footprint.')
    source = st.radio('Section exposure inputs',['Illustrative inputs','Upload CSV or Excel','Edit section inputs'],horizontal=True)
    template = (segment_table if segment_table is not None else consequence_template(route))[['section_id','start_km','end_km']].copy()
    for name in ['population_density_per_km2','asset_value_per_m2','burst_fixed_cost','leak_fixed_cost']:
        template[name] = float('nan')
    st.download_button('Download population/asset template',template.to_csv(index=False),'population_asset_template.csv','text/csv')
    data = template.copy()
    if source=='Illustrative inputs':
        data['population_density_per_km2'] = 100.*(1+data.section_id.mod(5))
        data['asset_value_per_m2'],data['burst_fixed_cost'],data['leak_fixed_cost'] = 10.,25000.,5000.
        st.caption('All default populations, heat-release rates and asset costs are illustrative assumptions—not measured Alberta data.')
    elif source=='Upload CSV or Excel':
        upload = st.file_uploader('Population/asset section data',type=['csv','xlsx'],key='ca_population_upload')
        if upload:
            try:
                data = pd.read_csv(io.BytesIO(upload.getvalue())) if upload.name.lower().endswith('.csv') else pd.read_excel(io.BytesIO(upload.getvalue()))
            except (ValueError,OSError,TypeError) as error:
                st.error(str(error))
    if source=='Edit section inputs':
        data = st.data_editor(data,hide_index=True,width='stretch',disabled=['section_id','start_km','end_km'],
            key='ca_editor_'+hashlib.sha256(repr(route).encode()).hexdigest())
    else:
        with st.expander('Review section inputs'):
            st.dataframe(data,hide_index=True,width='stretch')
    population_source = st.text_input('Population / asset data source and date',value='Illustrative assumptions')
    if segment_table is not None:
        lookup=segment_table.set_index('section_id')
        data['burst_maop_psi']=data.section_id.map(lookup.maop_psi)
        data['burst_diameter_in']=data.section_id.map(lookup.nominal_diameter_in)
    currency = st.text_input('Economic consequence currency / unit',value='CAD',key='ca_currency')
    st.caption('People in footprint = density(people/km²) × πr²/1,000,000. '
               'Exposure consequence = scenario probability × people in footprint. '
               'Direct economic consequence = fixed incident cost + scenario probability × πr² × asset value/m² × damage fraction. '
               'The economic overlay is a user-assumption model; no cost of life is assigned. '
               'Fixed response costs apply regardless of ignition. Do not double-count shared costs across failure modes.')
    signature = hashlib.sha256(repr((route,burst,leak,data.to_csv(index=False),population_source,currency)).encode()).hexdigest()
    if st.button('Calculate Consequences',type='primary'):
        try:
            if not currency.strip() or not population_source.strip():
                raise ValueError('Specify the economic unit and population/asset data source.')
            results = assess_consequences(route,data,burst,leak,segment_table=segment_table)
            results['population_asset_source'] = population_source
            results['economic_unit'] = currency
            results['event_location_basis'] = 'One representative midpoint event per section'
            st.session_state.ca_output = (signature,results)
        except (ValueError,TypeError,KeyError) as error:
            st.error(str(error))
    saved = st.session_state.get('ca_output')
    if saved and saved[0]!=signature:
        st.info('Inputs changed. Calculate Consequences again before using these results.')
    elif saved:
        results = saved[1]
        st.subheader('Impact radius and population exposure')
        visible = ['section_id','start_km','end_km','burst_radius_m','leak_radius_m',
                   'burst_people_in_footprint','leak_people_in_footprint',
                   'burst_exposure_consequence','leak_exposure_consequence',
                   'burst_economic_consequence','leak_economic_consequence']
        st.dataframe(results[visible],hide_index=True,width='stretch')
        figure = go.Figure()
        for mode,label in [('burst','Burst / rupture'),('leak','Leakage')]:
            figure.add_trace(go.Scatter(x=results.event_chainage_km,y=results[f'{mode}_exposure_consequence'],
                name=label,mode='lines+markers'))
        figure.update_layout(template='plotly_white',xaxis_title='Section midpoint (km)',
            yaxis_title='Expected people potentially exposed, conditional on mode failure',height=320)
        st.plotly_chart(figure,width='stretch')
        section_id = st.selectbox('Section to inspect on map',results.section_id.astype(int).tolist())
        row = results.loc[results.section_id==section_id].iloc[0]
        centre = point_at_chainage(route,float(row.event_chainage_km))
        m = folium.Map(location=centre,zoom_start=13,tiles='OpenStreetMap')
        folium.PolyLine(route,color='#2563a8',weight=4).add_to(m)
        for mode,color in [('burst','#dc2626'),('leak','#eab308')]:
            folium.Circle(centre,radius=float(row[f'{mode}_radius_m']),color=color,fill=True,fill_opacity=.12,
                tooltip=f'{mode}: radius {row[f"{mode}_radius_m"]:.1f} m; '
                        f'people in footprint {row[f"{mode}_people_in_footprint"]:.2f}').add_to(m)
        folium.Marker(centre,tooltip=f'Section {section_id} representative release point').add_to(m)
        st_folium(readable_map_overlays(m),height=430,width=1100,returned_objects=[],key=f'ca_map_{signature}_{section_id}')
        st.caption('Impact circles may overlap or cross section boundaries. Do not sum their population counts as unique residents. '
                   'A real route needs exposure assessment along the section and GIS/census data; no such data are fetched automatically.')
        st.download_button('Download full consequence assessment',results.to_csv(index=False),
                           'consequence_assessment.csv','text/csv')
        measure = st.radio('Consequence measure to use in risk profiles',
            ['People potentially exposed','Direct economic screening'],horizontal=True)
        kind = 'exposure' if measure=='People potentially exposed' else 'economic'
        unit = 'people potentially exposed' if kind=='exposure' else currency
        export = consequence_risk_inputs(results,kind)
        st.download_button('Download risk-ready consequence table',export.assign(consequence_unit=unit).to_csv(index=False),
                           'modeled_section_consequences.csv','text/csv')
        if st.button('Use these consequences in Risk & Reliability'):
            st.session_state.modeled_consequences = dict(route=route,table=export,unit=unit,
                source_signature=signature,measure=measure)
            if segment_table is not None:
                from copy import deepcopy
                project=deepcopy(st.session_state.assessment_project)
                values=export.set_index('section_id')
                for column in ['burst_consequence','leak_consequence']:
                    project['segments'][column]=project['segments'].section_id.map(values[column])
                project['consequence_unit']=unit
                st.session_state.assessment_project=project
                # Keep the editor draft in step with this explicit transfer.
                if 'project_draft' in st.session_state:
                    st.session_state.project_draft['segments']=project['segments'].copy()
                    st.session_state.project_draft['consequence_unit']=unit
                    st.session_state.project_editor_revision=st.session_state.get('project_editor_revision',0)+1
            st.session_state.ca_transfer_notice = True
            st.rerun()
    with st.expander('Model references and scope'):
        st.markdown(f'- [49 CFR 192.903: natural-gas PIR]({PIR_SOURCE}) — MAOP and nominal diameter; rupture screening, not a leakage or fatalities model.\n'
                    f'- [McGrattan, Baum & Hamins (2000), NISTIR 6546, Equation 7]({THERMAL_SOURCE}) — point-source thermal flux; no near-field or transient pipeline-release validation is implied.\n'
                    '- [EPA offsite consequence guidance, Appendix D](https://www.epa.gov/sites/default/files/2017-05/documents/oca-apds.pdf) — thermal endpoint context.\n'
                    '- [NOAA thermal radiation levels of concern](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/resources/thermal-radiation-levels-concern.html) — effects depend on heat flux and exposure duration.')
        st.write('These models do not calculate gas dispersion, toxic exposure, blast, terrain-driven liquid spread, '
                 'shielding, evacuation, fatalities or regulatory HCA designation. User-defined radii can represent separately assessed scenarios. '
                 'No Canadian/CSA compliance claim is made from the US PIR equation.')
