#!/usr/bin/env python3
"""Entrypoint for ALIRIM."""

import streamlit as st

from platform_ui import apply_global_style


st.set_page_config(
    page_title="ALIRIM | Risk & Integrity Management",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_global_style()

home = st.Page(
    "home.py",
    title="ALIRIM introduction",
    icon=":material/home:",
    default=True,
)
education = st.Page(
    "education_launch.py",
    title="Educational Module",
    icon=":material/school:",
    url_path="education",
)
data_integration = st.Page(
    "data_integration.py",
    title="Data Preparation Module",
    icon=":material/table_view:",
    url_path="data-integration",
)
pipeline_design = st.Page(
    "pipeline_design.py",
    title="Pipeline Design",
    icon=":material/architecture:",
    url_path="pipeline-design",
)
inspection = st.Page(
    "inspection_project.py",
    title="Static Multiple Inspection and Excavation Planning",
    icon=":material/calendar_month:",
    url_path="inspection",
)
rl_planning = st.Page(
    "rl_project.py",
    title="Dynamic Inspection and Maintenance Planning",
    icon=":material/model_training:",
    url_path="rl-planning",
)
journal_two = st.Page(
    "journal2_project.py",
    title="Static Single Delayed Inspection Planning",
    icon=":material/monitoring:",
    url_path="reliability-voi",
)
geohazard_planning = st.Page(
    "geohazard_planning.py",
    title="Planning for Geohazards",
    icon=":material/landscape:",
    url_path="geohazard-planning",
)
publications = st.Page(
    "publications_team.py",
    title="Publications, documentation and team",
    icon=":material/library_books:",
    url_path="publications-team",
)
teaching_pilot = st.Page(
    "teaching_pilot.py",
    title="Teaching Pilot and Feedback",
    icon=":material/feedback:",
    url_path="teaching-pilot",
)

navigation = st.navigation(
    {
        "ALIRIM": [home],
        "Learning Path": [education],
        "Data Preparation": [data_integration],
        "Pipe Design": [pipeline_design],
        "Maintenance Planning (Cracks/Corrosion)": [inspection, rl_planning, journal_two],
        "Maintenance Planning (Geohazards)": [geohazard_planning],
        "Research Resources": [publications],
        "Participate": [teaching_pilot],
    }
)
navigation.run()
