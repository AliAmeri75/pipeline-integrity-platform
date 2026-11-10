"""Manual entry and uploads alongside the existing measured-profile workflow."""
from copy import deepcopy

import numpy as np
import pandas as pd
import streamlit as st

from exploration_inputs import (
    REGISTER_COLUMNS, apply_route, defect_register, project_from_register,
    read_defect_register, read_route, register_workbook, snap_to_route,
)
from profile_map import route_length_km


def _refresh_defect_editor():
    st.session_state['project_defect_revision'] = st.session_state.get('project_defect_revision', 0) + 1


def _replace_defects(draft, table):
    updated = project_from_register(draft, table)
    draft.update(updated)
    draft.pop('_defect_input_error', None)
    _refresh_defect_editor()


def add_defect(draft, chainage_m):
    """Use the same current dimensions for map pins and chainage entry."""
    if draft.get('_defect_input_error'):
        raise ValueError('Complete or remove the unfinished table rows before adding a map defect.')
    kind = st.session_state.get('exploration_new_defect_type', 'Crack')
    prefix = 'C' if kind == 'Crack' else 'COR'
    table = defect_register(draft)
    ids, number = set(table.defect_id), 1
    while f'{prefix}-{number:03d}' in ids:
        number += 1
    record = dict(zip(REGISTER_COLUMNS, [
        f'{prefix}-{number:03d}', kind, chainage_m,
        st.session_state.get('exploration_new_depth_mm', 1.),
        st.session_state.get('exploration_new_length_mm', 40.),
        st.session_state.get('exploration_new_width_mm', 20.) if kind != 'Crack' else np.nan,
    ]))
    _replace_defects(draft, pd.concat([table, pd.DataFrame([record])], ignore_index=True))


def add_map_defect(draft, latitude, longitude):
    chainage, offset = snap_to_route(draft['route'], latitude, longitude)
    # Prevent a mistaken click far from the pipe from becoming an unnoticed input.
    if offset > 100:
        raise ValueError(f'That point is {offset:,.0f} m from the pipeline. Place the pin within 100 m of the line.')
    add_defect(draft, chainage)


def render_defect_inputs(draft, token):
    st.write('One row per defect. Edit its size or location, add a row at the bottom, '
             'or select rows and delete them. Several defects can belong to the same pipe joint.')
    st.caption('Distance is measured from the pipeline start, in metres. Depth and length are in mm. '
               'Cracks need no width; corrosion features also need a width.')
    revision = st.session_state.get('project_defect_revision', 0)
    key = f'project_defect_register_{token}_{revision}'
    base_key = '_base_' + key
    # Keep the editor's input stable while its row edits are applied. On a return
    # from another page, rebase from the retained draft after widget cleanup.
    if key not in st.session_state or base_key not in st.session_state:
        st.session_state[base_key] = defect_register(draft)
    edited = st.data_editor(
        st.session_state[base_key], num_rows='dynamic', hide_index=True, width='stretch', key=key,
        column_config={
            'defect_id': st.column_config.TextColumn('Defect ID', required=True),
            'defect_type': st.column_config.SelectboxColumn('Type',
                options=['Crack', 'Corrosion / metal loss'], required=True, default='Crack'),
            'chainage_m': st.column_config.NumberColumn('Distance from start (m)', min_value=0., format='%.3f', required=True),
            'depth_mm': st.column_config.NumberColumn('Depth (mm)', min_value=.0001, format='%.3f', required=True),
            'length_mm': st.column_config.NumberColumn('Length (mm)', min_value=.0001, format='%.2f', required=True),
            'width_mm': st.column_config.NumberColumn('Corrosion width (mm)', min_value=.0001, format='%.2f'),
        },
    )
    try:
        draft.update(project_from_register(draft, edited))
        draft.pop('_defect_input_error', None)
    except (ValueError, TypeError, KeyError) as error:
        draft['_defect_input_error'] = str(error)
        st.error(str(error) + ' The map keeps the last complete rows until this is corrected.')
    st.caption(f'{len(draft["summary"])} complete defect(s) in this draft. '
               'New or resized defects use an illustrative shape based on the entered dimensions. '
               'Unchanged imported profile grids are retained.')

    with st.expander('Add a defect by distance or map pin', expanded=True):
        kind, depth, length = st.columns(3)
        kind.selectbox('New defect type', ['Crack', 'Corrosion / metal loss'],
                       key='exploration_new_defect_type')
        depth.number_input('New defect depth (mm)', min_value=.0001, value=1., step=.1,
                           key='exploration_new_depth_mm')
        length.number_input('New defect length (mm)', min_value=.0001, value=40., step=1.,
                            key='exploration_new_length_mm')
        if st.session_state.exploration_new_defect_type != 'Crack':
            st.number_input('New corrosion width (mm)', min_value=.0001, value=20., step=1.,
                            key='exploration_new_width_mm')
        location, action = st.columns([2, 1], vertical_alignment='bottom')
        chainage = location.number_input('New defect distance from pipeline start (m)',
            min_value=0., value=0., step=1., key='exploration_new_chainage_m')
        if action.button('Add defect at this distance'):
            try:
                add_defect(draft, chainage)
                st.rerun()
            except (ValueError, TypeError, KeyError) as error:
                st.error(str(error))
        st.caption('Or use the pin tool on the map below. It adds a defect using these dimensions '
                   'and places it on the nearest point of the pipeline.')

    with st.expander('Upload crack / corrosion data (CSV or Excel)'):
        st.caption('Columns: defect_id, chainage_m, depth_mm, length_mm; optional defect_type '
                   'and width_mm for corrosion. Existing static-planning CSVs with crack_id, '
                   'latitude, longitude, depth_mm and length_mm are also accepted. '
                   'Load the correct route before importing GPS locations.')
        upload = st.file_uploader('Upload a defect size table', type=['csv', 'xlsx', 'xlsm'],
                                  key='simple_defect_upload_' + token)
        if upload is not None:
            try:
                incoming = read_defect_register(upload.getvalue(), upload.name, draft['route'])
                st.dataframe(incoming, hide_index=True, width='stretch')
                offset = incoming.attrs.get('maximum_gps_offset_m')
                if offset is not None:
                    st.info(f'GPS locations projected onto the current route. Largest offset: {offset:,.1f} m. '
                            'Check this before applying the upload.')
                if st.button('Replace defect register with uploaded data'):
                    _replace_defects(draft, incoming)
                    st.rerun()
            except (ValueError, TypeError, KeyError) as error:
                st.error('Defect table not loaded: ' + str(error))
        current = defect_register(draft)
        csv, excel = st.columns(2)
        csv.download_button('Download editable defect CSV', current.to_csv(index=False),
                            'defect_inputs.csv', 'text/csv')
        excel.download_button('Download editable defect Excel', register_workbook(current),
                              'defect_inputs.xlsx',
                              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def set_route(draft, route):
    draft.update(apply_route(draft, route))
    st.session_state.data_exploration_map_route = deepcopy(route)
    st.session_state.data_exploration_map_revision = st.session_state.get('data_exploration_map_revision', 0) + 1
    st.session_state.project_editor_revision = st.session_state.get('project_editor_revision', 0) + 1


def render_route_inputs(draft):
    with st.expander('Enter or upload pipeline route coordinates'):
        st.caption('List latitude and longitude in order from the pipeline start. '
                   'You can also draw the centreline on the map. Defect distances stay unchanged when a route changes.')
        st.caption('Applying a route retains existing pipe properties: zones beyond its end are trimmed, '
                   'and the final zone is extended when the route is longer. Review Pipe segments & consequences before saving.')
        revision = st.session_state.get('data_exploration_map_revision', 0)
        key = f'exploration_route_coordinates_{revision}'
        route = st.session_state.get('data_exploration_map_route', draft['route'])
        points = st.data_editor(pd.DataFrame(route, columns=['latitude', 'longitude']),
            num_rows='dynamic', hide_index=True, width='stretch', key=key,
            column_config={
                'latitude': st.column_config.NumberColumn('Latitude', min_value=-90., max_value=90., format='%.6f', required=True),
                'longitude': st.column_config.NumberColumn('Longitude', min_value=-180., max_value=180., format='%.6f', required=True),
            })
        if st.button('Apply route coordinates'):
            try:
                parsed = read_route(points.dropna(how='all').to_csv(index=False).encode(), 'route.csv')
                set_route(draft, parsed)
                st.rerun()
            except (ValueError, TypeError, KeyError) as error:
                st.error('Route not applied: ' + str(error))
        upload = st.file_uploader('Upload pipeline route (GeoJSON, CSV or Excel)',
            type=['geojson', 'json', 'csv', 'xlsx'], key='exploration_route_file')
        if upload is not None and st.button('Apply uploaded centreline'):
            try:
                set_route(draft, read_route(upload.getvalue(), upload.name))
                st.rerun()
            except (ValueError, TypeError, KeyError) as error:
                st.error('Route not applied: ' + str(error))
        st.download_button('Download editable route CSV',
            pd.DataFrame(route, columns=['latitude', 'longitude']).to_csv(index=False),
            'pipeline_route.csv', 'text/csv')
