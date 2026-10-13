"""Final validation module linking ALIRIM to the teaching pilot."""

import streamlit as st

from platform_ui import render_project_hero


PILOT_URL = "https://alirim-teaching-pilot.ua-smra.chatgpt.site/"


render_project_hero(
    "Teaching validation",
    "Teaching Pilot and Feedback",
    "Invite lecturers and pipeline-integrity experts to review one short ALIRIM learning activity and indicate whether they would use it for students or early-career learners.",
)

st.markdown(
    """
    ### What this pilot tests

    **Assumption:** Lecturers and subject experts find an interactive pipeline-integrity
    lesson useful enough to consider using it in teaching.

    **What visitors do:** Review the short teaching offer and register their email if
    they want to try it or provide feedback.
    
    """
)

st.link_button(
    "Open the ALIRIM Teaching Pilot",
    PILOT_URL,
    type="primary",
    use_container_width=True,
)

st.caption(
    "The pilot records anonymous page views and stores submitted email addresses for "
    "pilot communication."
)
