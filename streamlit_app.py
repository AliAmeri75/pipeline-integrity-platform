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

INSPECTION_APP_URL = (
    "https://pipeline-inspection-appgit-qjifsvi4zeuyuchaueiuwm.streamlit.app/"
)

home = st.Page(
    "home.py",
    title="ALIRIM introduction",
    icon=":material/home:",
    default=True,
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
publications = st.Page(
    "publications_team.py",
    title="Publications, documentation and team",
    icon=":material/library_books:",
    url_path="publications-team",
)

navigation = st.navigation(
    {
        "ALIRIM": [home],
        "Research applications": [rl_planning, journal_two],
        "Research resources": [publications],
    }
)
st.sidebar.markdown("#### Standalone application")
st.sidebar.page_link(
    INSPECTION_APP_URL,
    label="Fixed inspection scheduling ↗",
    icon=":material/calendar_month:",
    help="Open the inspection scheduling introduction and application in a new tab.",
    width="stretch",
)
navigation.run()
