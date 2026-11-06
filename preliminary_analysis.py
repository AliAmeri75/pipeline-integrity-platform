"""Threat workspaces sharing one asset register; no physical interaction model."""
import streamlit as st
from platform_ui import render_project_hero
from project_editor import get_project
from threat_workspaces import threat_project,render_corrosion_workspace,render_dent_workspace

render_project_hero('Maintenance Planning (Cracks/Corrosion/Dents)','Preliminary Analysis',
    'Deterministic condition, reliability and risk by defect type, using one pipeline dataset.')
st.caption('Separate assessments do not evaluate combined crack–corrosion–dent effects. '
    'Do not add the threat probabilities to estimate combined failure probability.')
workspace=st.radio('Defect workspace',['Crack','Corrosion','Dent'],horizontal=True,key='preliminary_threat')
model_names={
    'Crack':'CorLAS-based crack failure-pressure model',
    'Corrosion':'DNV-RP-F101-based nominal isolated metal-loss pressure equation',
    'Dent':'Geometric dent-strain screening — not a rupture-pressure model',
}
st.markdown('**Assessment model: '+model_names[workspace]+'**')
with st.expander('Model inputs, outputs and applicability'):
    if workspace=='Crack':
        st.write('The research implementation compares flow-stress and fracture-toughness failure pressures; '
            'the lower pressure controls. Inputs include crack depth/length, pipe diameter/WT, '
            'strength, elastic modulus and Charpy-based toughness. FPR is nominal predicted failure '
            'pressure divided by operating pressure. Reliability also includes the selected model factor.')
        st.latex(r'P_{\mathrm{failure}}=\min(P_{\mathrm{flow}},P_{\mathrm{toughness}})')
        st.caption('CorLAS is applied to isolated crack inputs here. A crack at a dent or metal-loss feature '
            'is not assessed by simply running this isolated-crack calculation. This is the existing research '
            'implementation, not a claim of certification or equivalence to a commercial software package.')
    elif workspace=='Corrosion':
        st.write('The implemented model is a nominal isolated longitudinal metal-loss equation used in '
            'DNV-RP-F101 literature. It is not ASME B31G or R-STRENG and is not a full DNV code assessment. '
            'Inputs are outside diameter D, WT t, maximum metal-loss depth d, axial length L and UTS.')
        st.latex(r'Q=\sqrt{1+0.31\frac{L^2}{Dt}},\qquad P_{\mathrm{failure}}=\frac{2t\,UTS}{D-t}\frac{1-d/t}{1-(d/t)/Q}')
        st.caption('Internal differential pressure only; isolated longitudinal metal loss, depth ≤85% WT, '
            'without dents or crack-like damage. No partial-factor tables or physical interaction model. '
            'Leakage is assessed separately as sampled depth ≥ sampled WT.')
        st.markdown('[Public equation and applicability](https://equinor.github.io/neqsim/process/mechanical_design/dnv_rp_f101_corroded_pipeline) '
            '· [DNV-RP-F101 publisher scope](https://www.dnv.com/energy/standards-guidelines/dnv-rp-f101-corroded-pipelines/)')
    else:
        st.write('The starting dent model uses the geometric strain equations documented in PHMSA Mechanical '
            'Damage (2009), section 7.2.3. It returns maximum inside/outside equivalent strain. '
            'Monte Carlo estimates the probability of exceeding the selected strain criterion. '
            'It does not calculate rupture pressure, FPR or burst/leakage POF. The separate SCADA & Fatigue tab adds '
            'pressure-cycle damage and time-dependent fatigue reliability (He–Zhou, 2021), with applicability checks.')
        st.caption('Dent–crack and dent–corrosion interactions remain unsupported. The consequence proxy '
            'must describe the strain-criterion event itself, not an assumed rupture or leak.')
with st.expander('Combined defects — available research and next implementation step'):
    st.write('Published models can represent interaction, but the isolated CorLAS/metal-loss equations '
        'must not be reused as a combined-defect model. A numerical interaction engine is not implemented in ALIRIM yet.')
    st.markdown(
        '- **Dent + crack:** extended finite-element fracture models predict crack propagation and burst pressure '
        'for specified geometry and restraint. [Okodi et al., 2020](https://www.mdpi.com/2076-3417/10/21/7554).\n'
        '- **Dent + corrosion:** finite-element pressure-capacity models account for combined defect geometry. '
        '[Huang et al., 2022](https://doi.org/10.1016/j.oceaneng.2022.112875). '
        'Adjacent defects have also been studied by '
        '[Sun et al., 2021](https://doi.org/10.1061/(ASCE)PS.1949-1204.0000570).')
    st.write('To implement one: link the dent and secondary defect IDs; enter relative axial/circumferential '
        'position, orientation, full geometry, material response, restraint and loading history; select '
        'a published model with known applicability; then validate its predictions against reference results. '
        'A validated surrogate could later provide fast calls from the same deterministic/Monte Carlo framework.')
    st.caption('The model must define leakage/rupture events before their consequences can be combined with '
        'probability. Do not add isolated defect probabilities or assume that a dent strain exceedance is a release.')
    st.markdown('[API RP 1183 update notice](https://www.api.org/products-and-services/standards/important-standards-announcements/addendum-1-rp-1183): '
        'API removed the first-edition Table 6 fatigue-screening guidance in Addendum 1. '
        'This app does not implement that removed table.')
project=get_project()
if workspace=='Crack':
    from deterministic_analysis import render_deterministic_analysis
    from reliability_analysis import render_reliability_analysis
    from consequence_assessment import render_consequence_assessment
    selected=threat_project(project,'Crack')
    deterministic,reliability,consequence=st.tabs([
        'Deterministic Analysis','Risk & Reliability','Consequence Assessment'])
    with deterministic:
        if selected['summary'].empty:
            st.info('No cracks in the saved dataset. Add crack profiles in Data Exploration.')
        else: render_deterministic_analysis(project=selected)
    with reliability:
        if not selected['summary'].empty:
            st.caption('Crack contribution only; other threats and physical interactions are not included.')
            render_reliability_analysis(embedded=True,project=selected)
        else: st.info('No crack records available for reliability analysis.')
    with consequence:
        render_consequence_assessment(project['route'],segment_table=project['segments'])
elif workspace=='Corrosion': render_corrosion_workspace(project)
else: render_dent_workspace(project)
