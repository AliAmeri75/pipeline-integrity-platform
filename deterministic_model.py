"""Independent deterministic resistance/FPR calculations; no Monte Carlo imports."""
from dataclasses import replace
import numpy as np
import pandas as pd
from education.pof_model import POFInputs,corlas_failure_pressure


def analyze_deterministic_profiles(summary: pd.DataFrame,base_inputs: POFInputs) -> pd.DataFrame:
    required = {'Profile ID','Feature ID','Feature location (m)','Maximum depth (mm)',
                'Profile length (mm)','Wall thickness (mm)','Outside diameter (mm)'}
    missing = required-set(summary.columns)
    if missing:
        raise ValueError('The prepared profile table is missing: '+', '.join(sorted(missing)))
    if summary.empty:
        raise ValueError('At least one prepared profile is required.')
    records = []
    for _,row in summary.iterrows():
        record = {
            'Profile ID':str(row['Profile ID']),'Feature ID':str(row['Feature ID']),
            'Feature location (m)':row['Feature location (m)'],
            'Defect depth (mm)':row['Maximum depth (mm)'],
            'Defect length (mm)':row['Profile length (mm)'],
            'Wall thickness (mm)':row['Wall thickness (mm)'],
            'Outside diameter (mm)':row['Outside diameter (mm)'],
            'Burst resistance pressure (psi)':None,'FPR':None,
            'Status':'Not calculated','Defect type':row.get('Defect type','Crack'),
        }
        if record['Defect type']!='Crack':
            record['Status'] = 'Not calculated: a corrosion-specific resistance model is required'
            records.append(record)
            continue
        try:
            depth,length,wall,diameter = [float(row[field]) for field in
                ['Maximum depth (mm)','Profile length (mm)','Wall thickness (mm)','Outside diameter (mm)']]
            if not np.isfinite([depth,length,wall,diameter]).all() or min(depth,length,wall,diameter)<=0:
                raise ValueError('Geometry values must be finite and positive')
            case = replace(base_inputs,diameter_in=diameter/25.4,wall_thickness_mm=wall,
                           flaw_length_mm=length,flaw_depth_mm=depth)
            resistance = corlas_failure_pressure(case)['failure_pressure_psi']
            if not np.isfinite(resistance) or resistance<=0:
                raise ValueError('Resistance calculation returned an invalid value')
            record.update({'Burst resistance pressure (psi)':float(resistance),
                           'FPR':float(resistance)/case.operating_pressure_psi,'Status':'Calculated'})
        except (ValueError,TypeError) as error:
            record['Status'] = str(error)
        records.append(record)
    return pd.DataFrame(records)
