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
