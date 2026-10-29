"""Standalone, no-intervention reliability screening for mapped defects."""
from dataclasses import replace
import math
import numpy as np
import pandas as pd
from education.pof_model import POFInputs, UncertaintyInputs, corlas_failure_pressure
from profile_map import route_length_km, point_at_chainage


def demo_data():
    origin = (53.6, -114.5)
    offsets = [(0, 0), (.05, .2), (-.03, .4), (.08, .65), (.02, .9), (.15, 1.1), (.12, 1.35)]
    low, high = 0., 3.
    for _ in range(60):
        scale = (low + high) / 2
        route = [[origin[0]+a*scale, origin[1]+b*scale] for a,b in offsets]
        if route_length_km(route) < 100:
            low = scale
        else:
            high = scale
    features = pd.DataFrame(dict(
        feature_id=[f'DEMO-{i+1:03d}' for i in range(12)], defect_type=['Crack']*12,
        chainage_km=[2.001,2.002,8.10,15.30,24.,38.1,51.2,62.401,62.403,76.2,88.8,96.1],
        depth_mm=[.6,1.,2.,3.5,4.5,1.5]*2, length_mm=[20.,40.,80.,140.,200.,60.]*2))
    return route, features


def validate_features(features, route, joint_length_m, section_table=None):
    required = {'feature_id','defect_type','chainage_km'}
    if not required.issubset(features.columns) or features.empty:
        raise ValueError('Provide feature_id, defect_type and chainage_km for at least one feature.')
    data = features.copy().reset_index(drop=True)
    if data.feature_id.isna().any() or data.feature_id.astype(str).str.strip().eq('').any() or data.feature_id.duplicated().any():
        raise ValueError('Feature IDs must be present and unique.')
    if not data.defect_type.isin(['Crack','Corrosion']).all():
        raise ValueError('Defect type must be Crack or Corrosion.')
    length = route_length_km(route)
    if length <= 0 or not math.isfinite(joint_length_m) or joint_length_m <= 0:
        raise ValueError('A positive route length and joint length are required.')
    chainage = pd.to_numeric(data.chainage_km, errors='coerce')
    if not np.isfinite(chainage).all() or not chainage.between(0,length).all():
        raise ValueError(f'Chainages must lie between 0 and {length:.6f} km.')
    data['chainage_km'] = chainage
    count = math.ceil(length*1000/joint_length_m)
    data['joint_number'] = np.minimum(np.floor(chainage*1000/joint_length_m).astype(int)+1,count)
    data['section_id'] = np.minimum(np.floor(chainage).astype(int)+1,math.ceil(length))
    if section_table is not None:
        # The shared project validates continuous coverage before calling here.
        starts = section_table.start_km.to_numpy(dtype=float)
        positions = np.searchsorted(starts, chainage.to_numpy(), side='right')-1
        positions = np.clip(positions, 0, len(section_table)-1)
        data['section_id'] = section_table.section_id.to_numpy()[positions]
    return data


def calculate_crack_reliability(features, route, joint_length_m, inputs, uncertainty, samples=1000, seed=7):
    """Snapshot burst/leak Pf. Shared WT/load draws within each joint.

    No growth, inspections, repair, discounting, or planning calls. Nonpositive
    normal draws are resampled to preserve physical domains, rather than clipping
    deep cracks below WT. Leakage is depth >= WT. Burst is pressure >= CorLAS
    resistance, conditional on a non-through-wall crack. Reported modes are thus
    mutually exclusive per feature, but can coexist for different joint features.
    """
    data = validate_features(features, route, joint_length_m)
    if not data.defect_type.eq('Crack').all():
        raise ValueError('CorLAS calculation supports cracks only. Import corrosion Pf instead.')
    if not 100 <= samples <= 10000:
        raise ValueError('Use 100–10,000 samples.')
    for field in ('depth_mm','length_mm'):
        data[field] = pd.to_numeric(data.get(field), errors='coerce')
        if not np.isfinite(data[field]).all() or (data[field] <= 0).any():
            raise ValueError('Positive finite crack depth and length are required.')
    corlas_failure_pressure(inputs)  # Validate shared material/geometry values.
    rng = np.random.default_rng(seed)
    def positive(mean, sd):
        if not np.isfinite([mean,sd]).all() or mean <= 0 or sd < 0:
            raise ValueError('Means must be positive and SDs finite and nonnegative.')
        values = rng.normal(mean, sd, samples)
        for _ in range(100):
            bad = values <= 0
            if not bad.any():
                return values
            values[bad] = rng.normal(mean, sd, int(bad.sum()))
        raise ValueError('Uncertainty produces too many nonphysical samples; revise the inputs.')
    data['burst_pf'], data['leak_pf'] = 0., 0.
    data['burst_failures'], data['leak_failures'] = 0, 0
    data['mc_samples'] = samples
    joints = []
    section_joints = []
    for number, group in data.groupby('joint_number', sort=True):
        walls = positive(inputs.wall_thickness_mm, uncertainty.wall_thickness_mm)
        pressures = positive(inputs.operating_pressure_psi, uncertainty.operating_pressure_psi)
        factors = positive(inputs.model_factor, uncertainty.model_factor)
        joint_burst, joint_leak = np.zeros(samples,dtype=bool), np.zeros(samples,dtype=bool)
        section_masks = {}
        for index, row in group.iterrows():
            depths = positive(row.depth_mm, uncertainty.flaw_depth_mm)
            lengths = positive(row.length_mm, uncertainty.flaw_length_mm)
            leak = depths >= walls
            burst = np.zeros(samples,dtype=bool)
            for k in np.flatnonzero(~leak):
                case = replace(inputs, flaw_depth_mm=float(depths[k]), flaw_length_mm=float(lengths[k]),
                               wall_thickness_mm=float(walls[k]), operating_pressure_psi=float(pressures[k]),
                               model_factor=float(factors[k]))
                evaluated = corlas_failure_pressure(case)
                resistance = evaluated['failure_pressure_psi']
                if not np.isfinite(resistance) or resistance <= 0:
                    raise ValueError(f'Invalid CorLAS resistance for {row.feature_id}; revise geometry/material.')
                burst[k] = evaluated['limit_state_margin_psi'] <= 0
            data.loc[index,['burst_pf','leak_pf']] = [burst.mean(),leak.mean()]
            data.loc[index,['burst_failures','leak_failures']] = [burst.sum(),leak.sum()]
            joint_burst |= burst
            joint_leak |= leak
            masks = section_masks.setdefault(int(row.section_id),
                [np.zeros(samples,dtype=bool),np.zeros(samples,dtype=bool)])
            masks[0] |= burst
            masks[1] |= leak
        joints.append(dict(joint_number=int(number),burst_pf=joint_burst.mean(),leak_pf=joint_leak.mean()))
        for section_id,(burst_mask,leak_mask) in section_masks.items():
            section_joints.append(dict(section_id=section_id,joint_number=int(number),
                burst_pf=float(burst_mask.mean()),leak_pf=float(leak_mask.mean())))
    data.attrs['section_joint_pfs'] = section_joints
    return data, pd.DataFrame(joints)


def import_feature_reliability(features, route, joint_length_m):
    """Use external Pf, assuming independent features within and across joints."""
    data = validate_features(features, route, joint_length_m)
    for field in ('burst_pf','leak_pf'):
        if field not in data:
            raise ValueError('Imported data require burst_pf and leak_pf columns.')
        data[field] = pd.to_numeric(data[field],errors='coerce')
        if not np.isfinite(data[field]).all() or not data[field].between(0,1).all():
            raise ValueError('Imported Pf values must be finite within [0, 1].')
    records = []
    for number, group in data.groupby('joint_number',sort=True):
        records.append(dict(joint_number=int(number),
            burst_pf=1-np.prod(1-group.burst_pf),leak_pf=1-np.prod(1-group.leak_pf)))
    data.attrs['section_joint_pfs'] = [dict(section_id=int(section),joint_number=int(joint),
        burst_pf=1-np.prod(1-group.burst_pf),leak_pf=1-np.prod(1-group.leak_pf))
        for (section,joint),group in data.groupby(['section_id','joint_number'])]
    return data,pd.DataFrame(records)


def consequence_template(route, sample=False):
    """One row per non-overlapping kilometre; the last section can be shorter."""
    length = route_length_km(route)
    if length <= 0:
        raise ValueError('Route must have positive length.')
    starts = np.arange(math.ceil(length),dtype=float)
    data = pd.DataFrame(dict(section_id=np.arange(1,len(starts)+1),start_km=starts,
        end_km=np.minimum(starts+1,length)))
    data['burst_consequence'] = np.nan
    data['leak_consequence'] = np.nan
    if sample:
        # Illustrative conditional costs only, not estimates for actual locations.
        data['burst_consequence'] = 1000000.*(1+np.mod(data.section_id,5))
        data['leak_consequence'] = 100000.*(1+np.mod(data.section_id,7))
    return data


def fixed_section_risk(route, features, consequences, burst_limit, leak_limit):
    """Fixed sections [0,1), [1,2), ...; feature chainage controls membership.

    A crack is counted once, even if its physical joint crosses a section edge.
    Section joint Pf from the Monte Carlo engine retains within-joint dependence.
    Mode-specific consequences are conditional losses for a section-level event.
    Total expected loss is an additive mode sum, not an any-failure probability.
    """
    if not 0 < burst_limit <= 1 or not 0 < leak_limit <= 1:
        raise ValueError('Pf limits must lie in (0, 1].')
    result = consequence_template(route)
    required = {'section_id','burst_consequence','leak_consequence'}
    if not required.issubset(consequences.columns):
        raise ValueError('Consequence data require section_id, burst_consequence and leak_consequence.')
    provided = consequences.copy()
    for field in required:
        provided[field] = pd.to_numeric(provided[field],errors='coerce')
        if not np.isfinite(provided[field]).all():
            raise ValueError('Consequences and section IDs must be finite numeric values; UNKNOWN cannot be treated as zero.')
    if provided.section_id.duplicated().any() or set(provided.section_id) != set(result.section_id):
        raise ValueError('Provide exactly one consequence row for every section_id in the route template.')
    provided = provided.set_index('section_id').loc[result.section_id].reset_index()
    for field in ('start_km','end_km'):
        if field in provided and not np.allclose(pd.to_numeric(provided[field],errors='coerce'),result[field],atol=1e-7,rtol=0):
            raise ValueError('Consequence start/end distances must match the current route template.')
    for field in ('burst_consequence','leak_consequence'):
        if (provided[field]<0).any():
            raise ValueError('Consequences must be nonnegative.')
        result[field] = provided[field].to_numpy()
    records = features.attrs.get('section_joint_pfs')
    if records is None:
        raise ValueError('Calculate or import feature probabilities again to prepare fixed-section results.')
    section_joints = pd.DataFrame(records)
    for mode in ('burst','leak'):
        grouped = section_joints.groupby('section_id')[f'{mode}_pf'].apply(lambda p: 1-np.prod(1-p))
        result[f'{mode}_pf'] = result.section_id.map(grouped).fillna(0.)
        result[f'{mode}_risk'] = result[f'{mode}_pf']*result[f'{mode}_consequence']
    result['total_risk'] = result.burst_risk+result.leak_risk
    result['feature_count'] = result.section_id.map(features.groupby('section_id').size()).fillna(0).astype(int)
    result['limit_ratio'] = np.maximum(result.burst_pf/burst_limit,result.leak_pf/leak_limit)
    result['pof_category'] = np.where(result.limit_ratio>1,'High',np.where(result.limit_ratio>=.5,'Medium','Low'))
    return result


def sliding_sections(route, features, joint_pfs, joint_length_m, burst_limit, leak_limit):
    """Combine joint survival within sliding 1 km windows; keep terminal window.

    Include intersected joints in full conservatively. Unlisted joints have no
    modeled defects; zero means no included failure mechanism, not proven safety.
    """
    if not 0 < burst_limit <= 1 or not 0 < leak_limit <= 1:
        raise ValueError('Pf limits must lie in (0, 1].')
    length = route_length_km(route)
    count = math.ceil(length*1000/joint_length_m)
    edges = np.minimum(np.arange(count+1)*joint_length_m/1000,length)
    terminal = max(0.,length-1)
    starts = np.unique(np.r_[edges[:-1][edges[:-1] < terminal],terminal])
    ends = np.minimum(starts+1,length)
    left = np.searchsorted(edges,starts+1e-10,side='right')-1
    right = np.searchsorted(edges,ends-1e-10,side='left')
    probabilities = []
    for field in ('burst_pf','leak_pf'):
        values = np.zeros(count)
        values[joint_pfs.joint_number.to_numpy(dtype=int)-1] = joint_pfs[field]
        logs = np.log1p(-np.minimum(values,1-np.finfo(float).eps))
        prefix = np.r_[0,np.cumsum(logs)]
        saturated = np.r_[0,np.cumsum(values==1)]
        p = -np.expm1(prefix[right]-prefix[left])
        p[saturated[right]-saturated[left]>0] = 1
        probabilities.append(np.clip(p,0,1))
    ratio = np.maximum(probabilities[0]/burst_limit,probabilities[1]/leak_limit)
    categories = np.where(ratio>1,'High',np.where(ratio>=.5,'Medium','Low'))
    windows = pd.DataFrame(dict(start_km=starts,end_km=ends,burst_pf=probabilities[0],
        leak_pf=probabilities[1],limit_ratio=ratio,category=categories))
    counts = features.groupby('joint_number').size().to_dict()
    rows = []
    for i in range(count):
        a = np.searchsorted(ends,edges[i]+1e-10,side='right')
        b = np.searchsorted(starts,edges[i+1]-1e-10,side='left')
        selected = a+int(np.argmax(ratio[a:b]))
        rows.append(dict(joint_number=i+1,start_km=edges[i],end_km=edges[i+1],
            features=counts.get(i+1,0),category=categories[selected],
            critical_start_km=starts[selected],critical_end_km=ends[selected],
            window_burst_pf=probabilities[0][selected],window_leak_pf=probabilities[1][selected]))
    return windows,pd.DataFrame(rows)
