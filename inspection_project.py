"""Introduction and launcher for fixed inspection scheduling."""

import streamlit as st

from platform_ui import render_external_cta, render_project_hero


render_project_hero(
    "Journal Papers 3 and 5",
    "Fixed Inspection Scheduling",
    "Reliability- and risk-informed comparison of equidistant inspection intervals for multiple pipe joints.",
)
render_external_cta(
    "https://pipeline-inspection-appgit-qjifsvi4zeuyuchaueiuwm.streamlit.app/",
    "Open the Inspection Scheduling App",
    "Continue in this browser tab to define joints, intervals, costs, and reliability assumptions.",
)

st.markdown("## What this module does")
st.markdown(
    """
- Represents multiple pipe joints, including statistically identical joint groups.
- Supports one or more initial cracks and initially crack-free joints.
- Models uncertain crack initiation, crack growth, inspection detection, sizing error, and repair.
- Compares candidate fixed intervals using expected lifecycle cost and leak/burst criteria.
- Provides tables, figures, and downloadable results for reporting and sensitivity analysis.
"""
)
st.link_button(
    "View source code on GitHub",
    "https://github.com/AliAmeri75/pipeline-inspection-app",
    width="stretch",
)
