"""Introduction page for the unified research platform."""

import streamlit as st

from platform_ui import editable_markdown, render_platform_hero, render_team


render_platform_hero()
render_team()

st.markdown('<div class="section-label">Research overview</div>', unsafe_allow_html=True)
st.markdown(
    editable_markdown(
        "PLATFORM_ABSTRACT.md",
        "Add the platform abstract in `content/PLATFORM_ABSTRACT.md`.",
    )
)

st.markdown('<div class="section-label">Research applications</div>', unsafe_allow_html=True)
st.markdown(
    """
    <section class="app-grid" aria-label="Research applications">
      <a class="app-card"
         href="https://pipeline-inspection-appgit-qjifsvi4zeuyuchaueiuwm.streamlit.app/"
         target="_blank" rel="noopener noreferrer">
        <span class="app-number">I</span>
        <h3>Fixed Inspection Scheduling</h3>
        <p>Compare candidate inspection intervals for multiple pipe joints using
        Monte Carlo deterioration, reliability criteria, repair actions, and lifecycle costs.</p>
        <span class="app-link">Open standalone introduction and application ↗</span>
      </a>
      <a class="app-card" href="rl-planning" target="_self">
        <span class="app-number">II</span>
        <h3>Dynamic RL Planning</h3>
        <p>Train optimal maintenance-only or joint inspection-and-maintenance policies
        for a cracked pipe joint using reinforcement learning.</p>
        <span class="app-link">Journal Paper 4 →</span>
      </a>
      <a class="app-card" href="reliability-voi" target="_self">
        <span class="app-number">III</span>
        <h3>Reliability and Value of Information</h3>
        <p>Evaluate prior and pre-posterior decisions for pipe joints with multiple
        cracks using uploaded or Google Drive-hosted POF datasets.</p>
        <span class="app-link">Journal Paper 2 →</span>
      </a>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="notice"><strong>Research-use notice.</strong> The applications are '
    'decision-support prototypes. Results require engineering review and do not replace '
    'applicable codes, regulatory requirements, ILI validation, or an operator’s '
    'integrity-management procedures.</div>',
    unsafe_allow_html=True,
)
