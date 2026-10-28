"""Introduction page for the unified research platform."""

import streamlit as st

from platform_ui import editable_markdown, render_platform_hero, render_team


render_platform_hero()

st.markdown("## Team")
render_team(show_contacts=True)

st.markdown('<div class="section-label">Research overview</div>', unsafe_allow_html=True)
st.markdown(
    editable_markdown(
        "PLATFORM_ABSTRACT.md",
        "Add the platform abstract in `content/PLATFORM_ABSTRACT.md`.",
    )
)

st.markdown('<div class="section-label">Prepare and learn</div>', unsafe_allow_html=True)
st.markdown(
    """
    <section class="learning-grid" aria-label="Data preparation and educational tutorial">
      <article class="app-card learning-card">
        <a class="app-card-main" href="data-integration" target="_self">
          <span class="app-number">Data</span>
          <h3>Data Preparation Module</h3>
          <p>Upload and analyze crack or corrosion grid profiles, visualize their
          depth and dimensions, and export the feature sizes and locations required
          by the Planning modules.</p>
          <span class="app-link">Prepare profile data →</span>
        </a>
      </article>
      <article class="app-card learning-card">
        <a class="app-card-main" href="https://alirim-education.streamlit.app/"
           target="_blank" rel="noopener noreferrer">
          <span class="app-number">Learn</span>
          <h3>ALIRIM Education</h3>
          <p>Follow a guided classroom case: learn the limit state, calculate failure
          pressure, plot input probability densities, estimate POF, interpret the result,
          and complete a short quiz.</p>
          <span class="app-link">Open the separate education app ↗</span>
        </a>
      </article>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">Planning modules</div>', unsafe_allow_html=True)
st.markdown(
    """
    <section class="app-grid" aria-label="Planning modules">
      <article class="app-card">
        <a class="app-card-main" href="inspection" target="_self">
          <span class="app-number">I</span>
          <h3>Static Multiple Inspection and Excavation Planning</h3>
          <p>Compare prior excavation schedules without ILI against ILI-informed
          schedules, then calculate lifecycle-cost value of information.</p>
        </a>
        <span class="app-link app-status">Publication (in press)</span>
      </article>
      <article class="app-card">
        <a class="app-card-main" href="rl-planning" target="_self">
          <span class="app-number">II</span>
          <h3>Dynamic Inspection and Maintenance Planning</h3>
          <p>Train optimal maintenance-only or joint inspection-and-maintenance policies
          for a cracked pipe joint using reinforcement learning.</p>
        </a>
        <a class="app-link publication-link"
           href="https://doi.org/10.1016/j.ress.2026.113466" target="_blank"
           rel="noopener noreferrer">View publication ↗</a>
      </article>
      <article class="app-card">
        <a class="app-card-main" href="reliability-voi" target="_self">
          <span class="app-number">III</span>
          <h3>Static Single Delayed Inspection Planning</h3>
          <p>Evaluate prior and pre-posterior decisions for pipe joints with multiple
          cracks using uploaded or Google Drive-hosted POF datasets.</p>
        </a>
        <span class="app-link app-status">Publication (in press)</span>
      </article>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="notice"><strong>Research-use notice.</strong> The Planning Modules are '
    'decision-support prototypes. Results require engineering review and do not replace '
    'applicable codes, regulatory requirements, ILI validation, or an operator’s '
    'integrity-management procedures.</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">Teaching validation</div>', unsafe_allow_html=True)
st.markdown(
    """
    <a class="external-cta" href="teaching-pilot" target="_self">
      <span class="external-cta-copy">
        <strong>Teaching Pilot and Feedback</strong>
        <span class="external-cta-detail">Help test whether ALIRIM is useful for teaching
        pipeline integrity to students and early-career learners.</span>
      </span>
      <b aria-hidden="true">→</b>
    </a>
    """,
    unsafe_allow_html=True,
)
