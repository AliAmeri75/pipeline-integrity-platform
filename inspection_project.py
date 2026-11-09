"""Static-planning introduction and the connected planning workspace."""
import streamlit as st

from platform_ui import ASSET_DIR, editable_markdown, render_project_hero, render_team
from inspection_planning.planner_ui import render_planner


def open_planning():
    st.session_state['static_planning_view'] = 'Planning & Results'


render_project_hero(
    'Reliability-based pipeline integrity planning',
    'Static Multiple Inspection and Excavation Planning',
    'Compare prior excavation intervals without ILI against fixed ILI-informed '
    'schedules, optimize lifecycle cost under reliability criteria, and quantify '
    'the value of information.',
)

introduction, planning = st.tabs(
    ['Introduction', 'Planning & Results'],
    key='static_planning_view', on_change='rerun',
)
with introduction:
    render_team()
    with st.container(border=True):
        action, illustration = st.columns([3, 1], vertical_alignment='center')
        with action:
            st.caption('Start your analysis')
            st.button('Open Planning and VoI Simulation', type='primary',
                icon=':material/calendar_month:', on_click=open_planning)
            st.write('Use the saved Data Exploration pipeline and cracks. Adjust '
                'samples, safety class, intervals, growth, POD, repair criteria '
                'and effectiveness, and costs in the planning workspace.')
        with illustration:
            st.image(str(ASSET_DIR / 'ili_pipeline.svg'), width='stretch')
    st.markdown('<div class="section-label">Project abstract</div>', unsafe_allow_html=True)
    st.markdown(editable_markdown('INSPECTION_ABSTRACT.md',
        'Add the inspection project abstract in content/INSPECTION_ABSTRACT.md.'))
    st.divider()
    st.markdown(editable_markdown('INSPECTION_DOCUMENTATION.md',
        'Add the inspection documentation in content/INSPECTION_DOCUMENTATION.md.'))
    st.markdown(
        '<div class="notice"><strong>Research-use notice.</strong> This application '
        'is a decision-support prototype. Its results require engineering review '
        'and do not replace ILI vendor validation, applicable codes, regulatory '
        'requirements, or an operator’s integrity-management procedures.</div>',
        unsafe_allow_html=True,
    )

# Render both tabs so inputs and results survive a return to the introduction.
# Simulations still run only when the user presses the Run button.
with planning:
    render_planner(show_header=False)
