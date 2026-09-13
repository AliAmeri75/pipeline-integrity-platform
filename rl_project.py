"""Introduction and launcher for RL-based dynamic planning."""

import streamlit as st

from platform_ui import render_external_cta, render_project_hero


render_project_hero(
    "Risk-informed dynamic decision support",
    "Dynamic Inspection and Maintenance Planning using RL",
    "Train and test state-dependent policies for a single cracked pipe joint using reinforcement learning.",
)
render_external_cta(
    "https://pipeline-rl-planning.streamlit.app/",
    "Open the Reinforcement-Learning Planning App",
    "Open the complete application in a new tab to choose Scenario I or II, train the policy, and inspect the results.",
    illustration="rl_ili_calendar_ai.svg",
    illustration_alt="Inline inspection, calendar, and AI planning illustration",
    feature_icon="ai",
)

st.markdown("## Planning scenarios")
left, right = st.columns(2)
with left:
    st.markdown("### Scenario I — maintenance planning")
    st.markdown(
        "Select the best current maintenance action for every risk, age, and growth state. "
        "Decisions are evaluated annually over the planning horizon."
    )
with right:
    st.markdown("### Scenario II — inspection and maintenance")
    st.markdown(
        "Jointly select the best current repair action and the next inspection interval "
        "for every state."
    )

st.markdown("## Principal inputs and outputs")
st.markdown(
    """
Users can define the initial crack dimensions, SCC and Paris-law growth parameters,
pipe geometry and material properties, repair costs and effectiveness, and leak/burst
failure consequences. The output includes the paper-style policy matrix, full
state-by-state policy, expected failures, repairs, inspections, lifecycle cost,
annual cost, lifetime, and learning diagnostics.
"""
)
st.link_button(
    "View the published study",
    "https://doi.org/10.1016/j.ress.2026.113466",
    width="stretch",
)
