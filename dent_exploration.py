"""Dent sample/upload workflow using the shared asset editor and saved dataset."""
from copy import deepcopy
import json
import numpy as np
import pandas as pd
import streamlit as st
from assessment_project import validate_project
from project_editor import get_project,render_project_editor,publish_project
from exploration_datasets import sample_dent_register,dent_workbook,read_dent_register,dent_project
from dent_assessment_model import dent_geometry,dent_shape_figure
from exploration_map import render_exploration_map
from profile_map import route_length_km


def _map_summary(dents):
    # Mapping adapter only: dent displacement is never stored as a metal-loss profile.
    return pd.DataFrame({'Profile ID':dents.dent_id.astype(str),'Feature ID':dents.dent_id.astype(str),
        'Defect type':'Dent','Feature location (m)':dents.chainage_m,
        'Maximum depth (%WT)':np.nan,'Maximum depth (mm)':dents.dent_depth_mm,
        'Profile length (mm)':dents.axial_length_mm})


def render_dent_exploration(*,is_sample):
    template=sample_dent_register()
    st.caption('Dent depth is inward pipe displacement, not wall loss. It can exceed wall thickness. '
        'Signed curvature radii are measured inputs for the starting strain model; '
        'they are not inferred from dent depth or from the illustrative 3D picture.')
    left,right=st.columns(2)
    left.download_button('Download sample dent CSV',template.to_csv(index=False),'sample_dents.csv','text/csv')
    right.download_button('Download sample dent Excel',dent_workbook(template),'sample_dents.xlsx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption('Sample data only: three plain dents at 0.5, 4.5 and 8.5 km on the fictional 10 km pipe '
        '(914.4 mm OD, 11.8 mm WT). The third dent illustrates a strain-screen exceedance, not an observed failure.')
    if is_sample:
        dents=template
        content=dents.to_csv(index=False).encode()
        initial=dent_project(dents,source='Synthetic 10 km dent demonstration')
        st.info('Sample data for dent geometry. No crack/corrosion profiles are inserted into this dent-only dataset.')
    else:
        upload=st.file_uploader('Upload measured dent register',type=['csv','xlsx'],key='dent_source_upload')
        st.caption('Use the sample column names. Excel reads the Dents sheet, or the first sheet if Dents is absent. '
            'Only the dent register is read; verify route, OD, WT and segment properties below. '
            'True in associated_crack_or_metal_loss flags a combined defect that the current dent model cannot assess.')
        if upload is None:
            st.info('Upload a CSV or Excel dent register, review the shared pipeline properties, then save for Preliminary Analysis.')
            return
        try:
            content=upload.getvalue();dents=read_dent_register(content,upload.name)
            initial=dent_project(dents,base=get_project(),source='Uploaded dent register: '+upload.name)
        except (ValueError,TypeError,KeyError,OSError) as error:
            st.error('Dent register not loaded: '+str(error));return
        st.success(f'Loaded {len(dents)} dent records. Route and segment properties start from your active saved dataset.')
    with st.expander('Define shared dents, pipe segments and uncertainties',expanded=True):
        draft=render_project_editor(initial['summary'],{},content,is_sample,initial_project=initial)
    dents=draft['dent_register']
    st.subheader('Pipeline and dent locations')
    with st.expander('Upload a pipeline centreline (GeoJSON)'):
        upload=st.file_uploader('Dent pipeline LineString',type=['geojson','json'],key='dent_route_upload')
        if upload is not None and st.button('Apply dent pipeline centreline'):
            try:
                document=json.loads(upload.getvalue());geometry=document.get('geometry',document)
                if geometry['type']!='LineString':raise ValueError('Use a GeoJSON LineString.')
                route=[[float(lat),float(lon)] for lon,lat in geometry['coordinates']]
                if route_length_km(route)<=0:raise ValueError('Use a positive-length route.')
                st.session_state.data_exploration_map_route=route
                st.session_state.data_exploration_map_revision=st.session_state.get('data_exploration_map_revision',0)+1
                st.rerun()
            except (ValueError,KeyError,TypeError) as error:st.error('Route not applied: '+str(error))
    key='exploration_selected_dent'
    ids=dents.dent_id.dropna().astype(str).tolist()
    if ids:
        if st.session_state.get(key) not in ids:st.session_state[key]=ids[0]
        render_exploration_map(_map_summary(dents),st.session_state[key],selection_key=key,shared_project=True)
    publish_project(draft)
    if not ids:
        st.info('Add at least one complete dent record before saving or inspecting geometry.');return
    selected=st.selectbox('Dent geometry',ids,key=key)
    try:
        preview=deepcopy(draft)
        preview['route']=st.session_state.get('data_exploration_map_route',preview['route'])
        preview=validate_project(preview)
        result=dent_geometry(preview)
        row=result.loc[result.dent_id.astype(str)==selected].iloc[0]
        cols=st.columns(3)
        cols[0].metric('Dent displacement',f'{row.dent_depth_mm:.2f} mm')
        cols[1].metric('Dent depth / outside diameter',f'{row.depth_percent_od:.2f}%')
        cols[2].metric('Pipe wall thickness',f'{row.wall_thickness_mm:.2f} mm')
        st.plotly_chart(dent_shape_figure(row),width='stretch',key='explore_dent_3d')
        st.caption('Illustrative Gaussian pipe depression, not a measured surface or the curvature field used in '
            'strain calculations. Wall material is not removed. The register contains the actual inputs used downstream.')
        st.dataframe(dents,hide_index=True,width='stretch')
    except (ValueError,KeyError,TypeError) as error:
        st.warning('Complete the draft geometry and pipe properties to preview: '+str(error))
    st.subheader('Next: Preliminary Analysis')
    st.write('Click Save shared dataset for all analyses above, then choose the Dent workspace for deterministic '
        'strain, criterion-exceedance reliability and the consequence proxy.')
    if st.button('Open Dent Preliminary Analysis'):
        st.session_state['preliminary_threat']='Dent'
        st.switch_page('preliminary_analysis.py')
