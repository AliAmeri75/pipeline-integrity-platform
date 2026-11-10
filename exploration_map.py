"""Map entry point tolerant of a pre-update helper cached by Streamlit."""
import importlib
import inspect
import profile_map


def render_exploration_map(summary,selected_profile_id,*,selection_key,shared_project=False,
                           on_add_defect=None,on_route_change=None):
    renderer=profile_map.render_profile_location_map
    parameters=inspect.signature(renderer).parameters
    if ('selection_key' not in parameters or (shared_project and 'shared_project' not in parameters)
            or (on_add_defect is not None and 'on_add_defect' not in parameters)
            or (on_route_change is not None and 'on_route_change' not in parameters)):
        # The running process may still hold the old two-argument function.
        # Refresh only on this known API mismatch, rather than catching arbitrary
        # TypeErrors raised by the map itself or reloading on every rerun.
        importlib.reload(profile_map)
        renderer=profile_map.render_profile_location_map
    if shared_project:
        callbacks={} if on_add_defect is None and on_route_change is None else dict(
            on_add_defect=on_add_defect,on_route_change=on_route_change)
        return renderer(summary,selected_profile_id,selection_key=selection_key,shared_project=True,**callbacks)
    return renderer(summary,selected_profile_id,selection_key=selection_key)
