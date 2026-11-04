"""Replaceable geometric dent-strain limit-state screening, not burst/fatigue Pf.

PHMSA Mechanical Damage Final Report (2009), section 7.2.3, equations 2–6,
PDF page 97 (printed page 87):
https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/technical-resources/pipeline/gas-distribution-integrity-management/65991/mechanicaldamagefinalreport.pdf
Curvature radii must follow that reference's signed convention and be measured,
not inferred from depth alone. No pressurization history or re-rounding simulation.
"""
import numpy as np
import pandas as pd
from profile_map import route_length_km
from probabilistic_reliability_model import positive_samples

DENT_COLUMNS=['dent_id','chainage_m','dent_depth_mm','axial_length_mm',
    'circumferential_width_mm','circumferential_radius_mm','axial_radius_mm',
    'associated_crack_or_metal_loss']
MODEL_ID='phmsa_geometric_strain'


def empty_dent_register():
    return pd.DataFrame({'dent_id':pd.Series(dtype=str),
        **{n:pd.Series(dtype=float) for n in DENT_COLUMNS[1:-1]},
        'associated_crack_or_metal_loss':pd.Series(dtype=bool)})


def validate_dents(table,project):
    if not set(DENT_COLUMNS).issubset(table): raise ValueError('Dent register is missing required columns.')
    data=table[DENT_COLUMNS].copy().reset_index(drop=True)
    if data.empty:return data
    if data.dent_id.isna().any() or data.dent_id.astype(str).str.strip().eq('').any() or data.dent_id.duplicated().any():
        raise ValueError('Dent IDs must be present and unique.')
    for name in DENT_COLUMNS[1:-1]:
        data[name]=pd.to_numeric(data[name],errors='coerce')
        if not np.isfinite(data[name]).all():raise ValueError('Complete finite geometry for every dent.')
        if 'radius' in name:
            if data[name].eq(0).any():raise ValueError('Signed curvature radii cannot be zero.')
        elif (data[name]<0).any() or (name!='chainage_m' and data[name].eq(0).any()):
            raise ValueError('Dent dimensions must be positive; chainage must be nonnegative.')
    if (data.chainage_m>route_length_km(project['route'])*1000+1e-6).any():
        raise ValueError('Every dent must lie on the shared route.')
    if data.associated_crack_or_metal_loss.isna().any() or not data.associated_crack_or_metal_loss.isin([True,False]).all():
        raise ValueError('Specify True/False for associated crack or metal loss.')
    return data


def geometric_dent_strain(diameter_mm,wall_mm,depth_mm,length_mm,r1_mm,r2_mm):
    d,t,h,l,r1,r2=np.broadcast_arrays(*[np.asarray(v,dtype=float) for v in
        (diameter_mm,wall_mm,depth_mm,length_mm,r1_mm,r2_mm)])
    if not all(np.isfinite(v).all() for v in (d,t,h,l,r1,r2)) or (
        (d<=2*t)|(t<=0)|(h<=0)|(h>=d/2)|(l<=0)|(r1==0)|(r2==0)).any():
        raise ValueError('Check dent geometry: positive bore, 0 < displacement < radius, L > 0, and nonzero signed radii.')
    e1=.5*t*(2/d-1/r1)
    e2=-.5*t/r2
    e3=.5*(h/l)**2
    inside=np.sqrt(e1*e1-e1*(e2+e3)+(e2+e3)**2)
    outside=np.sqrt(e1*e1+e1*(-e2+e3)+(-e2+e3)**2)
    return np.maximum(inside,outside)


# Replacement engines must return a strain demand compatible with the chosen capacity.
# Burst/fatigue models need their own event definition; do not relabel this output.
DENT_MODELS={MODEL_ID:geometric_dent_strain}


def dent_geometry(project,criterion_percent=6.,model_id=MODEL_ID):
    if not np.isfinite(criterion_percent) or not 0<criterion_percent<100:
        raise ValueError('Strain criterion must lie between 0 and 100%.')
    data=validate_dents(project.get('dent_register',empty_dent_register()),project)
    if data.empty:return data
    segments=project['segments'].sort_values('start_km')
    positions=np.clip(np.searchsorted(segments.start_km,data.chainage_m/1000,side='right')-1,0,len(segments)-1)
    data['section_id']=segments.section_id.to_numpy()[positions]
    data['diameter_mm']=25.4*segments.diameter_in.to_numpy()[positions]
    data['wall_thickness_mm']=segments.wall_thickness_mm.to_numpy()[positions]
    data['depth_percent_od']=100*data.dent_depth_mm/data.diameter_mm
    data['equivalent_strain_percent']=np.nan
    plain=~data.associated_crack_or_metal_loss
    a=data[plain]
    data.loc[plain,'equivalent_strain_percent']=100*DENT_MODELS[model_id](a.diameter_mm,
        a.wall_thickness_mm,a.dent_depth_mm,a.axial_length_mm,a.circumferential_radius_mm,a.axial_radius_mm)
    data['strain_margin_percent']=criterion_percent-data.equivalent_strain_percent
    data['assessment_status']=np.where(~plain,'Combined-defect model required',np.where(
        data.strain_margin_percent<=0,'Strain criterion exceeded — engineering review',
        'Below selected strain criterion — not an acceptance decision'))
    return data


def dent_reliability(project,criterion_percent=6.,cov=0.,capacity_sd_percent=0.,samples=1000,seed=7,model_id=MODEL_ID):
    """P(criterion - strain demand <= 0), not annual, burst or leakage Pf.

    Positive lognormal measurement uncertainty with selected COV. Signs of radii
    are retained. D/WT and strain capacity are shared within joint/property group;
    dent geometry draws independent. Group independence is an explicit approximation.
    """
    if not np.isfinite([cov,capacity_sd_percent]).all() or cov<0 or capacity_sd_percent<0:
        raise ValueError('COV and capacity SD must be finite and nonnegative.')
    if isinstance(samples,bool) or int(samples)!=samples or not 100<=samples<=10000:
        raise ValueError('Use 100–10,000 integer samples.')
    samples=int(samples);data=dent_geometry(project,criterion_percent,model_id)
    if data.empty:raise ValueError('Add dent records in Data Exploration first.')
    if data.associated_crack_or_metal_loss.any():
        raise ValueError('Combined crack/metal-loss dents need an interaction model; no reliability result is calculated.')
    rng=np.random.default_rng(seed)
    count=int(np.ceil(route_length_km(project['route'])*1000/project['joint_length_m']))
    data['joint_number']=np.minimum((data.chainage_m//project['joint_length_m']).astype(int)+1,count)
    data['strain_criterion_probability']=np.nan;data['criterion_failures']=0;data['mc_samples']=samples
    groups=[]
    def draw(mean):
        return np.sign(mean)*positive_samples(rng,abs(mean),abs(mean)*cov,'Lognormal',samples)
    for (joint,sid),group in data.groupby(['joint_number','section_id']):
        diameter=draw(float(group.diameter_mm.iloc[0]));wall=draw(float(group.wall_thickness_mm.iloc[0]))
        capacity=positive_samples(rng,criterion_percent/100,capacity_sd_percent/100,'Normal',samples)
        union=np.zeros(samples,dtype=bool)
        for i,row in group.iterrows():
            strain=DENT_MODELS[model_id](diameter,wall,draw(row.dent_depth_mm),draw(row.axial_length_mm),
                draw(row.circumferential_radius_mm),draw(row.axial_radius_mm))
            event=strain>=capacity;union|=event
            data.loc[i,'strain_criterion_probability']=event.mean()
            data.loc[i,'criterion_failures']=event.sum()
        groups.append(dict(section_id=int(sid),joint_number=int(joint),strain_criterion_probability=float(union.mean())))
    joints=pd.DataFrame(groups)
    sections=project['segments'][['section_id','start_km','end_km']].copy()
    grouped=joints.groupby('section_id').strain_criterion_probability.apply(lambda x:1-np.prod(1-x))
    sections['strain_criterion_probability']=sections.section_id.map(grouped).fillna(0.)
    return data,joints,sections


def dent_shape_figure(row):
    """Idealized displacement illustration only; not measured strain-model geometry."""
    import plotly.graph_objects as go
    x=np.linspace(-1.5*row.axial_length_mm,1.5*row.axial_length_mm,100)
    theta=np.linspace(-np.pi,np.pi,120)
    xx,tt=np.meshgrid(x,theta)
    radius=row.diameter_mm/2
    depth=row.dent_depth_mm*np.exp(-4*np.log(2)*(
        (xx/row.axial_length_mm)**2+(radius*tt/row.circumferential_width_mm)**2))
    rr=radius-depth
    figure=go.Figure(go.Surface(x=xx,y=rr*np.sin(tt),z=rr*np.cos(tt),surfacecolor=depth,
        colorscale='YlOrRd',colorbar=dict(title='Displacement (mm)'),
        hovertemplate='Axial position %{x:.1f} mm<br>Inward displacement %{surfacecolor:.2f} mm<extra></extra>'))
    figure.update_layout(title='Idealized plain dent · '+str(row.dent_id),height=450,
        scene=dict(xaxis_title='Axial position (mm)',yaxis_title='Y (mm)',zaxis_title='Z (mm)',aspectmode='data'),
        template='plotly_white',margin=dict(l=0,r=0,t=60,b=0))
    return figure
