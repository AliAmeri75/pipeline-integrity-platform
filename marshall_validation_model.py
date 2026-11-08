"""Published calculation reproduction; NOT a retrospective prediction of failure.

NTSB DCA10MP007, Attachment I Table I (40369111). Rectangular external
flaw scenarios combine corrosion/crack depth as tabulated by Enbridge at NTSB's
request. Keep source inputs separate from analyst assumptions and app outputs.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from education.pof_model import POFInputs,corlas_failure_pressure,GPA_TO_PSI

TABLE_I_URL=("https://data.ntsb.gov/Docket/Document/docBLOB?FileExtension=.PDF&"
    "FileName=IMP%20Attachment%20I%20-%20Table%20I%3A%20Fitness%20for%20service%20calculations%20performed%20by%20Enbridge%20at%20NTSB%27s%20request%20using%20Corrosion%2C%20crack%20and%20tool%20tolerance%20data-Master.PDF&ID=40369111")
TABLE_II_URL=("https://data.ntsb.gov/Docket/Document/docBLOB?FileExtension=.PDF&FileName="
    "IMP+Attachment+-+Table+II%3A+2004+to+2009+Metal+Loss+with+cracking_PII+e+mail_5_14_2012-Master.PDF&ID=40369915")
REPORT_URL='https://www.ntsb.gov/investigations/AccidentReports/Reports/PAR1201.pdf'
PUBLISHED_CONSTANTS={'diameter_in':30.,'ultimate_strength_psi':66000.,'flow_stress_psi':59000.,
    'charpy_ft_lbf':20.,'mop_psi':624.,'reference_pressure_psi':780.,'flaw_shape':'Rectangular','flaw_location':'External'}


def load_marshall():
    return pd.read_csv(Path(__file__).parent/'samples'/'validation'/'marshall_ntsb_table_i.csv',keep_default_na=False)


def compare_marshall(elastic_modulus_psi=30_000_000.,yield_strength_psi=52000.,tolerance_percent=1.):
    """Unfactored pressure vs published rounded values, both ellipse and rectangle.

    SMYS52000: NTSB finalreport p1 footnote4; using it as model yield is an
    assumption, not measured yield. E30Mpsi: analyst assumption not in TableI.
    Flow59000 fixed from TableI regardless of yield assumption. No target fitting.
    """
    if not np.isfinite([elastic_modulus_psi,yield_strength_psi,tolerance_percent]).all() or elastic_modulus_psi<=0 or not 0<yield_strength_psi<66000 or not 0<tolerance_percent<=100:
        raise ValueError('Check positive modulus, yield <66000psi and comparison tolerance (0–100%].')
    table=load_marshall();rows=[]
    for _,row in table.iterrows():
        p=POFInputs(diameter_in=30.,wall_thickness_mm=row.wall_thickness_in*25.4,
            flaw_length_mm=row.corlas_length_in*25.4,flaw_depth_mm=row.effective_depth_in*25.4,
            yield_strength_psi=yield_strength_psi,ultimate_strength_psi=66000.,
            elastic_modulus_gpa=elastic_modulus_psi/GPA_TO_PSI,charpy_energy=20.,
            operating_pressure_psi=624.,model_factor=1.,safety_factor=1.)
        ellipse=corlas_failure_pressure(p) # existing app default; original yield-average flow rule
        rect=corlas_failure_pressure(p,flaw_shape='Rectangular',flow_stress_psi=59000.)
        value=rect['failure_pressure_psi'];reference=row.ntsb_failure_pressure_psi
        rows.append(dict(**row.to_dict(),alirim_rectangular_psi=value,
            alirim_elliptical_psi=ellipse['failure_pressure_psi'],
            rectangular_flow_psi=rect['flow_pressure_psi'],rectangular_toughness_psi=rect['toughness_pressure_psi'],
            controlling_check='Flow stress' if rect['flow_pressure_psi']<=rect['toughness_pressure_psi'] else 'Fracture toughness',
            difference_psi=value-reference,difference_percent=100*(value-reference)/reference,
            elliptical_difference_percent=100*(ellipse['failure_pressure_psi']-reference)/reference,
            comparison_status='Within selected tolerance' if abs(100*(value-reference)/reference)<=tolerance_percent else 'Outside selected tolerance',
            alirim_fpr_at_mop=value/624.,ntsb_fpr_at_mop=reference/624.,
            below_1_25_mop_alirim=value<780.,below_1_25_mop_ntsb=reference<780.))
    return pd.DataFrame(rows)
