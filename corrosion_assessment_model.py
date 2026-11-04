"""Replaceable isolated longitudinal metal-loss pressure screening.

Public equation: https://equinor.github.io/neqsim/process/mechanical_design/dnv_rp_f101_corroded_pipeline
Not a full DNV-RP-F101 assessment: no partial factors, growth, interactions or combined loads.
Units: dimensions mm; strengths/pressures psi. Maximum assessed depth is 85% WT.
"""
import numpy as np
import pandas as pd
from probabilistic_reliability_model import positive_samples

MODEL_ID='isolated_metal_loss'
PARAMETERS=('diameter_in','wall_thickness_mm','operating_pressure_psi',
    'ultimate_strength_psi','flaw_depth_mm','flaw_length_mm','model_factor')


def check_longitudinal_profile(row):
    """Reject a known wider-than-longer feature rather than silently rotating it."""
    width=row.get('Profile width (mm)',np.nan)
    if pd.notna(width) and (not np.isfinite(float(width)) or float(width)>float(row['Profile length (mm)'])):
        raise ValueError('This longitudinal metal-loss model requires circumferential width ≤ axial length.')


def isolated_metal_loss(diameter_mm,wall_mm,depth_mm,length_mm,uts_psi):
    d,t,a,l,u=np.broadcast_arrays(*[np.asarray(v,dtype=float) for v in
        (diameter_mm,wall_mm,depth_mm,length_mm,uts_psi)])
    if not all(np.isfinite(v).all() for v in (d,t,a,l,u)) or (
        (d<=2*t)|(t<=0)|(a<0)|(a/t>.85)|(l<=0)|(u<=0)).any():
        raise ValueError('Model domain: D > 2t, positive WT, length and UTS, and 0 ≤ depth/WT ≤ 0.85.')
    q=np.sqrt(1+.31*l*l/(d*t))
    return 2*t*u/(d-t)*(1-a/t)/(1-a/t/q)


# New resistance functions can be registered here without changing the UI or aggregation.
CORROSION_MODELS={MODEL_ID:isolated_metal_loss}


def deterministic_corrosion(project,model_id=MODEL_ID):
    from assessment_project import segment_inputs
    records=[]
    for _,r in project['summary'].iterrows():
        if r['Defect type'] not in ('Corrosion','Corrosion / metal loss'): continue
        b=segment_inputs(project,int(r['Segment ID']))
        row={'Profile ID':str(r['Profile ID']),'Segment ID':int(r['Segment ID']),
            'Distance from start (km)':float(r['Distance from start (km)']),
            'Depth (mm)':float(r['Maximum depth (mm)']),'Length (mm)':float(r['Profile length (mm)']),
            'Wall thickness (mm)':b.wall_thickness_mm,'Burst resistance pressure (psi)':np.nan,
            'FPR':np.nan,'Status':'Not calculated','Model':model_id}
        try:
            check_longitudinal_profile(r)
            if b.operating_pressure_psi<=0: raise ValueError('Operating pressure must be positive.')
            resistance=float(CORROSION_MODELS[model_id](b.diameter_in*25.4,b.wall_thickness_mm,
                row['Depth (mm)'],row['Length (mm)'],b.ultimate_strength_psi))
            row.update({'Burst resistance pressure (psi)':resistance,'FPR':resistance/b.operating_pressure_psi,
                'Status':'Calculated'})
        except ValueError as error: row['Status']=str(error)
        records.append(row)
    return pd.DataFrame(records)


def corrosion_specs(project):
    from assessment_project import segment_specs
    specs={}
    for sid in project['segments'].section_id:
        rows=segment_specs(project,int(sid))
        specs[int(sid)]={n:dict(rows[n]) for n in PARAMETERS}
        # Never reuse the crack-specific CorLAS bias calibration for metal loss.
        specs[int(sid)]['model_factor']=dict(mean=1.,std=0.,distribution='Deterministic')
    return specs


def corrosion_reliability(project,specs,samples=1000,seed=7,model_id=MODEL_ID):
    """Snapshot mode-event unions, shared joint–segment pipe draws; no interactions."""
    from assessment_project import validate_project
    p=validate_project(project)
    if isinstance(samples,bool) or int(samples)!=samples or not 100<=samples<=10000:
        raise ValueError('Use 100–10,000 integer samples.')
    samples=int(samples);rng=np.random.default_rng(seed)
    features=p['summary']
    if features.empty or not features['Defect type'].isin(['Corrosion','Corrosion / metal loss']).all():
        raise ValueError('Provide corrosion records only; interacting or combined defects are unsupported.')
    records=[];joint_records=[]
    for (joint,sid),group in features.groupby(['Joint number','Segment ID'],sort=True):
        spec=specs[int(sid)]
        def draw(name,mean=None):
            item=spec[name]
            return positive_samples(rng,item['mean'] if mean is None else mean,
                item['std'],item['distribution'],samples)
        diameter=25.4*draw('diameter_in');wall=draw('wall_thickness_mm')
        pressure=draw('operating_pressure_psi');uts=draw('ultimate_strength_psi');factor=draw('model_factor')
        if (diameter<=2*wall).any(): raise ValueError('Nonphysical sampled bore; revise diameter/WT uncertainty.')
        union_burst=np.zeros(samples,dtype=bool);union_leak=union_burst.copy()
        for _,r in group.iterrows():
            check_longitudinal_profile(r)
            depth=draw('flaw_depth_mm',float(r['Maximum depth (mm)']))
            length=draw('flaw_length_mm',float(r['Profile length (mm)']))
            leak=depth>=wall
            unresolved=(~leak)&(depth/wall>.85)
            if unresolved.any():
                raise ValueError(f'{r["Profile ID"]}: {unresolved.sum()}/{samples} draws exceed 85% WT '
                    'without being through-wall. This model cannot assess them; no Pf or risk is reported. '
                    'Use an applicable deeper-defect model or review uncertainty assumptions.')
            burst=np.zeros(samples,dtype=bool);valid=~leak
            burst[valid]=pressure[valid]>=factor[valid]*CORROSION_MODELS[model_id](diameter[valid],wall[valid],
                depth[valid],length[valid],uts[valid])
            records.append(dict(feature_id=str(r['Profile ID']),defect_type='Corrosion',
                chainage_km=float(r['Distance from start (km)']),section_id=int(sid),joint_number=int(joint),
                burst_pf=float(burst.mean()),leak_pf=float(leak.mean()),burst_failures=int(burst.sum()),
                leak_failures=int(leak.sum()),mc_samples=samples,model_id=model_id))
            union_burst|=burst;union_leak|=leak
        joint_records.append(dict(section_id=int(sid),joint_number=int(joint),
            burst_pf=float(union_burst.mean()),leak_pf=float(union_leak.mean())))
    assessed=pd.DataFrame(records);joints=pd.DataFrame(joint_records)
    sections=p['segments'][['section_id','start_km','end_km','burst_consequence','leak_consequence']].copy()
    for mode in ('burst','leak'):
        grouped=joints.groupby('section_id')[mode+'_pf'].apply(lambda x:1-np.prod(1-x))
        sections[mode+'_pf']=sections.section_id.map(grouped).fillna(0.)
        sections[mode+'_risk']=sections[mode+'_pf']*sections[mode+'_consequence']
    sections['total_risk']=sections.burst_risk+sections.leak_risk
    sections['feature_count']=sections.section_id.map(assessed.groupby('section_id').size()).fillna(0).astype(int)
    return assessed,joints,sections
