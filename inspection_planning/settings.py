"""Retain planning choices when users visit Data Exploration and return.

Streamlit removes widget state for controls absent from a page. Keep a separate
plain-value copy, restoring defaults only when a widget is being recreated.
"""
import inspect
import streamlit as st


class PlanningSettings:
    def _widget(self, kind, label, *args, **kwargs):
        field = str(kwargs.pop('key', label))
        widget_key = 'static_planning_input_' + field
        saved = st.session_state.setdefault('static_planning_settings', {})
        widget = getattr(st, kind)
        bound = inspect.signature(widget).bind(label, *args, **kwargs)
        if widget_key not in st.session_state and field in saved and not kwargs.get('disabled', False):
            if kind == 'selectbox':
                options = list(bound.arguments['options'])
                if saved[field] in options:
                    bound.arguments['index'] = options.index(saved[field])
            else:
                bound.arguments['value'] = saved[field]
        bound.arguments['key'] = widget_key
        value = widget(*bound.args, **bound.kwargs)
        saved[field] = value
        return value

    def number_input(self, label, *args, **kwargs):
        return self._widget('number_input', label, *args, **kwargs)

    def selectbox(self, label, *args, **kwargs):
        return self._widget('selectbox', label, *args, **kwargs)

    def checkbox(self, label, *args, **kwargs):
        return self._widget('checkbox', label, *args, **kwargs)

    def text_input(self, label, *args, **kwargs):
        return self._widget('text_input', label, *args, **kwargs)
