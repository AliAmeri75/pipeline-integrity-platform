"""Introduction and launcher for fixed inspection scheduling."""

import streamlit as st

from platform_ui import (
    editable_markdown,
    render_inspection_cta,
    render_project_hero,
    render_team,
)


render_project_hero(
    "Reliability-based pipeline integrity planning",
    "Fixed Inspection Scheduling",
    "Interactive decision support for comparing fixed inspection intervals across multiple pipe joints under deterioration, inspection uncertainty, repair actions, failure risk, and life-cycle cost.",
)
render_team()
render_inspection_cta(
    "https://pipeline-inspection-appgit-qjifsvi4zeuyuchaueiuwm.streamlit.app/inspection_planner"
)

st.markdown('<div class="section-label">Project abstract</div>', unsafe_allow_html=True)
st.markdown(
    editable_markdown(
        "INSPECTION_ABSTRACT.md",
        "Add the inspection project abstract in `content/INSPECTION_ABSTRACT.md`.",
    )
)

st.divider()
st.markdown(
    editable_markdown(
        "INSPECTION_DOCUMENTATION.md",
        "Add the inspection documentation in `content/INSPECTION_DOCUMENTATION.md`.",
    )
)

st.markdown(
    '<div class="notice"><strong>Research-use notice.</strong> This application is a '
    'decision-support prototype. Its results require engineering review and do not replace '
    'ILI vendor validation, applicable codes, regulatory requirements, or an operator’s '
    'integrity-management procedures.</div>',
    unsafe_allow_html=True,
)
