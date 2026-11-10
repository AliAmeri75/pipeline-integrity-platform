"""Editable size registers and route imports for the shared assessment dataset.

Measured grids are retained for unchanged defects. A new or resized defect gets
an explicitly labelled illustrative shape; size-only inputs are never presented
as new inspection measurements.
"""
from copy import deepcopy
import io
import json
import math

import numpy as np
import pandas as pd

from profile_data import SUMMARY_COLUMNS
from profile_map import haversine_distance_km, route_length_km


REGISTER_COLUMNS = [
    'defect_id', 'defect_type', 'chainage_m', 'depth_mm', 'length_mm', 'width_mm',
]
ILLUSTRATIVE_SHAPE = 'Entered dimensions; illustrative shape'


def defect_register(project):
    """Return the simple, editable inputs, without derived joint/segment IDs."""
    summary = project['summary']
    return pd.DataFrame({
        'defect_id': summary['Profile ID'].astype(str),
        'defect_type': summary['Defect type'],
        'chainage_m': summary['Feature location (m)'],
        'depth_mm': summary['Maximum depth (mm)'],
        'length_mm': summary['Profile length (mm)'],
        'width_mm': summary.get('Profile width (mm)', np.nan),
    }).reset_index(drop=True)[REGISTER_COLUMNS]


def snap_to_route(route, latitude, longitude):
    """Project a GPS point to the nearest centreline leg; return chainage/offset.

    A local equirectangular projection is used for each leg, and distance along
    the route uses the same great-circle lengths as the map and joint adapter.
    """
    if route_length_km(route) <= 0:
        raise ValueError('Define the pipeline route before locating defects by GPS.')
    latitude, longitude = float(latitude), float(longitude)
    if not np.isfinite([latitude, longitude]).all() or not (
            -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Defect GPS coordinates must be valid latitude/longitude values.')
    best, traversed = None, 0.
    for start, end in zip(route[:-1], route[1:]):
        leg = haversine_distance_km(start, end) * 1000
        scale = math.cos(math.radians((start[0] + end[0] + latitude) / 3))
        vector = np.array([(end[1] - start[1]) * scale, end[0] - start[0]])
        point = np.array([(longitude - start[1]) * scale, latitude - start[0]])
        fraction = float(np.clip(np.dot(point, vector) / np.dot(vector, vector), 0, 1)) if leg else 0.
        snapped = [start[i] + fraction * (end[i] - start[i]) for i in (0, 1)]
        offset = haversine_distance_km([latitude, longitude], snapped) * 1000
        candidate = (offset, traversed + fraction * leg)
        if best is None or candidate < best:
            best = candidate
        traversed += leg
    return best[1], best[0]


def _read_table(content, filename, sheet_name):
    try:
        if filename.lower().endswith('.csv'):
            data = pd.read_csv(io.BytesIO(content), dtype=object)
        elif filename.lower().endswith(('.xlsx', '.xlsm')):
            with pd.ExcelFile(io.BytesIO(content), engine='openpyxl') as book:
                sheet = sheet_name if sheet_name in book.sheet_names else book.sheet_names[0]
                data = pd.read_excel(book, sheet_name=sheet, dtype=object)
        else:
            raise ValueError('Use a CSV or Excel (.xlsx) table.')
    except Exception as error:
        raise ValueError('Could not read the table: ' + str(error)) from error
    data.columns = [str(c).strip() for c in data.columns]
    return data


def validate_register(table, route):
    """Validate entered dimensions and retain multiple defects in one joint."""
    data = table.dropna(how='all').copy().reset_index(drop=True)
    if data.empty:
        return pd.DataFrame(columns=REGISTER_COLUMNS)
    missing = set(REGISTER_COLUMNS[:-1]) - set(data.columns)
    if missing:
        raise ValueError('Missing defect columns: ' + ', '.join(sorted(missing)))
    if 'width_mm' not in data:
        data['width_mm'] = np.nan
    if data.defect_id.isna().any() or data.defect_id.astype(str).str.strip().eq('').any():
        raise ValueError('Give every defect a unique Defect ID.')
    data['defect_id'] = data.defect_id.astype(str).str.strip()
    if data.defect_id.duplicated().any():
        raise ValueError('Defect IDs must be unique; defects may share the same location or joint.')
    kinds = data.defect_type.astype(str).str.strip().str.casefold()
    data['defect_type'] = kinds.map({
        'crack': 'Crack', 'corrosion': 'Corrosion / metal loss',
        'corrosion / metal loss': 'Corrosion / metal loss', 'metal loss': 'Corrosion / metal loss',
    })
    if data.defect_type.isna().any():
        raise ValueError('Choose Crack or Corrosion / metal loss. Use the Dent register for dents.')
    for column in ['chainage_m', 'depth_mm', 'length_mm']:
        data[column] = pd.to_numeric(data[column], errors='coerce')
        if not np.isfinite(data[column]).all():
            raise ValueError('Complete every defect location, depth and length with finite numbers.')
    if (data[['depth_mm', 'length_mm']] <= 0).any().any():
        raise ValueError('Defect depth and length must be positive, in millimetres.')
    length_m = route_length_km(route) * 1000
    if length_m <= 0:
        raise ValueError('Draw, enter or upload a positive-length pipeline route first.')
    if not data.chainage_m.between(0, length_m + 1e-5).all():
        raise ValueError(f'Defect distances must be between 0 and {length_m:,.3f} m along the route.')
    data['width_mm'] = pd.to_numeric(data.width_mm, errors='coerce')
    corrosion = data.defect_type.eq('Corrosion / metal loss')
    if (not np.isfinite(data.loc[corrosion, 'width_mm']).all() or
            (data.loc[corrosion, 'width_mm'] <= 0).any()):
        raise ValueError('Enter a positive width in mm for each corrosion feature. Cracks need no width.')
    data.loc[~corrosion, 'width_mm'] = np.nan
    return data[REGISTER_COLUMNS]


def read_defect_register(content, filename, route):
    """Read size tables using chainage (m/km) or mapped latitude/longitude."""
    data = _read_table(content, filename, 'Defects')
    aliases = {
        'crack_id': 'defect_id', 'profile_id': 'defect_id', 'Profile ID': 'defect_id',
        'feature_id': 'defect_id', 'Defect ID': 'defect_id', 'Defect type': 'defect_type',
        'Feature location (m)': 'chainage_m', 'distance_m': 'chainage_m',
        'Maximum depth (mm)': 'depth_mm', 'Profile length (mm)': 'length_mm',
        'Profile width (mm)': 'width_mm', 'Latitude': 'latitude', 'Longitude': 'longitude',
    }
    for old, new in aliases.items():
        if old in data and new not in data:
            data = data.rename(columns={old: new})
    if 'defect_type' not in data:
        data['defect_type'] = 'Crack'
    if 'chainage_m' not in data:
        if 'chainage_km' in data:
            data['chainage_m'] = pd.to_numeric(data.chainage_km, errors='coerce') * 1000
        elif {'latitude', 'longitude'}.issubset(data.columns):
            locations = [snap_to_route(route, lat, lon) for lat, lon in
                         zip(data.latitude, data.longitude)]
            data['chainage_m'] = [location[0] for location in locations]
            data.attrs['maximum_gps_offset_m'] = max((location[1] for location in locations), default=0.)
        else:
            raise ValueError('Provide chainage_m, chainage_km, or latitude and longitude for each defect.')
    result = validate_register(data, route)
    result.attrs.update(data.attrs)
    return result


def _illustrative_profile(length, depth, width, wall):
    """Idealized ellipse/slit for size-only inputs; never a measured grid."""
    xs = np.linspace(0., length, 25)
    # Cracks have no assessed width. The tiny plotting band only makes the slit visible.
    ys = np.linspace(-width / 2, width / 2, 13) if width else np.array([-.01, 0., .01])
    records = []
    for y in ys:
        transverse = max(0., 1 - (2 * y / width) ** 2) ** .5 if width else (1. if y == 0 else 0.)
        for x in xs:
            d = depth * max(0., 1 - (2 * x / length - 1) ** 2) ** .5 * transverse
            records.append({'Axial offset (mm)': x, 'Circumferential offset (mm)': y,
                            'Depth (%WT)': d / wall * 100})
    profile = pd.DataFrame(records)
    profile.attrs['illustrative'] = True
    return profile


def project_from_register(project, table):
    """Build a draft, preserving unchanged measured profiles and original inputs."""
    p = deepcopy(project)
    data = validate_register(table, p['route'])
    old = p['summary'].set_index('Profile ID', drop=False)
    records, profiles = [], {}
    for row in data.itertuples(index=False):
        original = old.loc[row.defect_id] if row.defect_id in old.index else None
        same_size = original is not None and (
            str(original['Defect type']) == row.defect_type and
            np.isclose(float(original['Maximum depth (mm)']), row.depth_mm, rtol=0, atol=1e-10) and
            np.isclose(float(original['Profile length (mm)']), row.length_mm, rtol=0, atol=1e-10) and
            (row.defect_type == 'Crack' or np.isclose(
                float(original['Profile width (mm)']), row.width_mm, rtol=0, atol=1e-10)))
        if same_size:
            record = original.to_dict()
            profiles[row.defect_id] = p['profiles'][row.defect_id].copy()
        else:
            segments = p['segments'].sort_values('start_km')
            position = np.clip(np.searchsorted(segments.start_km, row.chainage_m / 1000,
                                              side='right') - 1, 0, len(segments) - 1)
            segment = segments.iloc[position]
            wall, diameter = float(segment.wall_thickness_mm), float(segment.diameter_in) * 25.4
            if not np.isfinite([wall, diameter]).all() or min(wall, diameter) <= 0:
                raise ValueError('Enter positive pipe diameter and wall thickness in the property segments.')
            width = row.width_mm if row.defect_type != 'Crack' else None
            profiles[row.defect_id] = _illustrative_profile(row.length_mm, row.depth_mm, width, wall)
            record = {column: np.nan for column in SUMMARY_COLUMNS}
            record.update({'Profile ID': row.defect_id, 'Feature ID': row.defect_id,
                'Defect type': row.defect_type, 'Maximum depth (mm)': row.depth_mm,
                'Maximum depth (%WT)': row.depth_mm / wall * 100,
                'Profile length (mm)': row.length_mm, 'Profile width (mm)': row.width_mm,
                'Wall thickness (mm)': wall, 'Outside diameter (mm)': diameter,
                'Measured profile cells': 0, 'Shape source': ILLUSTRATIVE_SHAPE})
        record.update({'Feature location (m)': row.chainage_m,
            'Profile start (m)': row.chainage_m,
            'Profile end (m)': row.chainage_m + row.length_mm / 1000})
        records.append(record)
    p['summary'] = pd.DataFrame(records) if records else p['summary'].iloc[:0].copy()
    # Derived assignments are recomputed by validate_project at preview/Save.
    p['summary'] = p['summary'].drop(columns=[
        'Segment ID', 'Distance from start (km)', 'Joint number',
    ], errors='ignore')
    if not p['summary'].empty and p['summary']['Defect type'].eq('Crack').all():
        p['summary'] = p['summary'].drop(columns='Profile width (mm)', errors='ignore')
    p['profiles'] = profiles
    return p


def read_route(content, filename):
    """Read a single GeoJSON centreline or ordered latitude/longitude table."""
    if filename.lower().endswith(('.json', '.geojson')):
        try:
            document = json.loads(content)
            if document.get('type') == 'FeatureCollection':
                features = document.get('features', [])
                if len(features) != 1:
                    raise ValueError('Use one pipeline LineString per route file.')
                document = features[0]
            geometry = document.get('geometry', document)
            if geometry.get('type') != 'LineString':
                raise ValueError('Use a GeoJSON LineString or a Feature containing one.')
            route = [[float(point[1]), float(point[0])] for point in geometry['coordinates']]
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as error:
            raise ValueError('Could not read the GeoJSON route: ' + str(error)) from error
    else:
        table = _read_table(content, filename, 'Route')
        names = {str(c).casefold(): c for c in table.columns}
        if not {'latitude', 'longitude'}.issubset(names):
            raise ValueError('Route tables need latitude and longitude columns, in pipeline order.')
        route = table[[names['latitude'], names['longitude']]].astype(float).values.tolist()
    if route_length_km(route) <= 0:
        raise ValueError('Enter at least two distinct, valid route coordinates.')
    return route


def apply_route(project, route):
    """Keep existing property zones, trimming/extending the final zone as needed.

    Existing defects retain chainage; saving still rejects defects outside the new
    route. Reused pipe properties are a visible draft assumption for user review.
    """
    length = route_length_km(route)
    if length <= 0:
        raise ValueError('Enter at least two distinct, valid route coordinates.')
    p = deepcopy(project)
    segments = p['segments'].sort_values('start_km').copy()
    segments = segments.loc[segments.start_km < length - 1e-9].copy()
    if segments.empty:
        raise ValueError('The property register must start at the pipeline origin.')
    segments.iloc[-1, segments.columns.get_loc('end_km')] = length
    p['route'], p['segments'] = deepcopy(route), segments.reset_index(drop=True)
    p['uncertainties'] = p['uncertainties'].loc[
        p['uncertainties'].section_id.isin(segments.section_id)].copy()
    return p


def register_workbook(table):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        table.to_excel(writer, sheet_name='Defects', index=False)
        sheet = writer.sheets['Defects']
        sheet.freeze_panes = 'A2'
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 24
    return output.getvalue()
