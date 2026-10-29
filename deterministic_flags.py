"""User-selected deterministic screening flags and FPR chart annotations."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from academic_figures import academic_style

SEVERE_LABEL='Severe → immediate action!'


def flag_profiles(results):
    data=results.copy()
    fpr=pd.to_numeric(data.FPR,errors='coerce')
    depth=pd.to_numeric(data['Defect depth (mm)'],errors='coerce')
    wall=pd.to_numeric(data['Wall thickness (mm)'],errors='coerce')
    ratio=depth/wall.where(wall>0)
    data['Depth / WT']=ratio
    data['FPR < 1.1']=np.isfinite(fpr)&(fpr<1.1)
    data['Depth > 50% WT']=np.isfinite(ratio)&(ratio>.5)
    data['Severe']=data['FPR < 1.1']|data['Depth > 50% WT']
    data['Screening status']=np.where(data.Severe,SEVERE_LABEL,
        np.where(np.isfinite(fpr)&np.isfinite(ratio),'No threshold exceeded','Assessment incomplete'))
    data['Screening reason']=[
        '; '.join(reason for active,reason in [(low,'FPR < 1.1'),(deep,'Depth > 50% WT')] if active)
        for low,deep in zip(data['FPR < 1.1'],data['Depth > 50% WT'])]
    return data


def fpr_distance_figure(results):
    data=flag_profiles(results)
    calculated=data[(data.Status=='Calculated')&(pd.to_numeric(data.FPR,errors='coerce')>0)]
    figure=go.Figure(go.Scatter(x=calculated['Distance from start (km)'],y=calculated.FPR,
        customdata=calculated[['Profile ID','Screening reason','Depth / WT']].to_numpy(),
        name='Crack profiles',mode='markers',
        marker=dict(size=10,color=calculated.FPR,colorscale='RdYlGn',showscale=True),
        hovertemplate='Profile %{customdata[0]}<br>%{x:.3f} km<br>FPR %{y:.3f}<br>'
            'Depth/WT %{customdata[2]:.3f}<br>%{customdata[1]}<extra></extra>'))
    severe=calculated[calculated.Severe]
    if not severe.empty:
        figure.add_trace(go.Scatter(x=severe['Distance from start (km)'],y=severe.FPR,
            customdata=severe[['Profile ID','Screening reason','Depth / WT']].to_numpy(),
            mode='markers',name=SEVERE_LABEL,showlegend=True,
            marker=dict(symbol='circle-open',size=26,color='#dc2626',line=dict(width=3)),
            hovertemplate='Profile %{customdata[0]}<br>FPR %{y:.3f}<br>%{customdata[1]}<extra>'+SEVERE_LABEL+'</extra>'))
    figure.add_hline(y=1.1,line_dash='dash',line_color='#dc2626',annotation_text='FPR = 1.1 screening threshold',annotation_position='top right')
    figure.add_hline(y=1,line_dash='dot',line_color='#64748b',annotation_text='FPR = 1',annotation_position='bottom right')
    figure.update_layout(template='plotly_white',xaxis_title='Distance from route start (km)',
        yaxis_title='FPR',height=370,clickmode='event+select',margin=dict(t=65,r=75),
        legend=dict(orientation='h',y=-.25))
    academic_style(figure)
    figure.update_yaxes(type='linear')
    return figure
