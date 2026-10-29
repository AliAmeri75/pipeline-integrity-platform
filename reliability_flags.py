"""User-selected POF screening flags, independent of consequence/risk colours."""
import numpy as np
import pandas as pd
from academic_figures import academic_style,logarithmic_y

ACTION_LABEL='Immediate action!'


def flag_probabilities(table,burst_limit,leak_limit):
    if not all(np.isfinite(v) and 0<v<=1 for v in [burst_limit,leak_limit]):
        raise ValueError('POF screening thresholds must be finite and in (0, 1].')
    data=table.copy()
    burst=pd.to_numeric(data['burst_pf'],errors='coerce')
    leak=pd.to_numeric(data['leak_pf'],errors='coerce')
    data['burst_limit']=burst_limit
    data['leak_limit']=leak_limit
    data['burst_exceeds_limit']=np.isfinite(burst)&burst.between(0,1)&(burst>burst_limit)
    data['leak_exceeds_limit']=np.isfinite(leak)&leak.between(0,1)&(leak>leak_limit)
    data['action_required']=data.burst_exceeds_limit|data.leak_exceeds_limit
    valid=np.isfinite(burst)&np.isfinite(leak)&burst.between(0,1)&leak.between(0,1)
    data['screening_status']=np.where(data.action_required,ACTION_LABEL,
        np.where(valid,'No threshold exceeded','Assessment incomplete'))
    data['screening_reason']=[
        '; '.join(reason for flag,reason in [(b,f'Burst POF > {burst_limit:.6g}'),
            (l,f'Leakage POF > {leak_limit:.6g}')] if flag)
        for b,l in zip(data.burst_exceeds_limit,data.leak_exceeds_limit)]
    return data


def annotate_pof_figure(figure,sections,burst_limit,leak_limit):
    import plotly.graph_objects as go
    flagged=flag_probabilities(sections,burst_limit,leak_limit)
    for mode,limit,color in [('burst',burst_limit,'#dc2626'),('leak',leak_limit,'#b45309')]:
        figure.add_hline(y=limit,line_dash='dash',line_color=color,
            annotation_text=mode.title()+f' limit = {limit:.4g}',
            annotation_position='top right' if mode=='burst' else 'bottom right')
        severe=flagged[flagged[mode+'_exceeds_limit']]
        if severe.empty:
            continue
        figure.add_trace(go.Scatter(x=(severe.start_km+severe.end_km)/2,
            y=severe[mode+'_pf'],mode='markers+text',name=mode.title()+' — '+ACTION_LABEL,
            text=['→ '+ACTION_LABEL]*len(severe),textposition='top center',cliponaxis=False,
            marker=dict(symbol='circle-open',size=24,color=color,line=dict(width=3)),
            textfont=dict(color=color),customdata=severe[['section_id','start_km','end_km','screening_reason']].to_numpy(),
            hovertemplate='Segment %{customdata[0]} (%{customdata[1]:.3f}–%{customdata[2]:.3f} km)'
                '<br>POF %{y:.5g}<br>%{customdata[3]}<extra>'+ACTION_LABEL+'</extra>'))
    return logarithmic_y(academic_style(figure),thresholds=(burst_limit,leak_limit),probability=True)
