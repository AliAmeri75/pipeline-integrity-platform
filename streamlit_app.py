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
    "education/tutorial.py",
    title="Educational tutorial",
    icon=":material/school:",
    url_path="education",
)
data_integration = st.Page(
    "data_integration.py",
    title="Data Integration",
    icon=":material/table_view:",
    url_path="data-integration",
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
publications = st.Page(
    "publications_team.py",
    title="Publications, documentation and team",
    icon=":material/library_books:",
    url_path="publications-team",
)

navigation = st.navigation(
    {
        "ALIRIM": [home],
        "Data preparation": [data_integration],
        "Learning path": [education],
        "Research applications": [inspection, rl_planning, journal_two],
        "Research resources": [publications],
    }
)
navigation.run()
