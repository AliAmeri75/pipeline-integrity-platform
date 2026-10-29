"""Snapshot CorLAS Monte Carlo with configurable pipe/material distributions."""
from dataclasses import replace
import math
import numpy as np
import pandas as pd
from education.pof_model import corlas_failure_pressure
from reliability_model import validate_features

SHARED = ('diameter_in','wall_thickness_mm','operating_pressure_psi','yield_strength_psi',
          'ultimate_strength_psi','elastic_modulus_gpa','charpy_energy','model_factor')


def positive_samples(rng,mean,std,distribution,size):
    if not np.isfinite([mean,std]).all() or mean<=0 or std<0:
        raise ValueError('Parameter means must be positive and SDs finite and nonnegative.')
    if distribution not in ('Deterministic','Normal','Lognormal','Gumbel'):
        raise ValueError('Unsupported probability distribution: '+str(distribution))
    if distribution=='Deterministic' or std==0:
        return np.full(size,mean,dtype=float)
    def draw(n):
        if distribution=='Normal':
            return rng.normal(mean,std,n)
        if distribution=='Lognormal':
            sigma=math.sqrt(math.log1p((std/mean)**2))
            return rng.lognormal(math.log(mean)-sigma*sigma/2,sigma,n)
        scale=std*math.sqrt(6)/math.pi
        return rng.gumbel(mean-np.euler_gamma*scale,scale,n)
    values=draw(size)
    for _ in range(100):
        bad=(values<=0)|~np.isfinite(values)
        if not bad.any():
            return values
        values[bad]=draw(int(bad.sum()))
    raise ValueError('Too many nonphysical samples; revise the probability inputs.')


def calculate_crack_reliability(features,route,joint_length_m,inputs,uncertainty,samples=1000,seed=7,*,variable_specs=None,section_table=None,specs_by_segment=None):
    data=validate_features(features,route,joint_length_m,section_table)
    if not data.defect_type.eq('Crack').all():
        raise ValueError('CorLAS calculation supports cracks only. Import corrosion Pf instead.')
    if not 100<=samples<=10000:
        raise ValueError('Use 100–10,000 samples.')
    for field in ('depth_mm','length_mm'):
        data[field]=pd.to_numeric(data.get(field),errors='coerce')
        if not np.isfinite(data[field]).all() or (data[field]<=0).any():
            raise ValueError('Positive finite crack depth and length are required.')
    corlas_failure_pressure(inputs)
    specs={name:dict(distribution='Deterministic',mean=float(getattr(inputs,name)),std=0.) for name in SHARED}
    for name,sd in [('wall_thickness_mm',uncertainty.wall_thickness_mm),('operating_pressure_psi',uncertainty.operating_pressure_psi),
                    ('model_factor',uncertainty.model_factor),('flaw_depth_mm',uncertainty.flaw_depth_mm),
                    ('flaw_length_mm',uncertainty.flaw_length_mm)]:
        specs[name]=dict(distribution='Normal',std=float(sd))
        if name in SHARED:
            specs[name]['mean']=float(getattr(inputs,name))
    if variable_specs is not None:
        if set(variable_specs)!=set(specs):
            raise ValueError('Provide distributions for all pipe/material and crack-size parameters.')
        specs={name:dict(spec) for name,spec in variable_specs.items()}
    rng=np.random.default_rng(seed)
    def draw(name,size,mean=None):
        spec=specs[name]
        return positive_samples(rng,float(spec['mean'] if mean is None else mean),float(spec['std']),spec['distribution'],size)
    data['burst_pf'],data['leak_pf']=0.,0.
    data['burst_failures'],data['leak_failures']=0,0
    data['mc_samples']=samples
    joints,section_joints=[],[]
    grouping=['joint_number','section_id'] if specs_by_segment is not None else 'joint_number'
    for group_key,group in data.groupby(grouping,sort=True):
        number=group_key[0] if isinstance(group_key,tuple) else group_key
        if specs_by_segment is not None:
            specs=specs_by_segment[int(group.section_id.iloc[0])]
        shared={name:draw(name,samples) for name in SHARED}
        # Condition on valid strength ordering and a positive pipe bore; no clipping.
        for _ in range(100):
            bad=(shared['yield_strength_psi']>=shared['ultimate_strength_psi'])|(
                2*shared['wall_thickness_mm']>=25.4*shared['diameter_in'])
            if not bad.any():
                break
            for name in SHARED:
                shared[name][bad]=draw(name,int(bad.sum()))
        else:
            raise ValueError('Sampled geometry or strength order is invalid; revise means and uncertainty.')
        joint_burst,joint_leak=np.zeros(samples,dtype=bool),np.zeros(samples,dtype=bool)
        section_masks={}
        for index,row in group.iterrows():
            depths=draw('flaw_depth_mm',samples,float(row.depth_mm))
            lengths=draw('flaw_length_mm',samples,float(row.length_mm))
            leak=depths>=shared['wall_thickness_mm']
            burst=np.zeros(samples,dtype=bool)
            for k in np.flatnonzero(~leak):
                parameters={name:float(values[k]) for name,values in shared.items()}
                case=replace(inputs,**parameters,flaw_depth_mm=float(depths[k]),flaw_length_mm=float(lengths[k]))
                evaluated=corlas_failure_pressure(case)
                resistance=evaluated['failure_pressure_psi']
                if not np.isfinite(resistance) or resistance<=0:
                    raise ValueError(f'Invalid CorLAS resistance for {row.feature_id}; revise geometry/material.')
                burst[k]=evaluated['limit_state_margin_psi']<=0
            data.loc[index,['burst_pf','leak_pf']]=[burst.mean(),leak.mean()]
            data.loc[index,['burst_failures','leak_failures']]=[burst.sum(),leak.sum()]
            joint_burst|=burst
            joint_leak|=leak
            masks=section_masks.setdefault(int(row.section_id),[np.zeros(samples,dtype=bool),np.zeros(samples,dtype=bool)])
            masks[0]|=burst
            masks[1]|=leak
        joints.append(dict(joint_number=int(number),section_id=int(group.section_id.iloc[0]),burst_pf=joint_burst.mean(),leak_pf=joint_leak.mean()))
        for section_id,(b,l) in section_masks.items():
            section_joints.append(dict(section_id=section_id,joint_number=int(number),burst_pf=float(b.mean()),leak_pf=float(l.mean())))
    data.attrs['section_joint_pfs']=section_joints
    data.attrs['variable_specs']=specs
    return data,pd.DataFrame(joints)
