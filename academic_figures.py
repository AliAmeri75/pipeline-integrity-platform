"""Consistent publication-style assessment charts; no changes to model results."""
import math

FONT='Times New Roman, Times, serif'


def academic_style(figure):
    figure.update_layout(template='plotly_white',paper_bgcolor='white',plot_bgcolor='white',
        font=dict(family=FONT,size=16,color='#111111'),height=450,
        title_font=dict(family=FONT,size=20,color='#111111'),
        margin=dict(l=85,r=65,t=75,b=100),
        legend=dict(orientation='h',y=-.24,bgcolor='white',bordercolor='#d1d5db',borderwidth=1),
        hoverlabel=dict(bgcolor='white',font_family=FONT))
    figure.update_xaxes(showline=True,mirror=True,linecolor='#111111',linewidth=1,
        ticks='outside',showgrid=True,gridcolor='#e5e7eb',zeroline=False)
    figure.update_yaxes(showline=True,mirror=True,linecolor='#111111',linewidth=1,
        ticks='outside',showgrid=True,gridcolor='#e5e7eb',zeroline=False)
    figure.update_annotations(font_family=FONT,bgcolor='white',borderpad=4)
    return figure


def logarithmic_y(figure,thresholds=(),probability=False):
    """Use only positive plotted values for log limits; never substitute for zero."""
    values=[float(v) for trace in figure.data if trace.y is not None for v in trace.y
            if v is not None and math.isfinite(float(v)) and float(v)>0]
    values += [float(v) for v in thresholds if math.isfinite(float(v)) and float(v)>0]
    low,high=(min(values),max(values)) if values else (1e-4,1.)
    bottom,top=math.log10(low)-.45,math.log10(high)+.45
    if probability:
        top=min(0.,top)
    figure.update_yaxes(type='log',range=[bottom,top],exponentformat='power',showexponent='all')
    # Plotly shapes take raw data coordinates, but annotations on a log axis
    # take log10 coordinates. Convert labels created by add_hline accordingly.
    for annotation in figure.layout.annotations:
        if annotation.yref=='y' and annotation.y is not None and float(annotation.y)>0:
            annotation.y=math.log10(float(annotation.y))
    return figure
