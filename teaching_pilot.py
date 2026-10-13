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

    **Decision rule:** After the first 10 unique visitors, **3 or more email
    registrations** supports continuing the pilot. **2 or fewer registrations** means
    the offer or prototype should be revised before more development.
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
    "pilot communication. The registration dashboard is protected for the site owner."
)
