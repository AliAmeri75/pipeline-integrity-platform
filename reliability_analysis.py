"""Shared-segment reliability, consequence and risk visualizations."""
import html
import folium
import numpy as np
import plotly.graph_objects as go
from branca.colormap import LinearColormap
from profile_map import route_length_km, point_at_chainage


def result_map(route, features, sections, column, label, pof_limit=None):
    def number(value,fmt='.4g'):
        return format(float(value),fmt) if np.isfinite(value) else 'UNKNOWN'
    m = folium.Map(location=route[0],tiles='OpenStreetMap')
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri World Imagery',name='Satellite').add_to(m)
    vertices = [route_length_km(route[:i+1]) for i in range(1,len(route))]
    maximum = float(sections[column].max())
    if not np.isfinite(maximum): maximum=1.
    scale = LinearColormap(['#16a34a','#eab308','#dc2626'],vmin=0,
                          vmax=pof_limit if pof_limit is not None else maximum if maximum>0 else 1,
                          caption=label+(' — selected Pf limit' if pof_limit is not None else ' — relative colour scale'))
    scale.add_to(m)
    for row in sections.itertuples():
        start,end = row.start_km,row.end_km
        points = [start]+[d for d in vertices if start<d<end]+[end]
        value = float(getattr(row,column))
        folium.PolyLine([point_at_chainage(route,float(d)) for d in points],weight=7,
            color=scale(value) if np.isfinite(value) else '#94a3b8',tooltip=f'Segment {row.section_id}: {start:.3f}–{end:.3f} km; {label}: '+(f'{value:.4g}' if np.isfinite(value) else 'UNKNOWN'),
            popup=f'Segment {row.section_id}<br>{start:.3f}–{end:.3f} km<br>'
                  f'Burst Pf: {row.burst_pf:.4g}<br>Leakage Pf: {row.leak_pf:.4g}<br>'
                  f'Burst consequence: {number(row.burst_consequence)}<br>Leakage consequence: {number(row.leak_consequence)}<br>'
                  f'Total expected consequence: {number(row.total_risk)}').add_to(m)
    for row in features.itertuples():
        section = sections.set_index('section_id').loc[int(row.section_id)]
        folium.CircleMarker(point_at_chainage(route,row.chainage_km),radius=6,
            color=scale(float(section[column])) if np.isfinite(section[column]) else '#94a3b8',fill=True,fill_opacity=.9,
            tooltip=f'{html.escape(str(row.feature_id))}: {row.defect_type}',
            popup=f'{html.escape(str(row.feature_id))}<br>Joint {row.joint_number}<br>'
                  f'Feature burst Pf: {row.burst_pf:.3g}<br>Feature leakage Pf: {row.leak_pf:.3g}<br>'
                  f'Segment {row.section_id}: {section.start_km:.3f}–{section.end_km:.3f} km<br>'
                  f'{label}: {number(section[column])}').add_to(m)
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


def render_reliability_analysis(*, embedded=False):
    from shared_reliability_ui import render_shared_reliability
    render_shared_reliability(embedded=embedded)

if __name__ == '__main__':
    render_reliability_analysis()
