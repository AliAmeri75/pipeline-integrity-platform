#!/usr/bin/env python3
"""Entrypoint for the Pipeline Integrity Research Platform."""

import streamlit as st

from platform_ui import apply_global_style


st.set_page_config(
    page_title="Pipeline Integrity Research Platform",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_global_style()

home = st.Page(
    "home.py",
    title="Platform introduction",
    icon=":material/home:",
    default=True,
)
inspection = st.Page(
    "inspection_project.py",
    title="Fixed inspection scheduling",
    icon=":material/calendar_month:",
    url_path="inspection",
)
rl_planning = st.Page(
    "rl_project.py",
    title="Dynamic RL planning",
    icon=":material/model_training:",
    url_path="rl-planning",
)
journal_two = st.Page(
    "journal2_project.py",
    title="Reliability and VoI",
    icon=":material/monitoring:",
    url_path="reliability-voi",
)

navigation = st.navigation(
    {
        "Platform": [home],
        "Research applications": [inspection, rl_planning, journal_two],
    }
)
navigation.run()
