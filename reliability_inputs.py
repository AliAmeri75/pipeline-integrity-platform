"""POF parameter dashboard; defaults mirror the fixed-inspection research model."""
import streamlit as st

DISTRIBUTIONS = ['Deterministic','Normal','Lognormal','Gumbel']
# Synced from pipeline-inspection-app/Simp_Sys_Thresh_J3_optimized.py constants.
# Diameter is fixed there; no diameter SD is inferred.
DEFAULT_SPECS = {
    'diameter_in':dict(distribution='Deterministic',mean=20.,std=0.),
    'wall_thickness_mm':dict(distribution='Normal',mean=6.35,std=.6),
    'operating_pressure_psi':dict(distribution='Gumbel',mean=936.,std=.02*1.07*936.),
    'yield_strength_psi':dict(distribution='Normal',mean=1.1*52000,std=.035*1.1*52000),
    'ultimate_strength_psi':dict(distribution='Normal',mean=1.12*66000,std=.035*1.12*66000),
    'elastic_modulus_gpa':dict(distribution='Normal',mean=210.,std=.04*210.),
    'charpy_energy':dict(distribution='Lognormal',mean=85.,std=.0223*85.**1.46),
    'model_factor':dict(distribution='Normal',mean=1.27,std=.21),
    'flaw_depth_mm':dict(distribution='Normal',std=.74),
    'flaw_length_mm':dict(distribution='Normal',std=15.6),
}
LABELS = {
    'diameter_in':'Outside diameter (in)','wall_thickness_mm':'Wall thickness (mm)',
    'operating_pressure_psi':'Operating pressure (psi)','yield_strength_psi':'Yield strength (psi)',
    'ultimate_strength_psi':'Ultimate strength (psi)','elastic_modulus_gpa':'Elastic modulus (GPa)',
    'charpy_energy':'Charpy energy (model units)','model_factor':'Model factor θ',
    'flaw_depth_mm':'Crack depth (mm)','flaw_length_mm':'Crack length (mm)',
}


def render_reliability_inputs():
    specs = {}
    for name,default in DEFAULT_SPECS.items():
        for field,value in default.items():
            st.session_state.setdefault(f'pof_{name}_{field}',value)
    st.session_state.setdefault('pof_samples',1000)
    st.session_state.setdefault('pof_seed',7)
    with st.sidebar:
        st.markdown('### Risk & Reliability Inputs')
        st.caption('Starting values match the fixed-inspection model. These are research defaults, not pipeline-specific calibration.')
        if st.button('Reset POF inputs to fixed-inspection defaults'):
            for name,default in DEFAULT_SPECS.items():
                for field,value in default.items():
                    st.session_state[f'pof_{name}_{field}'] = value
            st.session_state.pof_samples=1000
            st.session_state.pof_seed=7
        groups = [
            ('Pipe Geometry',['diameter_in','wall_thickness_mm']),
            ('Operating Pressure',['operating_pressure_psi']),
            ('Material Properties',['yield_strength_psi','ultimate_strength_psi','elastic_modulus_gpa','charpy_energy']),
            ('Resistance Model Uncertainty',['model_factor']),
            ('Crack Sizing',['flaw_depth_mm','flaw_length_mm']),
        ]
        for title,names in groups:
            with st.expander(title,expanded=title=='Pipe Geometry'):
                for name in names:
                    default = DEFAULT_SPECS[name]
                    with st.container(border=True):
                        st.markdown('**'+LABELS[name]+'**')
                        distribution = st.selectbox('Distribution',DISTRIBUTIONS,
                            index=None,key=f'pof_{name}_distribution')
                        spec = dict(distribution=distribution)
                        if 'mean' in default:
                            spec['mean'] = st.number_input('Mean / deterministic value',min_value=.000001,
                                value=None,format='%.6g',key=f'pof_{name}_mean')
                        else:
                            st.caption('Mean for each crack comes from its depth/length in the defect table.')
                        sd = st.number_input('Standard deviation',min_value=0.,value=None,
                            format='%.6g',disabled=distribution=='Deterministic',key=f'pof_{name}_std')
                        spec['std'] = 0. if distribution=='Deterministic' else sd
                        specs[name] = spec
        with st.expander('POF Simulation',expanded=False):
            samples = st.number_input('Samples per feature',min_value=100,max_value=10000,value=None,step=100,key='pof_samples')
            seed = st.number_input('Random seed',min_value=0,max_value=1000000,value=None,key='pof_seed')
        st.caption('Pipe/material/load draws are shared by cracks within a joint. Crack dimensions are independent. '
                   'Different joints are treated as independent. No growth, initiation or inspection model is added here.')
    return specs,samples,seed
