"""Data Exploration owns the common asset, geometry and uncertainty inputs."""
from copy import deepcopy
import hashlib
import json
import pandas as pd
import streamlit as st
from assessment_project import (sample_project,default_segments,default_uncertainties,
    validate_project,project_signature,sample_route)
from profile_map import route_length_km
from reliability_inputs import LABELS


def get_project():
    if 'assessment_project' not in st.session_state:
        st.session_state.assessment_project=validate_project(sample_project())
    return st.session_state.assessment_project


def render_project_editor(summary,profiles,content,is_sample,*,initial_project=None,source_type=''):
    """Return edited draft; publication is explicit, after route review."""
    current=get_project()
    token=(('shared-sample-v3-'+initial_project['source'] if initial_project is not None else
        'shared-sample-v2-uniform-pipe') if is_sample else
        hashlib.sha256(content+str(initial_project.get('source','') if initial_project else source_type).encode()).hexdigest())
    if st.session_state.get('project_source_token')!=token:
        if initial_project is not None:
            draft=deepcopy(initial_project)
        elif is_sample:
            draft=sample_project()
        else:
            draft=dict(route=deepcopy(current['route']),summary=summary.copy(),profiles=profiles,
                workbook=content,joint_length_m=current['joint_length_m'],
                source='Uploaded measured '+source_type+' profiles',consequence_unit=current['consequence_unit'])
            draft['segments']=default_segments(draft['route'],summary)
            draft['uncertainties']=default_uncertainties(draft['segments'])
        st.session_state.project_draft=draft
        st.session_state.project_source_token=token
        st.session_state.data_exploration_map_route=deepcopy(draft['route'])
        st.session_state.project_joint_length=float(draft['joint_length_m'])
    draft=st.session_state.project_draft
    st.session_state.setdefault('project_joint_length',float(draft['joint_length_m']))
    st.subheader('Shared pipeline dataset')
    st.write('Define the asset once here. Save it to use the same route, defects, segment properties '
             'and uncertainty assumptions in Deterministic Analysis, Risk & Reliability, '
             'and Static Multiple Inspection and Excavation Planning.')
    st.caption('Chainage is distance from the route origin. Property segments may have any positive length; '
        'they must cover the entire route without gaps or overlaps. Segment IDs are not joint IDs.')
    tabs=st.tabs(['Defect register','Pipe segments & consequences','Uncertainties','Dent register'],
        default='Dent register' if draft['summary'].empty else 'Defect register')
    with tabs[0]:
        st.caption('Edit crack/corrosion chainage and type; measured profile dimensions remain unchanged. '
            'Dent displacement is entered in the separate Dent register. The sample datasets use '
            'a fictional 10 km pipe, 914.4 mm OD and 11.8 mm WT throughout.')
        draft['summary']=st.data_editor(draft['summary'],hide_index=True,width='stretch',
            disabled=[c for c in draft['summary'].columns if c not in ['Feature location (m)','Defect type']],
            key='project_defects_'+token,column_config={
                'Defect type':st.column_config.SelectboxColumn(options=['Crack','Corrosion / metal loss'])})
    with tabs[1]:
        st.caption('Nominal values below are also the means for probabilistic analysis. '
            'diameter_in: outside diameter in inches; wall_thickness_mm: WT; pressure and strengths: psi. '
            'nominal_diameter_in and maop_psi are separate inputs for consequence screening; verify them against asset records. '
            'Consequence is conditional loss for a segment event, NOT probability-weighted loss. '
            'Blank consequence = UNKNOWN; reliability can run, but corresponding risk remains unavailable.')
        st.caption('Sample material, uncertainty and consequence values are illustrative, not calibrated asset records.')
        route=st.session_state.get('data_exploration_map_route',draft['route'])
        st.write(f'Current mapped route: {route_length_km(route):.6f} km')
        if st.button('Reset segments to 1 km template (overwrites draft properties)'):
            # Explicit reset, rather than silently overwriting edited property zones.
            if route_length_km(route)<=0:
                st.error('Draw or upload a positive-length route before rebuilding its segments.')
            else:
                geometry=draft['summary']
                if geometry.empty:
                    first=draft['segments'].iloc[0]
                    geometry=pd.DataFrame([{'Feature location (m)':0.,'Outside diameter (mm)':float(first.diameter_in)*25.4,
                        'Wall thickness (mm)':float(first.wall_thickness_mm)}])
                draft['segments']=default_segments(route,geometry)
                draft['uncertainties']=default_uncertainties(draft['segments'])
                st.session_state.project_editor_revision=st.session_state.get('project_editor_revision',0)+1
                st.rerun()
        revision=st.session_state.get('project_editor_revision',0)
        draft['segments']=st.data_editor(draft['segments'],num_rows='dynamic',hide_index=True,width='stretch',
            key=f'project_segments_{token}_{revision}')
        draft['consequence_unit']=st.text_input('Shared consequence unit',draft['consequence_unit'])
    with tabs[2]:
        st.caption('One distribution and SD for each parameter in each property segment. '
            'Pipe/material/load means come from the segment table; crack/corrosion-size means come from each measured profile. '
            'SD is absolute, in the parameter units (not a coefficient of variation). '
            'Deterministic ignores SD. These are assumed uncertainties, not automatically estimated measurement accuracy.')
        st.caption('This register feeds the crack/corrosion models. The starting dent strain model uses its '
            'dedicated geometry COV and strain-criterion uncertainty controls in Preliminary Analysis → Dent.')
        with st.expander('Parameter names and units'):
            st.dataframe(pd.DataFrame([dict(parameter=n,meaning=label.replace('Crack','Crack / corrosion'))
                for n,label in LABELS.items()]),hide_index=True)
        if st.button('Synchronize uncertainty rows with segment IDs'):
            ids=pd.to_numeric(draft['segments'].section_id,errors='coerce')
            if ids.isna().any() or ids.duplicated().any() or (ids%1!=0).any():
                st.error('Enter unique integer segment IDs first.')
            else:
                defaults=default_uncertainties(draft['segments'])
                existing=draft['uncertainties'].set_index(['section_id','parameter'])
                aligned=defaults.set_index(['section_id','parameter'])
                aligned.update(existing)
                draft['uncertainties']=aligned.reset_index()
                st.session_state.project_editor_revision=revision+1
                st.rerun()
        ids=draft['uncertainties'].section_id.dropna().unique().tolist()
        if ids:
            selected=st.selectbox('Property segment — uncertainty settings',ids)
            mask=draft['uncertainties'].section_id==selected
            display=draft['uncertainties'].loc[mask].copy()
            matching=draft['segments'].loc[draft['segments'].section_id==selected]
            display['Mean / source']=[str(matching.iloc[0].get(name,'From each measured defect'))
                if not matching.empty else 'UNKNOWN segment' for name in display.parameter]
            display=display[['section_id','parameter','distribution','Mean / source','std']]
            edited=st.data_editor(display,hide_index=True,
                disabled=['section_id','parameter','Mean / source'],width='stretch',key=f'project_uncertainties_{token}_{revision}_{selected}',column_config={
                    'distribution':st.column_config.SelectboxColumn(options=['Deterministic','Normal','Lognormal','Gumbel'])})
            edited=edited.drop(columns='Mean / source')
            draft['uncertainties']=pd.concat([draft['uncertainties'].loc[~mask],edited],ignore_index=True)
        st.caption('After changing segment IDs, synchronize the uncertainty rows. Existing settings for unchanged IDs are retained.')
    with tabs[3]:
        from dent_assessment_model import empty_dent_register
        st.caption('Dent depth is inward deformation, not metal loss. Enter measured dent geometry separately. '
            'Dimensions and signed curvature radii are in mm; chainage is metres. '
            'Radii follow PHMSA Mechanical Damage (2009), section 7.2.3. '
            'Do not reinterpret crack/corrosion grids as dent measurements. Combined defects are flagged, not assessed.')
        draft['dent_register']=st.data_editor(draft.get('dent_register',empty_dent_register()),
            num_rows='dynamic',hide_index=True,width='stretch',key='project_dent_register_'+token)
    draft['profiles']=profiles
    return draft


def publish_project(draft):
    route=st.session_state.get('data_exploration_map_route',draft['route'])
    draft['route']=deepcopy(route)
    draft['joint_length_m']=float(st.session_state.get('project_joint_length',12.))
    if st.button('Save shared dataset for all analyses',type='primary'):
        try:
            project=validate_project(draft)
            st.session_state.assessment_project=project
            st.session_state.prepared_profile_route=project['route']
            st.success('Saved. Preliminary Analysis and Static Multiple Inspection and Excavation Planning now use this exact dataset.')
        except (ValueError,KeyError,TypeError) as error:
            st.error('Dataset not saved: '+str(error))
    saved=get_project()
    st.page_link('inspection_project.py',label='Continue to Inspection Planning with this saved dataset',icon=':material/calendar_month:')
    try:
        if project_signature(validate_project(draft))!=project_signature(saved):
            st.warning('Unsaved dataset changes. Downstream analyses still use the last saved dataset.')
    except (ValueError,KeyError,TypeError):
        st.warning('The draft dataset is incomplete. Fix its inputs before saving; analyses retain the last valid dataset.')
    st.caption('Active dataset: '+saved['source']+' · '+project_signature(saved)[:10]+
        '. Changes above are drafts until saved. Session data is not permanent storage.')
    st.download_button('Download active segment register',saved['segments'].to_csv(index=False),
        'pipeline_segments.csv','text/csv')
    st.download_button('Download active uncertainty register',saved['uncertainties'].to_csv(index=False),
        'segment_uncertainties.csv','text/csv')
    st.download_button('Download active defect register',saved['summary'].to_csv(index=False),
        'pipeline_defects.csv','text/csv')
    if 'dent_register' in saved:
        st.download_button('Download active dent register',saved['dent_register'].to_csv(index=False),
            'pipeline_dents.csv','text/csv')
    st.download_button('Download active route GeoJSON',json.dumps(dict(type='LineString',
        coordinates=[[lon,lat] for lat,lon in saved['route']])), 'pipeline_route.geojson','application/geo+json')
