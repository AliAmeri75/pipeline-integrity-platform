"""Post-planning spatial reliability, preserving the shared joint ownership.

Adapted from AliAmeri75/pipeline-inspection-app/joint_risk_map.py. These are
failure-probability indicators; failure consequences are not included.
"""
import html

import folium
import numpy as np
import pandas as pd
from branca.element import Element

from map_presentation import readable_map_overlays
from profile_map import point_at_chainage, route_length_km


def _joint_result_indices(result, handoff, edges):
    """Expand counted clean groups without conflating their segment populations."""
    names = list(result['joint_names'])
    if len(set(names)) != len(names):
        raise ValueError('Simulation joint/group names must be unique.')
    definitions = handoff['joints']
    if set(names) != {joint['name'] for joint in definitions}:
        raise ValueError('The simulation joint groups do not match the saved dataset. Run the comparison again.')
    lookup = {name: i for i, name in enumerate(names)}
    cracked, clean = {}, {}
    for joint in definitions:
        if joint['cracks']:
            cracked[int(joint['joint_number'])] = joint
        else:
            section = int(joint['section_id'])
            if section in clean:
                raise ValueError('Multiple initially crack-free groups exist for one segment.')
            clean[section] = joint
    segments = handoff['project']['segments'].sort_values('start_km')
    midpoints = (edges[:-1] + edges[1:]) / 2
    owners = segments.section_id.to_numpy()[
        np.searchsorted(segments.start_km.to_numpy(), midpoints, side='right') - 1]
    indices, populations = [], {joint['name']: 0 for joint in definitions}
    for number, section in enumerate(owners, start=1):
        joint = cracked.get(number) or clean.get(int(section))
        if joint is None:
            raise ValueError(f'Missing simulation group for physical joint {number}.')
        populations[joint['name']] += 1
        indices.append(lookup[joint['name']])
    for joint in definitions:
        if populations[joint['name']] != int(joint['count']):
            raise ValueError('The saved joint counts and spatial ownership do not match. Run the comparison again.')
    return np.asarray(indices, dtype=int)


def _limit_ratio(probability, limit):
    if not np.isfinite(limit) or limit < 0 or limit > 1:
        raise ValueError('Selected annual probability limits must be within [0, 1].')
    if limit == 0:
        return np.where(probability > 0, np.inf, 0.)
    return probability / limit


def sliding_window_reliability(result, handoff):
    """Return overlapping 1 km windows and each joint's worst enclosing window.

    Windows advance by one nominal joint and include a final window ending at
    the route endpoint. Boundary joints are included in full. Joint cumulative
    probabilities are combined by independent survival products before annual
    conditional increments are calculated. For routes shorter than 1 km use the
    actual route length, with no extrapolation. The whole-route planning safety
    decision remains separate from this spatial display.
    """
    route = handoff['project']['route']
    length = route_length_km(route)
    joint_length_m = float(handoff['project']['joint_length_m'])
    count = int(handoff['total_joints'])
    if not np.isfinite(joint_length_m) or joint_length_m <= 0 or length <= 0 or count < 1:
        raise ValueError('The saved pipeline must have positive length and valid physical joints.')
    times = np.asarray(result['times'], dtype=float)
    if times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('At least two finite increasing result times are required.')
    edges = np.minimum(np.arange(count + 1) * joint_length_m / 1000, length)
    if np.any(np.diff(edges) <= 0) or not np.isclose(edges[-1], length):
        raise ValueError('The spatial joint grid does not cover the saved route.')
    indices = _joint_result_indices(result, handoff, edges)
    terminal = max(0., length - 1.)
    starts = np.unique(np.r_[edges[:-1][edges[:-1] < terminal], terminal])
    ends = np.minimum(starts + 1., length)
    left = np.searchsorted(edges, starts + 1e-10, side='right') - 1
    right = np.searchsorted(edges, ends - 1e-10, side='left')
    peaks, years = [], []
    for key in ('joint_leak_pofs', 'joint_burst_pofs'):
        values = np.asarray(result[key], dtype=float)
        if values.shape != (len(result['joint_names']), len(times)) or not np.isfinite(values).all():
            raise ValueError('Joint probabilities must be finite and match the simulation groups and times.')
        cumulative = values[indices]
        if (cumulative < 0).any() or (cumulative > 1).any() or (np.diff(cumulative, axis=1) < -1e-12).any():
            raise ValueError('The spatial map requires increasing cumulative joint probabilities within [0, 1]. '
                'Repeated-failure event counts cannot be displayed as cumulative probabilities.')
        logs = np.log1p(-np.minimum(cumulative, 1 - np.finfo(float).eps))
        prefix = np.vstack([np.zeros(len(times)), np.cumsum(logs, axis=0)])
        saturated = np.vstack([np.zeros(len(times)), np.cumsum(cumulative == 1, axis=0)])
        log_survival = prefix[right] - prefix[left]
        log_survival[(saturated[right] - saturated[left]) > 0] = -np.inf
        previous = log_survival[:, :-1]
        annual = np.zeros_like(previous)
        valid = np.isfinite(previous)
        difference = np.zeros_like(previous)
        np.subtract(log_survival[:, 1:], previous, out=difference, where=valid)
        annual[valid] = -np.expm1(np.minimum(difference[valid], 0))
        annual /= np.diff(times)
        peak_index = np.argmax(annual, axis=1)
        peaks.append(annual[np.arange(len(starts)), peak_index])
        years.append(times[1:][peak_index])
    ratio = np.maximum(_limit_ratio(peaks[0], float(result['max_annual_leak_pof'])),
                       _limit_ratio(peaks[1], float(result['max_annual_burst_pof'])))
    categories = np.where(ratio > 1, 'High', np.where(ratio >= .5, 'Medium', 'Low'))
    windows = pd.DataFrame(dict(start_km=starts, end_km=ends,
        section_length_km=ends-starts, peak_annual_leak_pof=peaks[0],
        peak_annual_burst_pof=peaks[1], leak_peak_year=years[0], burst_peak_year=years[1],
        limit_ratio=ratio, category=categories))
    crack_counts = handoff['project']['summary'].groupby('Joint number').size().to_dict()
    rows = []
    for i in range(count):
        a = np.searchsorted(ends, edges[i] + 1e-10, side='right')
        b = np.searchsorted(starts, edges[i+1] - 1e-10, side='left')
        if a >= b:
            raise ValueError(f'No enclosing reliability window covers joint {i + 1}.')
        selected = a + int(np.argmax(ratio[a:b]))
        rows.append(dict(joint_id=f'Joint {i+1}', start_km=edges[i], end_km=edges[i+1],
            initial_cracks=crack_counts.get(i+1, 0), category=categories[selected],
            limit_ratio=ratio[selected], critical_window_start_km=starts[selected],
            critical_window_end_km=ends[selected],
            peak_annual_window_leak_pof=peaks[0][selected],
            peak_annual_window_burst_pof=peaks[1][selected]))
    return windows, pd.DataFrame(rows)


def reliability_map(route, table):
    """Draw the saved bent route and retain a high-contrast reliability legend."""
    pipeline_map = folium.Map(location=route[0], tiles='OpenStreetMap')
    colors = {'High': '#dc2626', 'Medium': '#eab308', 'Low': '#16a34a'}
    groups = (table.category != table.category.shift()).cumsum()
    vertex_distances = [route_length_km(route[:i+1]) for i in range(1, len(route))]
    for _, group in table.groupby(groups):
        start, end = float(group.start_km.iloc[0]), float(group.end_km.iloc[-1])
        distances = [start] + [d for d in vertex_distances if start < d < end] + [end]
        category = group.category.iloc[0]
        folium.PolyLine([point_at_chainage(route, d) for d in distances],
            color=colors[category], weight=7,
            tooltip=f'{category}: {start:.3f}–{end:.3f} km').add_to(pipeline_map)
    for row in table[table.initial_cracks > 0].itertuples():
        folium.CircleMarker(point_at_chainage(route, (row.start_km + row.end_km)/2),
            radius=6, color=colors[row.category], fill=True, fill_opacity=.9,
            tooltip=f'{html.escape(row.joint_id)}: {row.category}',
            popup=f'{html.escape(row.joint_id)}<br>{row.initial_cracks} initial cracks<br>'
                  f'Worst enclosing window: {row.critical_window_start_km:.3f}–{row.critical_window_end_km:.3f} km<br>'
                  f'Peak annual window leakage Pf: {row.peak_annual_window_leak_pof:.3g}<br>'
                  f'Peak annual window burst Pf: {row.peak_annual_window_burst_pof:.3g}').add_to(pipeline_map)
    legend = '''<div style="position:fixed;bottom:25px;left:25px;z-index:9999;
        background:white;color:#111827;border:1px solid #cbd5e1;border-radius:8px;
        padding:12px;box-shadow:0 3px 12px #0003;font-size:13px">
        <b>Planning Reliability — Selected Pf Limits</b><br>
        <span style="color:#dc2626">●</span> High: above a limit<br>
        <span style="color:#eab308">●</span> Medium: 50–100% of a limit<br>
        <span style="color:#16a34a">●</span> Low: below 50%<br>
        Worst overlapping 1 km window; no consequences included</div>'''
    pipeline_map.get_root().html.add_child(Element(legend))
    pipeline_map.fit_bounds(route)
    return readable_map_overlays(pipeline_map)
