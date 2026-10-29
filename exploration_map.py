"""Map entry point tolerant of a pre-update helper cached by Streamlit."""
import importlib
import inspect
import profile_map


def render_exploration_map(summary,selected_profile_id,*,selection_key,shared_project=False):
    renderer=profile_map.render_profile_location_map
    if 'selection_key' not in inspect.signature(renderer).parameters or (shared_project and 'shared_project' not in inspect.signature(renderer).parameters):
        # The running process may still hold the old two-argument function.
        # Refresh only on this known API mismatch, rather than catching arbitrary
        # TypeErrors raised by the map itself or reloading on every rerun.
        importlib.reload(profile_map)
        renderer=profile_map.render_profile_location_map
    if shared_project:
        return renderer(summary,selected_profile_id,selection_key=selection_key,shared_project=True)
    return renderer(summary,selected_profile_id,selection_key=selection_key)
