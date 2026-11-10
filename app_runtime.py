"""Refresh the shared-input helpers retained by a running Cloud deployment.

Streamlit can execute an updated page while imported Python modules still refer
to the previous deployment. Refresh this small dependency group once per code
revision, in dependency order, before any page binds its rendering functions.
"""
import importlib
import sys


SHARED_INPUT_REVISION = 'planning-batches-v2'
SHARED_INPUT_MODULES = (
    'profile_data', 'profile_visuals', 'profile_map', 'project_editor',
    'exploration_map', 'deterministic_analysis', 'threat_workspaces',
    'inspection_planning.execution', 'inspection_planning.planner_ui',
)


def refresh_shared_input_modules():
    for name in SHARED_INPUT_MODULES:
        module = sys.modules.get(name)
        if module is not None and getattr(module, '_shared_input_revision', None) != SHARED_INPUT_REVISION:
            importlib.reload(module)
            module._shared_input_revision = SHARED_INPUT_REVISION
