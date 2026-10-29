"""One validated asset register for exploration and snapshot assessments.

Measured profile grids are immutable. Segment WT does not silently rescale their
measured depths: imported %WT grids are converted using the workbook's inspection
WT, then retained as absolute measured dimensions for subsequent assessments.
"""
from copy import deepcopy
import hashlib
import numpy as np
import pandas as pd
from education.pof_model import POFInputs, UncertaintyInputs
from profile_data import synthetic_sample_workbook, parse_profile_workbook, summary_for_defect_type
from profile_map import route_length_km, point_at_chainage
from reliability_inputs import DEFAULT_SPECS
from deterministic_model import analyze_deterministic_profiles
from deterministic_flags import flag_profiles
from probabilistic_reliability_model import calculate_crack_reliability

PARAMETERS = tuple(DEFAULT_SPECS)


def sample_route():
    """Fictional bent centreline near Edmonton, trimmed to exactly 10 km."""
    route = [[53.535,-113.585],[53.548,-113.535],[53.557,-113.480],
             [53.567,-113.430],[53.580,-113.360]]
    result=[route[0]]
    for point in route[1:]:
        candidate=result+[point]
        if route_length_km(candidate)>=10:
            result.append(list(point_at_chainage(candidate,10.)))
            # Linear lat/lon interpolation differs slightly from geodesic distance.
            lo,hi=0.,1.
            start=result[-2]
            for _ in range(60):
                fraction=(lo+hi)/2
                end=[start[i]+fraction*(point[i]-start[i]) for i in (0,1)]
                if route_length_km(result[:-1]+[end])<10: lo=fraction
                else: hi=fraction
            result[-1]=end
            return result
        result=candidate
    raise ValueError('Sample route is shorter than requested.')


def default_segments(route, summary, segment_length_km=1.):
    length=route_length_km(route)
    count=int(np.ceil((length-1e-8)/segment_length_km))
    records=[]
    for i in range(count):
        row=dict(section_id=i+1,start_km=i*segment_length_km,
                 end_km=min((i+1)*segment_length_km,length))
        row.update({name:spec['mean'] for name,spec in DEFAULT_SPECS.items() if 'mean' in spec})
        row['diameter_in']=float(summary.iloc[0]['Outside diameter (mm)'])/25.4
        row['wall_thickness_mm']=float(summary.iloc[0]['Wall thickness (mm)'])
        row['maop_psi']=936.
        row['nominal_diameter_in']=row['diameter_in']
        row.update(burst_consequence=np.nan,leak_consequence=np.nan)
        records.append(row)
    table=pd.DataFrame(records)
    # Seed pipe geometry from the measured-profile metadata at each location.
    for _,feature in summary.iterrows():
        distance=float(feature['Feature location (m)'])/1000
        mask=(table.start_km<=distance)&(table.end_km>distance)
        table.loc[mask,'diameter_in']=float(feature['Outside diameter (mm)'])/25.4
        table.loc[mask,'wall_thickness_mm']=float(feature['Wall thickness (mm)'])
        table.loc[mask,'nominal_diameter_in']=float(feature['Outside diameter (mm)'])/25.4
    return table


def default_uncertainties(segments):
    return pd.DataFrame([dict(section_id=int(segment.section_id),parameter=name,
        distribution=spec['distribution'],std=spec['std'])
        for segment in segments.itertuples() for name,spec in DEFAULT_SPECS.items()])


def sample_project():
    content=synthetic_sample_workbook()
    summary,profiles=parse_profile_workbook(content)
    summary=summary_for_defect_type(summary,'Crack')
    summary['Feature location (m)']=[500.,4500.,8500.]
    route=sample_route()
    segments=default_segments(route,summary)
    # Illustrative losses, explicitly identified as invented sample inputs.
    segments['burst_consequence']=1_000_000.
    segments['leak_consequence']=100_000.
    return dict(route=route,summary=summary,profiles=profiles,segments=segments,
        uncertainties=default_uncertainties(segments),joint_length_m=12.,
        consequence_unit='CAD',source='Synthetic 10 km demonstration',workbook=content)


def validate_project(project):
    p=deepcopy(project)
    length=route_length_km(p['route'])
    if not np.isfinite(length) or length<=0: raise ValueError('Define a positive-length pipeline route.')
    if not np.isfinite(p['joint_length_m']) or p['joint_length_m']<=0:
        raise ValueError('Joint length must be positive.')
    segments=p['segments'].copy().sort_values('start_km').reset_index(drop=True)
    required=['section_id','start_km','end_km','maop_psi','nominal_diameter_in']+[n for n,s in DEFAULT_SPECS.items() if 'mean' in s]
    for name in required:
        segments[name]=pd.to_numeric(segments[name],errors='coerce')
    if segments.empty or not np.isfinite(segments[required].to_numpy(dtype=float)).all():
        raise ValueError('Complete every segment boundary and nominal pipe/material/load property.')
    if segments.section_id.duplicated().any() or not (segments.section_id%1==0).all() or (segments.section_id<1).any():
        raise ValueError('Segment IDs must be unique positive integers.')
    segments['section_id']=segments.section_id.astype(int)
    if not np.isclose(segments.start_km.iloc[0],0,atol=1e-7) or not np.isclose(segments.end_km.iloc[-1],length,atol=1e-7):
        raise ValueError('Segments must cover the route from 0 to its full length.')
    if (segments.end_km<=segments.start_km).any() or not np.allclose(
            segments.start_km.iloc[1:],segments.end_km.iloc[:-1],atol=1e-7,rtol=0):
        raise ValueError('Segments must be continuous, non-overlapping and have positive length.')
    if (segments[[n for n,s in DEFAULT_SPECS.items() if 'mean' in s]]<=0).any().any():
        raise ValueError('Nominal pipe, load and material values must be positive.')
    if (segments[['maop_psi','nominal_diameter_in']]<=0).any().any():
        raise ValueError('MAOP and nominal pipe diameter must be positive.')
    for name in ['burst_consequence','leak_consequence']:
        supplied=segments[name].replace('UNKNOWN',np.nan)
        values=pd.to_numeric(supplied,errors='coerce')
        if (supplied.notna() & values.isna()).any() or np.isinf(values).any() or (values.dropna()<0).any():
            raise ValueError('Consequences must be nonnegative finite numbers or blank / UNKNOWN.')
        segments[name]=values
    if segments[['burst_consequence','leak_consequence']].notna().any().any() and not str(p['consequence_unit']).strip():
        raise ValueError('Specify the common consequence unit.')
    if (segments.yield_strength_psi>=segments.ultimate_strength_psi).any() or (
            2*segments.wall_thickness_mm>=25.4*segments.diameter_in).any():
        raise ValueError('Check strength ordering and pipe bore in each segment.')
    summary=p['summary'].copy()
    if summary.empty or summary['Profile ID'].duplicated().any():
        raise ValueError('At least one uniquely identified measured profile is required.')
    chainage=pd.to_numeric(summary['Feature location (m)'],errors='coerce')/1000
    if not np.isfinite(chainage).all() or not chainage.between(0,length+1e-8).all():
        raise ValueError('Every defect chainage must be within the mapped route.')
    if not summary['Defect type'].isin(['Crack','Corrosion / metal loss','Corrosion']).all():
        raise ValueError('Defect type must be Crack or Corrosion / metal loss.')
    for name in ['Maximum depth (mm)','Profile length (mm)']:
        values=pd.to_numeric(summary[name],errors='coerce')
        if not np.isfinite(values).all() or (values<=0).any():
            raise ValueError('Measured defect depth and length must be positive and known.')
    positions=np.clip(np.searchsorted(segments.start_km.to_numpy(),chainage,side='right')-1,0,len(segments)-1)
    summary['Segment ID']=segments.section_id.to_numpy(dtype=int)[positions]
    summary['Distance from start (km)']=chainage
    summary['Joint number']=np.minimum((chainage*1000//p['joint_length_m']).astype(int)+1,
        int(np.ceil(length*1000/p['joint_length_m'])))
    uncertainty=p['uncertainties'].copy()
    uncertainty['std']=pd.to_numeric(uncertainty['std'],errors='coerce')
    expected={(int(s),n) for s in segments.section_id for n in PARAMETERS}
    if uncertainty.duplicated(['section_id','parameter']).any() or set(zip(uncertainty.section_id,uncertainty.parameter))!=expected:
        raise ValueError('Provide exactly one uncertainty row for every parameter in every segment.')
    if not np.isfinite(uncertainty['std']).all() or (uncertainty['std']<0).any() or not uncertainty.distribution.isin(
            ['Deterministic','Normal','Lognormal','Gumbel']).all():
        raise ValueError('Choose a supported distribution and a finite nonnegative SD for each parameter.')
    uncertainty=uncertainty.sort_values(['section_id','parameter']).reset_index(drop=True)
    p.update(segments=segments,summary=summary,uncertainties=uncertainty)
    return p


def project_signature(project):
    # Include measured grid content, not only maximum sizes.
    return hashlib.sha256(repr((project['route'],project['joint_length_m'],
        project['summary'].to_csv(index=False),project['segments'].to_csv(index=False),
        project['uncertainties'].to_csv(index=False),project['consequence_unit'],
        [(name,grid.to_csv()) for name,grid in project['profiles'].items()])).encode()).hexdigest()


def segment_inputs(project, segment_id):
    segment=project['segments'].set_index('section_id').loc[segment_id]
    return POFInputs(**{n:float(segment[n]) for n,s in DEFAULT_SPECS.items() if 'mean' in s},
        flaw_depth_mm=min(1.,float(segment.wall_thickness_mm)/2))


def assessment_geometry(project):
    """Adapt %WT display grids to assessment WT without changing measured mm."""
    summary=project['summary'].copy()
    profiles={}
    for index,row in summary.iterrows():
        base=segment_inputs(project,row['Segment ID'])
        grid=project['profiles'][str(row['Profile ID'])].copy()
        if 'Depth (%WT)' in grid:
            grid['Depth (%WT)']=grid['Depth (%WT)']*float(row['Wall thickness (mm)'])/base.wall_thickness_mm
        profiles[str(row['Profile ID'])]=grid
        summary.loc[index,'Wall thickness (mm)']=base.wall_thickness_mm
        summary.loc[index,'Outside diameter (mm)']=base.diameter_in*25.4
    return summary,profiles


def segment_specs(project, segment_id):
    inputs=segment_inputs(project,segment_id)
    result={}
    for row in project['uncertainties'].query('section_id == @segment_id').itertuples():
        spec=dict(distribution=row.distribution,std=0. if row.distribution=='Deterministic' else float(row.std))
        if row.parameter not in ['flaw_depth_mm','flaw_length_mm']:
            spec['mean']=getattr(inputs,row.parameter)
        result[row.parameter]=spec
    return result


def deterministic_project(project):
    p=validate_project(project)
    records=[]
    for _,row in p['summary'].iterrows():
        base=segment_inputs(p,row['Segment ID'])
        feature=row.to_frame().T.copy()
        feature['Wall thickness (mm)']=base.wall_thickness_mm
        feature['Outside diameter (mm)']=25.4*base.diameter_in
        result=analyze_deterministic_profiles(feature,base)
        result['Segment ID']=int(row['Segment ID'])
        result['Joint number']=int(row['Joint number'])
        result['Distance from start (km)']=row['Distance from start (km)']
        result['Operating pressure (psi)']=base.operating_pressure_psi
        records.extend(result.to_dict('records'))
    return flag_profiles(pd.DataFrame(records))


def reliability_project(project,samples=1000,seed=7):
    p=validate_project(project)
    summary=p['summary']
    features=pd.DataFrame(dict(feature_id=summary['Profile ID'],
        defect_type=summary['Defect type'].replace({'Corrosion / metal loss':'Corrosion'}),
        chainage_km=summary['Distance from start (km)'],depth_mm=summary['Maximum depth (mm)'],
        length_mm=summary['Profile length (mm)']))
    # Do not discard corrosion defects or substitute crack probabilities.
    if not features.defect_type.eq('Crack').all():
        raise ValueError('Corrosion reliability is unavailable: select and validate a corrosion-specific model before assessing this project.')
    specs={int(s):segment_specs(p,int(s)) for s in p['segments'].section_id}
    assessed,joints=calculate_crack_reliability(features,p['route'],p['joint_length_m'],
        segment_inputs(p,int(p['segments'].section_id.iloc[0])),UncertaintyInputs(),samples,seed,
        section_table=p['segments'],specs_by_segment=specs)
    sections=p['segments'][['section_id','start_km','end_km','burst_consequence','leak_consequence']].copy()
    joint_sections=pd.DataFrame(assessed.attrs['section_joint_pfs'])
    for mode in ['burst','leak']:
        probability=joint_sections.groupby('section_id')[mode+'_pf'].apply(lambda x:1-np.prod(1-x))
        sections[mode+'_pf']=sections.section_id.map(probability).fillna(0.)
        consequence=pd.to_numeric(sections[mode+'_consequence'],errors='coerce')
        if (consequence.dropna()<0).any() or np.isinf(consequence).any():
            raise ValueError('Consequences must be nonnegative finite values or UNKNOWN.')
        sections[mode+'_consequence']=consequence
        sections[mode+'_risk']=sections[mode+'_pf']*consequence
    sections['total_risk']=sections.burst_risk+sections.leak_risk
    sections['feature_count']=sections.section_id.map(assessed.groupby('section_id').size()).fillna(0).astype(int)
    return assessed,joints,sections
