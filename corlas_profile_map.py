"""Pointwise CorLAS screening at measured depths with fixed profile length."""
from dataclasses import replace
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from education.pof_model import corlas_failure_pressure
from profile_visuals import measured_depth_grid


def evaluate_profile_grid(profile,base_inputs,wall_mm,diameter_mm,length_mm):
    try:
        geometry=np.asarray([wall_mm,diameter_mm,length_mm,base_inputs.operating_pressure_psi],dtype=float)
    except (ValueError,TypeError) as error:
        raise ValueError('Numeric pipe geometry and operating pressure are required.') from error
    if not np.isfinite(geometry).all() or (geometry<=0).any():
        raise ValueError('Positive finite wall thickness, diameter, profile length and operating pressure are required.')
    wall_mm,diameter_mm,length_mm=map(float,[wall_mm,diameter_mm,length_mm])
    xs,ys,depths,unit=measured_depth_grid(profile,wall_mm)
    if unit!='mm':
        raise ValueError('Wall thickness is required to convert measured depths to mm.')
    records=[]
    # Identical depths have identical resistance with all other inputs fixed.
    evaluated={}
    for j,y in enumerate(ys):
        for i,x in enumerate(xs):
            depth=float(depths[j,i])
            pressure,fpr=np.nan,np.nan
            status='Not calculated'
            if not np.isfinite(depth):
                status='No finite measurement'
            elif depth<0:
                status='Invalid negative depth'
            elif depth==0:
                status='Zero depth: no crack resistance calculated'
            elif depth>=wall_mm:
                status='Through-wall depth: CorLAS not applicable'
            else:
                if depth not in evaluated:
                    try:
                        inputs=replace(base_inputs,wall_thickness_mm=wall_mm,diameter_in=diameter_mm/25.4,
                            flaw_length_mm=length_mm,flaw_depth_mm=depth)
                        resistance=float(corlas_failure_pressure(inputs)['failure_pressure_psi'])
                        if not np.isfinite(resistance) or resistance<=0:
                            raise ValueError('CorLAS returned invalid resistance')
                        evaluated[depth]=(resistance,resistance/base_inputs.operating_pressure_psi,'Calculated')
                    except (ValueError,ArithmeticError) as error:
                        evaluated[depth]=(np.nan,np.nan,str(error))
                pressure,fpr,status=evaluated[depth]
            records.append({'Axial offset (mm)':x,'Circumferential offset (mm)':y,
                'Measured depth (mm)':depth,'Burst resistance pressure (psi)':pressure,'FPR':fpr,
                'Profile length used (mm)':length_mm,'Operating pressure (psi)':base_inputs.operating_pressure_psi,
                'Status':status})
    return pd.DataFrame(records)


def minimum_grid_result(cells):
    valid=cells[cells.Status=='Calculated']
    if valid.empty:
        return None
    return valid.loc[valid.FPR.idxmin()].to_dict()


def corlas_depth_pressure_figure(cells,profile_id):
    x=sorted(cells['Axial offset (mm)'].unique())
    y=sorted(cells['Circumferential offset (mm)'].unique())
    def grid(column):
        return cells.pivot(index='Circumferential offset (mm)',columns='Axial offset (mm)',
            values=column).reindex(index=y,columns=x).to_numpy()
    depth=grid('Measured depth (mm)')
    pressure=grid('Burst resistance pressure (psi)')
    fpr=grid('FPR')
    status=grid('Status')
    custom=np.empty(depth.shape+(3,),dtype=object)
    custom[:,:,0],custom[:,:,1],custom[:,:,2]=depth,fpr,status
    figure=make_subplots(rows=1,cols=2,shared_yaxes=True,horizontal_spacing=.16,
        subplot_titles=['Measured crack depth','CorLAS burst resistance'])
    figure.add_trace(go.Heatmap(x=x,y=y,z=depth,colorscale='YlOrRd',connectgaps=False,
        colorbar=dict(title='Depth<br>(mm)',x=.42,len=.85),
        hovertemplate='Axial %{x:.2f} mm<br>Circumferential %{y:.2f} mm<br>Depth %{z:.4f} mm<extra></extra>'),row=1,col=1)
    figure.add_trace(go.Heatmap(x=x,y=y,z=pressure,colorscale='RdYlGn',connectgaps=False,
        customdata=custom,colorbar=dict(title='Burst pressure<br>(psi)',x=1.02,len=.85),
        hovertemplate='Axial %{x:.2f} mm<br>Circumferential %{y:.2f} mm<br>'
            'Depth %{customdata[0]:.4f} mm<br>CorLAS pressure %{z:.2f} psi<br>'
            'FPR %{customdata[1]:.4f}<br>%{customdata[2]}<extra></extra>'),row=1,col=2)
    lowest=minimum_grid_result(cells)
    if lowest is not None:
        for col in (1,2):
            figure.add_trace(go.Scatter(x=[lowest['Axial offset (mm)']],y=[lowest['Circumferential offset (mm)']],
                mode='markers',marker=dict(symbol='x',size=12,color='#111827'),showlegend=False,
                hovertemplate='Minimum calculated FPR: '+f'{lowest["FPR"]:.4f}'+'<extra></extra>'),row=1,col=col)
    figure.update_xaxes(title_text='Axial offset (mm)')
    figure.update_yaxes(title_text='Circumferential offset (mm)',row=1,col=1)
    figure.update_layout(title='Profile '+str(profile_id)+' · depth and resistance',height=430,
        template='plotly_white',margin=dict(l=55,r=95,t=75,b=50))
    return figure
