"""Selected publications, application documentation, and team contacts."""

import streamlit as st

from platform_ui import editable_markdown, render_project_hero, render_team


render_project_hero(
    "Research record and resources",
    "Publications, Documentation and Team",
    "Selected research outputs, application documentation, and contact information for the platform developers.",
)

st.markdown("## Team")
render_team(show_contacts=True)

st.markdown(editable_markdown("PUBLICATIONS.md", "Add publications in `content/PUBLICATIONS.md`."))

st.divider()
st.markdown(editable_markdown("DOCUMENTATION.md", "Add documentation in `content/DOCUMENTATION.md`."))
