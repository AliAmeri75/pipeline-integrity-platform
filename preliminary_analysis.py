"""Preliminary analysis workspaces: deterministic FPR, reliability/risk and consequences."""
import streamlit as st
from platform_ui import render_project_hero
from deterministic_analysis import render_deterministic_analysis
from reliability_analysis import render_reliability_analysis
from consequence_assessment import render_consequence_assessment
from project_editor import get_project

render_project_hero(
    'Maintenance Planning (Cracks/Corrosion)',
    'Preliminary Analysis',
    'Inspect deterministic defect resistance, assess reliability and risk, and estimate consequences in one workspace.',
)
deterministic, reliability, consequence = st.tabs([
    'Deterministic Analysis', 'Risk & Reliability', 'Consequence Assessment'
])
with deterministic:
    render_deterministic_analysis()
with reliability:
    render_reliability_analysis(embedded=True)
with consequence:
    project=get_project()
    render_consequence_assessment(project['route'],segment_table=project['segments'])
