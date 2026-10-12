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
inspection = st.Page(
    "inspection_project.py",
    title="Multiple Inspection and Excavation",
    icon=":material/calendar_month:",
    url_path="inspection",
)
rl_planning = st.Page(
    "rl_project.py",
    title="Dynamic Inspection and Maintenance Scheduling",
    icon=":material/model_training:",
    url_path="rl-planning",
)
journal_two = st.Page(
    "journal2_project.py",
    title="Single Delayed Inspection",
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
        "Learning path": [education],
        "Research applications": [inspection, rl_planning, journal_two],
        "Research resources": [publications],
    }
)
navigation.run()
