"""Read-only handoff from the saved asset register to fixed-interval planning.

This adapter retains feature IDs and physical joint numbers. It never publishes
an editor draft, changes measured profiles, or invents corrosion/dent crack data.
"""
from copy import deepcopy
import math

import numpy as np
import pandas as pd

from assessment_project import validate_project, project_signature, segment_specs
from profile_map import route_length_km


PROPERTY_MAP = {
    'diameter_in': 'OD', 'wall_thickness_mm': 'WT',
    'operating_pressure_psi': 'Pservice', 'yield_strength_psi': 'SMYS',
    'ultimate_strength_psi': 'SMTS', 'elastic_modulus_gpa': 'E',
    'charpy_energy': 'CVN', 'model_factor': 'err',
}


def planning_handoff(project):
    """Validate a snapshot and return all joints, including initially clean ones.

    A joint that straddles property zones is ambiguous: this first integration
    requires the zones to have identical planning properties at that boundary.
    It does not split one physical joint into two statistical joints.
    """
    p = validate_project(project)
    if not p['summary']['Defect type'].eq('Crack').all() or (
        'dent_register' in p and not p['dent_register'].empty
    ):
        raise ValueError('This inspection planner currently supports cracks only. '
            'Corrosion and dent planning models are not connected yet. '
            'Use a crack-only saved dataset; no defects have been discarded.')
    length = route_length_km(p['route'])
    joint_length = float(p['joint_length_m'])
    count = int(math.ceil(length * 1000 / joint_length - 1e-9))
    segments = p['segments'].set_index('section_id', drop=False)
    specs = {int(i): segment_specs(p, int(i)) for i in segments.index}

    def context(segment_id):
        segment = segments.loc[segment_id]
        properties = {target: deepcopy(specs[segment_id][source])
                      for source, target in PROPERTY_MAP.items()}
        costs = {target: float(segment[source]) / 1e6
                 for source, target in [('burst_consequence', 'Cf_burst'),
                                        ('leak_consequence', 'Cf_leak')]
                 if pd.notna(segment[source])}
        return dict(properties=properties, costs=costs, use_nominal_repair=True,
                    maop_psi=float(segment.maop_psi))

    contexts = {int(i): context(int(i)) for i in segments.index}
    ordered = p['segments']
    for previous, current in zip(ordered.itertuples(), ordered.iloc[1:].itertuples()):
        boundary = float(current.start_km) * 1000 / joint_length
        if not np.isclose(boundary, round(boundary), atol=1e-7, rtol=0):
            # Size uncertainty belongs to the crack's section, too.
            same = (contexts[previous.section_id] == contexts[current.section_id]
                    and specs[previous.section_id] == specs[current.section_id])
            if not same:
                raise ValueError(f'Segment boundary at {current.start_km:g} km cuts a '
                    f'{joint_length:g} m physical joint with different properties, '
                    'uncertainties or consequences. Align that boundary with a joint '
                    'boundary, or use consistent inputs across this joint. '
                    'The planner will not split or average it silently.')

    # Half-open joints [start, end), with the final route endpoint in the last.
    midpoint = (np.arange(count) * joint_length +
                np.minimum((np.arange(count) + 1) * joint_length, length * 1000)) / 2000
    positions = np.searchsorted(ordered.start_km.to_numpy(), midpoint, side='right') - 1
    section_ids = ordered.section_id.to_numpy()[positions]
    cracked = {int(n): group for n, group in p['summary'].groupby('Joint number', sort=True)}
    joints, rows = [], []
    for number, defects in cracked.items():
        section = int(defects.iloc[0]['Segment ID'])
        spec = specs[section]
        cracks = []
        for _, feature in defects.iterrows():
            cracks.append(dict(feature_id=str(feature['Feature ID']),
                profile_id=str(feature['Profile ID']),
                chainage_m=float(feature['Feature location (m)']),
                mean_length=float(feature['Profile length (mm)']),
                mean_depth=float(feature['Maximum depth (mm)']),
                length_distribution=spec['flaw_length_mm']['distribution'],
                length_std=spec['flaw_length_mm']['std'],
                depth_distribution=spec['flaw_depth_mm']['distribution'],
                depth_std=spec['flaw_depth_mm']['std']))
        joint = dict(name=f'Joint {number}', count=1, cracks=cracks,
                     section_id=section, joint_number=number, **deepcopy(contexts[section]))
        joints.append(joint)
        for crack in cracks:
            rows.append({'Profile ID': crack['profile_id'], 'Feature ID': crack['feature_id'],
                'Joint number': number, 'Segment ID': section,
                'Distance from start (m)': crack['chainage_m'],
                'Maximum depth (mm)': crack['mean_depth'],
                'Profile length (mm)': crack['mean_length']})
    # Counted clean groups preserve each segment's input population and include
    # the final partial joint. No row is created for every kilometre of pipe.
    for section in ordered.section_id.astype(int):
        clean = [i + 1 for i, owner in enumerate(section_ids)
                 if owner == section and i + 1 not in cracked]
        if clean:
            joints.append(dict(name=f'Initially crack-free · Segment {section}',
                count=len(clean), cracks=[], section_id=section,
                **deepcopy(contexts[section])))
    if not joints:
        raise ValueError('The saved route contains no pipe joints.')
    register = pd.DataFrame(rows)
    preview = pd.DataFrame([{
        'Joint / group': j['name'], 'Segment ID': j['section_id'], 'Count': j['count'],
        'Initial cracks per joint': len(j['cracks']),
        'Outside diameter (in)': j['properties']['OD']['mean'],
        'Wall thickness (mm)': j['properties']['WT']['mean'],
        'Operating pressure (psi)': j['properties']['Pservice']['mean'],
    } for j in joints])
    return dict(project=p, dataset_id=project_signature(p), joints=joints,
        defect_register=register, preview=preview, pipeline_length_km=length,
        total_joints=count, cracked_joints=len(cracked),
        initial_cracks=len(p['summary']), consequence_unit=p['consequence_unit'])


def planning_joints(handoff, growth, birth_rate, *, use_segment_costs=False):
    """Add planning-only settings to a private copy of the shared input snapshot."""
    joints = deepcopy(handoff['joints'])
    for joint in joints:
        joint['properties'].update(deepcopy(growth))
        joint['birth_rate'] = float(birth_rate)
        # Preliminary Analysis losses describe a segment event. The planning
        # engine instead sums individual joint failure events over time. Reuse
        # those losses only after the user explicitly accepts this interpretation.
        if not use_segment_costs:
            joint.pop('costs', None)
    return joints
