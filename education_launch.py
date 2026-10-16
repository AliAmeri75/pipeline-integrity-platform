"""Launch the independently deployed ALIRIM Education application."""

import streamlit as st

from platform_ui import render_project_hero


EDUCATION_APP_URL = "https://alirim-education.streamlit.app/"

render_project_hero(
    "Standalone learning application",
    "ALIRIM Education",
    "The educational tutorial now has its own application so new learning materials can be added and tested independently.",
)

st.link_button(
    "Open ALIRIM Education",
    EDUCATION_APP_URL,
    type="primary",
    use_container_width=True,
)

st.caption("The education app opens separately from the research platform.")
