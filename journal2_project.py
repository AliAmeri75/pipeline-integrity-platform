"""Introduction and launcher for the independently deployed Journal 2 app."""

import streamlit as st

from platform_ui import render_external_cta, render_project_hero


render_project_hero(
    "Publication in press",
    "Reliability and Value-of-Information Planning",
    "Prior and pre-posterior lifecycle decisions for a pipe joint containing a population of growing cracks.",
)
render_external_cta(
    "https://pipeline-reliability-voi.streamlit.app/simulation",
    "Open the Reliability and VoI App",
    "Open the simulation directly in a new tab to connect the POF datasets and run the analysis.",
    illustration="voi_ili_calendar.svg",
    illustration_alt="Inline inspection and calendar planning illustration",
)

st.markdown("## What this module does")
st.markdown(
    """
- Represents a population of one to eight growing cracks in one pipe joint.
- Compares prior repair decisions with decisions informed by inspection results.
- Evaluates perfect and imperfect updated probability-of-failure cases.
- Supports reliability policies π1 and π2, consequence costs, inspection cost, and discounting.
- Reports expected lifecycle cost, repair timing, inspection timing, net value of information, and justifiability.
"""
)

st.markdown("## Data connection")
st.markdown(
    """
The independent application reads the large Monte Carlo POF arrays from the approved
public Google Drive folder. A direct upload option is also available. The app reads
data only and does not modify Drive.
"""
)
