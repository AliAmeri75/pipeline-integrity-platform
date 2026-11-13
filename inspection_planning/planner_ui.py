"""Fixed-interval planning inside ALIRIM's shared-data session.

Simulation/results UI adapted from AliAmeri75/pipeline-inspection-app,
inspection_planner.py; shared-data integration replaces its separate input editor.
"""


def render_planner(*, show_header=True):
    import contextlib
    import copy
    import hashlib
    import html
    import io
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    import folium
    import streamlit as st
    from packaging.version import Version
    from streamlit_folium import st_folium
    from inspection_planning.engine import (
        DEFAULT_MAX_ANNUAL_BURST_POF, DEFAULT_MAX_ANNUAL_LEAK_POF,
        EXCAVATION_DECISION_MODE, ILI_DECISION_MODE, POD,
        POD_DEPTH_LENGTH_MODEL, POD_DEPTH_ONLY_MODEL,
    )
    from inspection_planning.comparison import (
        calculate_value_of_information, compare_ili_intervals_to_prior_safe,
        format_optional_decimal, select_lowest_cost_result, select_optimal_result,
    )
    from project_editor import get_project
    from planning_project import planning_handoff, planning_joints
    from profile_map import point_at_chainage
    from inspection_planning.risk_map import sliding_window_reliability, reliability_map
    from inspection_planning.settings import PlanningSettings
    from inspection_planning.execution import run_batched_flexible_simulation, effective_batch_size, EXECUTION_REVISION
    from inspection_planning.diagnostics import interval_safety_rows, joint_safety_rows

    COLORS = {
        "navy": "#10243d",
        "teal": "#0f766e",
        "blue": "#2563a8",
        "amber": "#c87818",
        "coral": "#c94f3d",
        "violet": "#7556a6",
    }
    MODERN_CHART_WIDTH = Version(st.__version__) >= Version("1.51.0")
    DEFAULT_CRACK_BIRTH_RATE = 0.00008
    PIPELINE_CLASSES = ["Class 1", "Class 2", "Class 3", "Class 4", "User-defined"]
    PIPELINE_CLASS_SAFETY_LIMITS = {
        "Class 1": {
            "max_annual_leak_pof": DEFAULT_MAX_ANNUAL_LEAK_POF,
            "max_annual_burst_pof": DEFAULT_MAX_ANNUAL_BURST_POF,
        },
        "Class 2": {
            "max_annual_leak_pof": 1e-3,
            "max_annual_burst_pof": 1e-4,
        },
        "Class 3": {
            "max_annual_leak_pof": 1e-4,
            "max_annual_burst_pof": 1e-5,
        },
        "Class 4": {
            "max_annual_leak_pof": 1e-5,
            "max_annual_burst_pof": 1e-6,
        },
    }
    st.markdown(
        """
        <style>
        :root { --ink:#10243d; --teal:#0f766e; --paper:#f4f2ec; --line:#d9dfdf; }
        .hero { padding:1.05rem 1.3rem; margin:-.3rem 0 1rem; color:white;
                background:var(--ink); border-bottom:4px solid var(--teal); }
        .hero small { color:#8fd1c9; font-weight:800; letter-spacing:.13em;
                      text-transform:uppercase; }
        .hero h1 { margin:.18rem 0; color:white; font-family:Georgia,serif;
                   font-size:2rem; font-weight:500; }
        .hero p { margin:.25rem 0 0; color:#d9e3ea; font-size:.86rem; }
        div[data-testid="stMetric"] { background:white; border:1px solid var(--line);
                                      border-top:3px solid var(--teal); padding:.85rem; }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {
            background:white; border:1px solid var(--line); padding:.25rem;
        }
        .note { padding:.75rem .9rem; background:#e8efed; border-left:3px solid var(--teal);
                color:#425461; font-size:.84rem; margin:.4rem 0 .9rem; }
        .result-matrix { background:white; border:1px solid var(--line); border-radius:12px;
                         overflow:hidden; margin:.7rem 0 1rem; box-shadow:0 7px 22px rgba(16,36,61,.07); }
        .result-matrix table { width:100%; border-collapse:collapse; font-size:.88rem; }
        .result-matrix th { background:var(--ink); color:white; padding:.75rem .65rem;
                            text-align:center; font-weight:700; }
        .result-matrix td { padding:.78rem .65rem; text-align:center;
                            border-top:1px solid #e5e9e8; }
        .result-matrix td:first-child { text-align:left; font-weight:750; color:var(--ink); }
        .result-matrix tr:nth-child(even) td { background:#f7f9f8; }
        .badge-safe, .badge-unsafe { display:inline-block; padding:.18rem .55rem;
                                    border-radius:999px; font-weight:800; }
        .badge-safe { color:#0f6a42; background:#dcf4e7; }
        .badge-unsafe { color:#9b2d22; background:#fde5e1; }
        .not-found { color:#9b2d22; font-weight:800; }
        .voi-card { border:1px solid; border-radius:12px; padding:1rem 1.15rem;
                    margin:.65rem 0 1rem; box-shadow:0 7px 22px rgba(16,36,61,.07); }
        .voi-card .voi-label { font-size:.78rem; font-weight:800; letter-spacing:.06em;
                               text-transform:uppercase; }
        .voi-card .voi-value { font-size:2rem; line-height:1.15; font-weight:800;
                               margin:.18rem 0; }
        .voi-card .voi-message { font-size:.9rem; font-weight:650; }
        .voi-positive { color:#0b5d36; background:#e5f5eb; border-color:#91cba8; }
        .voi-negative { color:#8d241c; background:#fde9e6; border-color:#e7a59d; }
        .voi-neutral { color:#425461; background:#eef1f2; border-color:#cbd3d6; }
        .stButton > button[kind="primary"] { background:var(--teal); border-color:var(--teal); }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if show_header:
        st.markdown(
            """
            <div class="hero">
              <small>Reliability-based planning</small>
              <h1>Static Multiple Inspection and Excavation Planning</h1>
              <p>Compare prior excavation scheduling without ILI against pre-posterior,
                 ILI-informed scheduling using the same deterioration and cost model.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


    try:
        handoff = planning_handoff(get_project())
    except (ValueError, KeyError, TypeError) as exc:
        st.title("Inspection Planning")
        st.error(str(exc))
        st.page_link("data_integration.py", label="Review saved data in Data Exploration", icon="📋")
        return
    st.success("Connected to the saved Data Exploration dataset. No pipeline or defect re-entry is needed.")
    st.caption(handoff["project"]["source"] + " · Dataset " + handoff["dataset_id"][:10]
        + ". Draft edits are used only after saving them in Data Exploration.")
    st.page_link("data_integration.py", label="Edit pipeline and defects in Data Exploration", icon="📋")
    cols = st.columns(4)
    for col, label, value in zip(cols, ["Pipeline length", "Physical joints", "Cracked joints", "Initial cracks"],
        [f"{handoff['pipeline_length_km']:.3f} km", str(handoff['total_joints']),
         str(handoff['cracked_joints']), str(handoff['initial_cracks'])]):
        col.metric(label, value)
    with st.expander("Saved pipeline, defects and planning inputs", expanded=False):
        st.caption("Maximum measured depth and full measured profile length define each initial crack. "
            "All cracks within the same nominal joint are kept together. Initially crack-free joints "
            "remain in the route and can develop new cracks through the initiation model.")
        st.dataframe(handoff["defect_register"], hide_index=True, width="stretch")
        st.dataframe(handoff["preview"], hide_index=True, width="stretch")
        with st.expander("Saved segment properties and uncertainties"):
            st.dataframe(handoff["project"]["segments"], hide_index=True, width="stretch")
            st.dataframe(handoff["project"]["uncertainties"], hide_index=True, width="stretch")
        route = handoff["project"]["route"]
        view = folium.Map(location=route[0], zoom_start=12, tiles="OpenStreetMap")
        folium.PolyLine(route, color="#0f766e", weight=5, tooltip="Saved pipeline route").add_to(view)
        for _, feature in handoff["defect_register"].iterrows():
            point = point_at_chainage(route, float(feature["Distance from start (m)"]) / 1000)
            folium.CircleMarker(point, radius=6, color="#c94f3d", fill=True,
                tooltip=html.escape(str(feature["Profile ID"])) + " · Joint " + str(feature["Joint number"])).add_to(view)
        view.fit_bounds(route)
        st_folium(view, height=330, returned_objects=[], key="saved_planning_route_" + handoff["dataset_id"][:10])
    st.caption("Planning adds growth, initiation, ILI, repair, cost and safety assumptions below. "
        "The existing method conditions the simulation on survival at time zero. "
        "Initial-condition assessment remains in Preliminary Analysis.")

    def unpack_result(raw, interval, decision_mode, sim_params):
        (
            times, leak_pof, burst_pof, leak_hazard, burst_hazard, inspections,
            cpp, cff, crr, cii, is_safe, unsafe_times,
            cpp_cracked, cpp_crack_free, repairs, actions, debug,
        ) = raw
        return {
            "interval": interval,
            "decision_mode": decision_mode,
            "max_annual_leak_pof": sim_params["max_annual_leak_pof"],
            "max_annual_burst_pof": sim_params["max_annual_burst_pof"],
            "times": times,
            "leak_pof": leak_pof,
            "burst_pof": burst_pof,
            "leak_hazard": leak_hazard,
            "burst_hazard": burst_hazard,
            "leak_annual_pof": debug["system_leak_annual_pof"],
            "burst_annual_pof": debug["system_burst_annual_pof"],
            "inspections": inspections,
            "cpp": cpp,
            "total_cpp": float(np.sum(cpp)),
            "failure_cost": float(np.sum(cff)),
            "repair_cost": float(np.sum(crr)),
            "inspection_cost": float(np.sum(cii)),
            "is_safe": is_safe,
            "unsafe_times": unsafe_times,
            "expected_repairs": float(np.sum(repairs)),
            "joint_names": debug["joint_names"],
            "joint_leak_pofs": debug["joint_leak_pofs"],
            "joint_burst_pofs": debug["joint_burst_pofs"],
            "joint_leak_step_pofs": debug["joint_leak_step_pofs"],
            "joint_burst_step_pofs": debug["joint_burst_step_pofs"],
            "requested_samples": debug["requested_samples"],
            "retained_samples": debug["retained_samples"],
        }


    def parse_manual_years(value, label, horizon_years):
        """Parse comma-separated integer intervention years."""
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label}: enter one or more years.")
        parts = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
        try:
            values = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError(f"{label}: use whole years separated by commas, for example 2, 10, 15.") from exc
        if not values or any(not np.isfinite(year) or not year.is_integer() for year in values):
            raise ValueError(f"{label}: each entry must be a whole year.")
        years = [int(year) for year in values]
        if any(year < 1 or year > horizon_years for year in years):
            raise ValueError(f"{label}: years must be from 1 to {int(horizon_years)}.")
        if len(set(years)) != len(years):
            raise ValueError(f"{label}: remove duplicate years.")
        return sorted(years)


    def run_interval_study(joints, intervals, model, decision_mode, job):
        method_label = (
            "prior excavation"
            if decision_mode == EXCAVATION_DECISION_MODE
            else "ILI-informed inspection"
        )
        result_key = 'prior_results' if decision_mode == EXCAVATION_DECISION_MODE else 'ili_results'
        log_key = 'prior_log' if decision_mode == EXCAVATION_DECISION_MODE else 'ili_log'
        results = job.setdefault(result_key, [])
        progress = st.progress(0, text=f"Preparing {method_label} simulations…")
        log = io.StringIO()
        log.write(job.get(log_key, ''))
        for index, interval in enumerate(intervals):
            if any(result['interval'] == interval for result in results):
                continue
            sim = copy.deepcopy(model["sim"])
            sim["inspection_interval"] = interval
            checkpoint = job.setdefault('checkpoints', {}).setdefault(f'{decision_mode}:{interval}', {})
            def report(done, requested, retained):
                progress.progress((index + done / requested) / len(intervals),
                    text=f'{method_label.capitalize()}: {interval}-year interval, '
                         f'{done:,}/{requested:,} samples processed ({retained:,} retained).')
            with contextlib.redirect_stdout(log):
                raw = run_batched_flexible_simulation(
                    "equidistant",
                    model["horizon"],
                    1,
                    model["samples"],
                    joints,
                    model["costs"],
                    sim,
                    [model["depth_error"], model["length_error"]],
                    model["q_pod"],
                    default_birth_rate=model["birth_rate"],
                    property_seed=model["seed"],
                    crack_length_std=model["initial_length_std"],
                    crack_depth_std=model["initial_depth_std"],
                    track_debug=False,
                    decision_mode=decision_mode,
                    batch_size=model['batch_size'], state=checkpoint, on_progress=report,
                )
            results.append(unpack_result(raw, interval, decision_mode, sim))
            job[log_key] = log.getvalue()
        progress.progress(1.0, text=f"{method_label.capitalize()} optimization complete")
        return results, log.getvalue()


    def base_figure(title, x_title, y_title):
        figure = go.Figure()
        figure.update_layout(
            title={"text": title, "font": {"family": "Georgia", "size": 20}},
            xaxis_title=x_title,
            yaxis_title=y_title,
            height=430,
            margin={"l": 60, "r": 25, "t": 70, "b": 55},
            paper_bgcolor="white",
            plot_bgcolor="white",
            hovermode="x unified",
            font={"family": "Arial", "color": COLORS["navy"]},
            legend={"orientation": "h", "y": -0.22, "x": 0.5, "xanchor": "center"},
        )
        figure.update_xaxes(showgrid=True, gridcolor="#e8ebea")
        figure.update_yaxes(showgrid=True, gridcolor="#e8ebea")
        return figure


    def show_figure(figure, *, key=None, selectable=False):
        width_argument = (
            {"width": "stretch"}
            if MODERN_CHART_WIDTH
            else {"use_container_width": True}
        )
        chart_arguments = {
            "config": {"displaylogo": False},
            **width_argument,
        }
        if selectable:
            chart_arguments.update(
                key=key,
                on_select="rerun",
                selection_mode="points",
            )
        return st.plotly_chart(figure, **chart_arguments)


    def _safety_label(result):
        return "Safe" if result["is_safe"] else "Unsafe"


    def recommendation_matrix(prior_cost_optimal, prior_safe, ili_cost_optimal, ili_safe):
        """Build a compact result matrix for cost and safety decisions."""

        def row(method, cost_optimal, safe_result):
            safety = _safety_label(cost_optimal)
            badge_class = "badge-safe" if cost_optimal["is_safe"] else "badge-unsafe"
            safe_interval = (
                f"{safe_result['interval']} years"
                if safe_result is not None
                else '<span class="not-found">Not found</span>'
            )
            safe_cost = (
                f"${safe_result['total_cpp']:.4f}M"
                if safe_result is not None
                else "—"
            )
            return (
                "<tr>"
                f"<td>{method}</td>"
                f"<td><b>{cost_optimal['interval']} years</b></td>"
                f"<td>${cost_optimal['total_cpp']:.4f}M</td>"
                f'<td><span class="{badge_class}">{safety}</span></td>'
                f"<td>{safe_interval}</td>"
                f"<td>{safe_cost}</td>"
                "</tr>"
            )

        prior_row = row("Prior excavation (no ILI)", prior_cost_optimal, prior_safe)
        ili_row = row("Pre-posterior (ILI-informed)", ili_cost_optimal, ili_safe)
        return (
            '<div class="result-matrix"><table><thead><tr>'
            "<th>Planning method</th>"
            "<th>Cost-optimal interval</th>"
            "<th>Lowest cost</th>"
            "<th>Safety at cost optimum</th>"
            "<th>Minimum-cost safe interval</th>"
            "<th>Safe cost</th>"
            "</tr></thead><tbody>"
            f"{prior_row}{ili_row}"
            "</tbody></table></div>"
        )


    def _cost_customdata(results):
        return np.asarray(
            [
                [
                    result["total_cpp"],
                    result["failure_cost"],
                    result["repair_cost"],
                    result["inspection_cost"],
                    _safety_label(result),
                ]
                for result in results
            ],
            dtype=object,
        )


    def _cost_hover_template(total_label):
        return (
            "<b>Interval: %{x} years</b><br>"
            f"{total_label}: $%{{customdata[0]:.6f}}M<br>"
            "Cf (failure): $%{customdata[1]:.6f}M<br>"
            "Cr (repair): $%{customdata[2]:.6f}M<br>"
            "Ci (inspection): $%{customdata[3]:.6f}M<br>"
            "Safety: <b>%{customdata[4]}</b><extra></extra>"
        )


    def cost_figure(results, title, interval_label, total_label):
        figure = base_figure(
            title,
            interval_label,
            f"Expected cost (million {handoff['consequence_unit'] or 'currency units'})",
        )
        styles = [
            (total_label, "total_cpp", COLORS["navy"]),
            ("Failure cost, Cf", "failure_cost", COLORS["coral"]),
            ("Repair cost, Cr", "repair_cost", COLORS["teal"]),
            ("Inspection cost, Ci", "inspection_cost", COLORS["amber"]),
        ]
        customdata = _cost_customdata(results)
        marker_symbols = ["circle" if result["is_safe"] else "x" for result in results]
        for label, key, color in styles:
            figure.add_trace(
                go.Scatter(
                    x=[result["interval"] for result in results],
                    y=[result[key] for result in results],
                    name=label,
                    mode="lines+markers",
                    line={"color": color, "width": 2.6},
                    marker={"size": 8, "symbol": marker_symbols},
                    customdata=customdata,
                    hovertemplate=_cost_hover_template(total_label),
                )
            )
        figure.update_layout(hovermode="closest", clickmode="event+select")
        return figure


    def _selected_points(event):
        """Read selected Plotly points across Streamlit's dict and attribute APIs."""

        if event is None:
            return []
        selection = getattr(event, "selection", None)
        if selection is None and isinstance(event, dict):
            selection = event.get("selection")
        if selection is None:
            return []
        points = getattr(selection, "points", None)
        if points is None and isinstance(selection, dict):
            points = selection.get("points")
        return list(points or [])


    def _result_at_interval(results, interval):
        try:
            selected_interval = float(interval)
        except (TypeError, ValueError):
            return None
        return next(
            (
                result
                for result in results
                if np.isclose(float(result["interval"]), selected_interval)
            ),
            None,
        )


    def show_selected_cost(result, total_label):
        if result is None:
            return
        st.markdown(f"**Selected interval: {result['interval']} years**")
        columns = st.columns(4)
        columns[0].metric(total_label, f"${result['total_cpp']:.6f}M")
        columns[1].metric("Cf — failure cost", f"${result['failure_cost']:.6f}M")
        columns[2].metric("Cr — repair cost", f"${result['repair_cost']:.6f}M")
        columns[3].metric("Safety", _safety_label(result))
        if result["is_safe"]:
            st.success("Safe — this interval satisfies both probability-of-failure criteria.")
        else:
            st.error("Unsafe — this interval exceeds at least one probability-of-failure criterion.")
        st.caption(
            f"Limits used: PfL ≤ {result['max_annual_leak_pof']:.1e}; "
            f"PfB ≤ {result['max_annual_burst_pof']:.1e}."
        )


    def show_selectable_cost_figure(results, title, interval_label, total_label, key):
        st.caption("Click any point to inspect its Cf, Cr, and Safe/Unsafe result. ○ Safe   × Unsafe")
        event = show_figure(
            cost_figure(results, title, interval_label, total_label),
            key=key,
            selectable=True,
        )
        points = _selected_points(event)
        if points:
            point = points[0]
            interval = point.get("x") if isinstance(point, dict) else getattr(point, "x", None)
            show_selected_cost(_result_at_interval(results, interval), total_label)


    def annual_pof_figure(result, schedule_label):
        figure = base_figure(
            f"Annual system POF at the cost-optimal {result['interval']}-year "
            f"{schedule_label.lower()} interval",
            "Year",
            "Annual probability of failure (whole pipeline)",
        )
        figure.add_trace(
            go.Scatter(
                x=result["times"],
                y=np.maximum(result["leak_annual_pof"], 1e-12),
                name="Leakage",
                mode="lines+markers",
                line={"color": COLORS["blue"], "width": 2.6},
                marker={"size": 5},
            )
        )
        figure.add_trace(
            go.Scatter(
                x=result["times"],
                y=np.maximum(result["burst_annual_pof"], 1e-12),
                name="Burst",
                mode="lines+markers",
                line={"color": COLORS["coral"], "width": 2.6},
                marker={"size": 5},
            )
        )
        leak_limit = result["max_annual_leak_pof"]
        burst_limit = result["max_annual_burst_pof"]
        if leak_limit > 0:
            figure.add_hline(
                y=leak_limit,
                line_dash="dot",
                line_color=COLORS["blue"],
                annotation_text=f"PfL limit = {leak_limit:.1e}",
            )
        if burst_limit > 0:
            figure.add_hline(
                y=burst_limit,
                line_dash="dash",
                line_color=COLORS["coral"],
                annotation_text=f"PfB limit = {burst_limit:.1e}",
            )
        for inspection in result["inspections"]:
            figure.add_vline(x=inspection, line_dash="dot", line_color=COLORS["teal"],
                             opacity=0.45)
        figure.update_yaxes(type="log")
        return figure


    def results_table(results, total_label):
        total_column = f"Total {total_label} ($M)"
        return pd.DataFrame(
            [
                {
                    "Interval (years)": result["interval"],
                    total_column: result["total_cpp"],
                    "Cf — failure ($M)": result["failure_cost"],
                    "Cr — repair ($M)": result["repair_cost"],
                    "ILI inspection ($M)": result["inspection_cost"],
                    "Expected repairs": result["expected_repairs"],
                    "Safety": _safety_label(result),
                }
                for result in results
            ]
        )


    def comparison_cost_figure(prior_results, ili_results):
        figure = base_figure(
            "Prior excavation versus ILI-informed scheduling",
            "Schedule interval (years)",
            f"Expected lifecycle cost (million {handoff['consequence_unit'] or 'currency units'})",
        )
        figure.add_trace(
            go.Scatter(
                x=[result["interval"] for result in prior_results],
                y=[result["total_cpp"] for result in prior_results],
                name="Prior: excavation without ILI",
                mode="lines+markers",
                line={"color": COLORS["amber"], "width": 3},
                marker={
                    "size": 8,
                    "symbol": ["circle" if result["is_safe"] else "x" for result in prior_results],
                },
                customdata=_cost_customdata(prior_results),
                hovertemplate=_cost_hover_template("Cprior"),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[result["interval"] for result in ili_results],
                y=[result["total_cpp"] for result in ili_results],
                name="Pre-posterior: ILI-informed",
                mode="lines+markers",
                line={"color": COLORS["teal"], "width": 3},
                marker={
                    "size": 8,
                    "symbol": ["circle" if result["is_safe"] else "x" for result in ili_results],
                },
                customdata=_cost_customdata(ili_results),
                hovertemplate=_cost_hover_template("Cpp"),
            )
        )
        figure.update_layout(hovermode="closest", clickmode="event+select")
        return figure


    def show_comparison_cost_figure(prior_results, ili_results):
        st.caption("Click a Cprior or Cpp point to inspect Cf, Cr, and Safe/Unsafe. ○ Safe   × Unsafe")
        event = show_figure(
            comparison_cost_figure(prior_results, ili_results),
            key="comparison_cost_selection",
            selectable=True,
        )
        points = _selected_points(event)
        if not points:
            return
        point = points[0]
        if isinstance(point, dict):
            interval = point.get("x")
            curve_number = point.get("curve_number", 0)
        else:
            interval = getattr(point, "x", None)
            curve_number = getattr(point, "curve_number", 0)
        selected_results = prior_results if int(curve_number) == 0 else ili_results
        total_label = "Cprior" if int(curve_number) == 0 else "Cpp"
        show_selected_cost(_result_at_interval(selected_results, interval), total_label)


    def comparison_table(prior_safe_result, ili_results):
        return pd.DataFrame(
            compare_ili_intervals_to_prior_safe(prior_safe_result, ili_results)
        )


    st.subheader("Planning Settings")
    st.caption("Open a section below to edit your planning assumptions. Pipeline and crack data "
               "come from the saved Data Exploration dataset.")
    settings = PlanningSettings()
    settings_left, settings_right = st.columns(2)

    with settings_left:
        with st.expander("Simulation settings", expanded=True):
            samples = settings.number_input("Monte Carlo samples", min_value=100, value=1000, step=100,
                help='Total requested realizations. The app processes these in smaller batches to reduce memory use.')
            sample_batch_size = settings.number_input('Samples per batch', min_value=1, max_value=1000,
                value=250, step=50, help='Lower values reduce peak memory. They do not reduce the total sample count. '
                    'Changing batch size changes the random realizations, so rerun the whole comparison.')
            horizon = settings.number_input("Analysis horizon (years)", 5, 100, 30, 5)
            pipe_length = handoff["pipeline_length_km"]
            st.caption(f"Saved route length: {pipe_length:.6f} km")
            random_seed = settings.number_input("Random seed", 0, 1000000, 0, 1)

    with settings_right:
        with st.expander("Pipeline class and safety criteria", expanded=True):
            pipeline_class = settings.selectbox("Pipeline class", PIPELINE_CLASSES)
            class_limits = PIPELINE_CLASS_SAFETY_LIMITS.get(pipeline_class)
            widget_suffix = pipeline_class.lower().replace(" ", "_").replace("-", "_")
            if class_limits is not None:
                st.caption("The study's annual POF limits are selected automatically for this class.")
                max_annual_leak_pof = settings.number_input(
                    "Maximum annual leakage POF, PfL",
                    value=class_limits["max_annual_leak_pof"],
                    format="%.1e",
                    disabled=True,
                    key=f"pfl_{widget_suffix}",
                )
                max_annual_burst_pof = settings.number_input(
                    "Maximum annual burst POF, PfB",
                    value=class_limits["max_annual_burst_pof"],
                    format="%.1e",
                    disabled=True,
                    key=f"pfb_{widget_suffix}",
                )
                st.caption(
                    "Classes 1–4 use an illustrative one-order-of-magnitude progression. "
                    "These are study assumptions, not values prescribed directly by CSA Z662. "
                    "[CSA Group research](https://www.csagroup.org/wp-content/uploads/"
                    "CSA-Group-Research-Pipeline-Safety-Factors-Exec-Summary.pdf) describes "
                    "the broader risk-consistent safety-class basis."
                )
            else:
                st.info("Enter the two annual POF limits for this analysis.")
                max_annual_leak_pof = settings.number_input(
                    "Maximum annual leakage POF, PfL",
                    min_value=0.0,
                    max_value=1.0,
                    value=None,
                    placeholder="Enter the PfL limit",
                    format="%.1e",
                    key=f"pfl_{widget_suffix}",
                )
                max_annual_burst_pof = settings.number_input(
                    "Maximum annual burst POF, PfB",
                    min_value=0.0,
                    max_value=1.0,
                    value=None,
                    placeholder="Enter the PfB limit",
                    format="%.1e",
                    key=f"pfb_{widget_suffix}",
                )
            safety_criteria_valid = (
                max_annual_leak_pof is not None and max_annual_burst_pof is not None
            )
            if safety_criteria_valid:
                st.caption(
                    "A schedule is Safe only when "
                    f"PfL ≤ {max_annual_leak_pof:.1e} and "
                    f"PfB ≤ {max_annual_burst_pof:.1e}."
                )
                st.caption('These checks use the annual probability of at least one failure '
                    'anywhere on the full pipeline, combined across its physical joints. '
                    'The limits are compared directly with that whole-pipeline probability; '
                    'there is no division by pipeline length. The map also reports local '
                    'sliding 1 km windows.')

    with settings_left:
        with st.expander("Prior excavation intervals"):
            prior_interval_start = settings.number_input(
                "First excavation interval (years)", 1, 100, 5, 1
            )
            prior_interval_end = settings.number_input(
                "Last excavation interval (years)", 1, 100, 20, 1
            )
            prior_interval_step = settings.number_input(
                "Excavation interval step (years)", 1, 50, 5, 1
            )

    with settings_right:
        with st.expander("ILI inspection intervals"):
            ili_interval_start = settings.number_input(
                "First ILI interval (years)", 1, 100, 5, 1
            )
            ili_interval_end = settings.number_input(
                "Last ILI interval (years)", 1, 100, 20, 1
            )
            ili_interval_step = settings.number_input(
                "ILI interval step (years)", 1, 50, 5, 1
            )

    with settings_left:
        with st.expander("Crack initiation"):
            st.caption("Existing crack sizes and their uncertainties come from Data Exploration.")
            initial_length_std = initial_depth_std = 0.0  # Per-crack specs take precedence.
            default_birth_rate = settings.number_input(
                "Crack birth rate (cracks per joint-year)",
                min_value=0.0,
                value=DEFAULT_CRACK_BIRTH_RATE,
                step=0.00001,
                format="%.6f",
                help=(
                    "Expected number of newly initiated cracks in one pipe joint during "
                    "one year. New-crack counts use a Poisson distribution; initiation "
                    "times retain the existing research model's sampling rule. "
                    "Set this to zero to model no new crack initiation."
                ),
            )
            st.caption(
                "This planning-only birth rate applies to every saved physical joint."
            )
            st.caption('Newly initiated cracks retain the research model\'s sizes: '
                'depth 0.1–0.4 mm and full length 40–45 mm. Reducing existing crack sizes '
                'does not change these future initiation assumptions.')

    with settings_right:
        with st.expander("Crack growth model"):
            mean_g = settings.number_input("Mean depth growth, α (mm/year)", 0.0, 10.0, 0.10, 0.01)
            std_g = settings.number_input("Std. α", 0.0, 10.0, 0.03, 0.01)
            mean_neq = settings.number_input("Mean cycles/year, Neq", 0.0, 1e7, 1000.0, 100.0)
            std_neq = settings.number_input("Std. Neq", 0.0, 1e7, 300.0, 50.0)
            mean_c = settings.number_input("Mean Paris C", 0.0, 1e-8, 2.5e-13, 1e-14, format="%.3e")
            std_c = settings.number_input("Std. Paris C", 0.0, 1e-8, 1.35e-13, 1e-14, format="%.3e")
            delta_s = settings.number_input("Stress range, ΔS", 0.01, 1000.0, 2.0, 0.1)
            paris_m = settings.number_input("Paris exponent, m", 0.1, 10.0, 3.0, 0.1)

    with settings_left:
        with st.expander("ILI measurement model — POD and sizing error"):
            st.caption(
                "POD controls whether ILI detects a crack; sizing errors describe the "
                "uncertainty in the reported crack dimensions."
            )
            pod_model = settings.selectbox(
                "POD model",
                options=[POD_DEPTH_ONLY_MODEL, POD_DEPTH_LENGTH_MODEL],
                format_func=lambda value: {
                    POD_DEPTH_ONLY_MODEL: "Depth only (current model)",
                    POD_DEPTH_LENGTH_MODEL: "Depth and length",
                }[value],
                help=(
                    "Choose whether detection depends only on crack depth or on both "
                    "crack depth and crack length."
                ),
            )
            q_pod = settings.number_input(
                "Depth coefficient, qd (1/mm)",
                min_value=0.0,
                max_value=100.0,
                value=2.0,
                step=0.1,
                help="Higher qd gives a higher POD for the same crack depth.",
            )
            if pod_model == POD_DEPTH_LENGTH_MODEL:
                q_length_pod = settings.number_input(
                    "Length coefficient, qL (1/mm)",
                    min_value=0.0,
                    max_value=10.0,
                    value=0.01,
                    step=0.01,
                    format="%.3f",
                    help="Higher qL gives a higher POD for the same crack length.",
                )
                st.latex(r"POD(d,L)=1-\exp[-(q_d d+q_L L)]")
            else:
                q_length_pod = 0.0
                st.latex(r"POD(d)=1-\exp(-q_d d)")
            example_pod = POD(
                1.0,
                q_pod,
                length=40.0,
                pod_model=pod_model,
                q_length=q_length_pod,
            )
            st.caption(
                f"Example POD for a 1 mm deep, 40 mm long crack: {example_pod:.1%}. "
                "Calibrate the coefficients using ILI vendor qualification or excavation data."
            )
            length_error = settings.number_input(
                "ILI crack-length error std. (mm)", 0.0, 100.0, 15.6, 0.1
            )
            depth_error = settings.number_input(
                "ILI crack-depth error std. (mm)", 0.0, 20.0, 0.74, 0.01
            )

    with settings_right:
        with st.expander("Repair criteria 1 and 2"):
            st.markdown("**Repair criterion 1**")
            d_rep1 = settings.number_input(
                "Type 1 depth criterion (%WT)", 0.0, 100.0, 50.0, 1.0
            )
            fpr_rep1 = settings.number_input(
                "Type 1 pressure factor", 0.0, 10.0, 1.25, 0.05
            )
            st.divider()
            st.markdown("**Repair criterion 2**")
            d_rep2 = settings.number_input(
                "Type 2 depth criterion (%WT)", 0.0, 100.0, 70.0, 1.0
            )
            fpr_rep2 = settings.number_input(
                "Type 2 pressure factor", 0.0, 10.0, 1.10, 0.05
            )

    with settings_right:
        with st.expander("Repair effectiveness"):
            st.caption("For this model, each technique leaves a residual crack depth after treatment. "
                       "The value is sampled uniformly between the minimum and maximum; use the same "
                       "minimum and maximum for a fixed residual depth.")
            st.markdown("**Recoat (Type 1 intervention)**")
            coat_df = settings.number_input("Recoat growth factor, df1", 0.0, 1.0, 0.0, 0.05)
            coat_period = settings.number_input("Recoat effective period (years)", 0, 100, 5, 1)
            recoat_depth_min = settings.number_input(
                "Recoat residual crack depth minimum (mm)", 0.0, 100.0, 1.1, 0.1,
                help="Lower end of the residual-depth range used after a Type 1 intervention.")
            recoat_depth_max = settings.number_input(
                "Recoat residual crack depth maximum (mm)", 0.0, 100.0, 1.4, 0.1,
                help="Upper end of the residual-depth range used after a Type 1 intervention.")
            if recoat_depth_min > recoat_depth_max:
                st.error("Recoat residual-depth minimum cannot exceed its maximum.")
                st.stop()
            st.divider()
            st.markdown("**Sleeve (Type 2 intervention)**")
            sleeve_df = settings.number_input("Sleeve growth factor, df2", 0.0, 1.0, 0.0, 0.05)
            sleeve_period = settings.number_input("Sleeve effective period (years)", 0, 100, 5, 1)
            sleeve_depth_min = settings.number_input(
                "Sleeve residual crack depth minimum (mm)", 0.0, 100.0, 1.1, 0.1,
                help="Lower end of the residual-depth range used after a Type 2 intervention.")
            sleeve_depth_max = settings.number_input(
                "Sleeve residual crack depth maximum (mm)", 0.0, 100.0, 1.4, 0.1,
                help="Upper end of the residual-depth range used after a Type 2 intervention.")
            if sleeve_depth_min > sleeve_depth_max:
                st.error("Sleeve residual-depth minimum cannot exceed its maximum.")
                st.stop()

    with settings_left:
        with st.expander(f"Costs (million {handoff['consequence_unit'] or 'currency units'})"):
            st.caption("The planning model sums costs for individual joint failure events. "
                       "Use the same currency for every cost; no currency conversion is performed.")
            use_segment_costs = settings.checkbox(
                "Use saved segment consequences as the loss for each joint failure event",
                help="This is an additional cost assumption: multiple joint failures can each incur "
                     "the full saved segment loss. Leave off to use the failure costs below.")
            if use_segment_costs:
                st.caption("Saved values are converted to millions. The failure costs below are "
                           "fallbacks only for UNKNOWN saved consequences.")
            inspection_cost_per_km = settings.number_input(
                "ILI inspection cost per km per event ($M/km)",
                0.0,
                1000.0,
                0.015,
                0.001,
                help=(
                    "Applied once across the full pipeline at every scheduled ILI. "
                    "For example, 0.01 $M/km for a 10 km pipeline gives 0.10 $M "
                    "per ILI event before discounting."
                ),
            )
            repair_1_cost = settings.number_input(
                "Type 1 intervention cost, Cr1", 0.0, 1000.0, 0.20, 0.05,
                help="For the prior method, this is the base cost of excavating and treating a cracked joint.",
            )
            repair_2_cost = settings.number_input("Additional type 2 cost, Cr2", 0.0, 1000.0, 0.0, 0.05)
            leak_cost = settings.number_input("Leak failure cost", 0.0, 10000.0, 2.0, 0.5)
            burst_cost = settings.number_input("Burst failure cost", 0.001, 10000.0, 20.0, 1.0)
            discount_percent = settings.number_input("Discount rate (%)", 0.0, 100.0, 4.0, 0.5)

    st.markdown(
        '<div class="note"><b>Prior method:</b> at each candidate interval, joints '
        'known to contain initial cracks are excavated and treated with perfect '
        'observation—no ILI, POD, or measurement error. <b>Pre-posterior method:</b> '
        'ILI detection and measured crack sizes determine whether treatment occurs.</div>',
        unsafe_allow_html=True,
    )

    prior_intervals = (
        list(
            range(
                int(prior_interval_start),
                int(prior_interval_end) + 1,
                int(prior_interval_step),
            )
        )
        if prior_interval_start <= prior_interval_end
        else []
    )
    ili_intervals = (
        list(
            range(
                int(ili_interval_start),
                int(ili_interval_end) + 1,
                int(ili_interval_step),
            )
        )
        if ili_interval_start <= ili_interval_end
        else []
    )
    growth_properties = {
        "alpha": {"mean": mean_g, "std": std_g, "distribution": "Normal"},
        "Neq": {"mean": mean_neq, "std": std_neq, "distribution": "Normal"},
        "C": {"mean": mean_c, "std": std_c, "distribution": "Lognormal"},
    }

    try:
        joints = planning_joints(handoff, growth_properties, default_birth_rate,
                                 use_segment_costs=use_segment_costs)
        total_joints = sum(joint["count"] for joint in joints)
        total_initial_cracks = sum(
            joint["count"] * len(joint["cracks"]) for joint in joints
        )
        summary = pd.DataFrame(
            [
                {
                    "Joint/group": joint["name"],
                    "Count": joint["count"],
                    "Cracks per joint": len(joint["cracks"]),
                    "Birth rate (cracks/joint-year)": joint["birth_rate"],
                }
                for joint in joints
            ]
        )
        with st.expander("Parsed model input", expanded=False):
            st.dataframe(summary, width="stretch", hide_index=True)
    except ValueError as exc:
        st.error(str(exc))
        joints = []
        total_joints = total_initial_cracks = 0

    custom_plan_enabled = False
    custom_prior_per_joint = False
    custom_schedule_config = None
    custom_schedule_error = None

    with st.expander("User-defined schedules", expanded=False):
        st.caption(
            "Evaluate one named plan for each method in addition to the fixed-interval "
            "comparison. Enter years such as 2, 10, 15. These plans are evaluated as "
            "given; they are not added to the fixed-interval optimization curves."
        )
        custom_plan_enabled = settings.checkbox(
            "Enable user-defined plan evaluation", value=False
        )
        custom_ili_years = []
        custom_prior_years = []
        custom_joint_schedule_map = None
        custom_prior_description = ""
        custom_ili_description = ""
        custom_prior_plan_name = "Plan 1_no_ILI"
        custom_ili_plan_name = "Plan 1_ILI"
        custom_joint_schedule_records = []

        if custom_plan_enabled:
            name_cols = st.columns(2)
            with name_cols[0]:
                custom_prior_plan_name = settings.text_input(
                    "Prior plan name", value="Plan 1_no_ILI"
                )
                custom_prior_per_joint = settings.checkbox(
                    "Set a separate excavation schedule for each cracked joint",
                    value=False,
                )
            with name_cols[1]:
                custom_ili_plan_name = settings.text_input(
                    "ILI plan name", value="Plan 1_ILI"
                )
                default_ili_years = ", ".join(
                    str(year) for year in range(
                        int(ili_interval_start), int(horizon) + 1, int(ili_interval_start)
                    )
                ) or str(min(int(ili_interval_start), int(horizon)))
                custom_ili_year_text = settings.text_input(
                    "ILI inspection years for the whole system (comma-separated)",
                    value=default_ili_years,
                    help="The same ILI years apply across the full pipeline.",
                )

            cracked_joint_models = [joint for joint in joints if joint.get("cracks")]
            if custom_prior_per_joint:
                st.caption(
                    "Enter either manual excavation years or one fixed interval in each row. "
                    "The table has one row per cracked physical joint. Crack-free groups are "
                    "not assigned excavations in the prior method."
                )
                if not cracked_joint_models:
                    st.info("No initially cracked joints are present in this saved dataset.")
                else:
                    default_prior_interval = min(
                        max(1, int(prior_interval_start)), int(horizon)
                    )
                    default_rows = [
                        {
                            "Cracked joint": joint["name"],
                            "Manual excavation years": "",
                            "Fixed interval (years)": default_prior_interval,
                        }
                        for joint in cracked_joint_models
                    ]
                    schedule_field = "prior_joint_schedule_" + handoff["dataset_id"][:12]
                    saved_planning = st.session_state.setdefault("static_planning_settings", {})
                    saved_rows = saved_planning.get(schedule_field)
                    joint_labels = [row["Cracked joint"] for row in default_rows]
                    if (isinstance(saved_rows, list)
                            and [str(row.get("Cracked joint", "")) for row in saved_rows] == joint_labels):
                        editor_rows = saved_rows
                    else:
                        editor_rows = default_rows
                    schedule_editor_key = "static_planning_editor_" + handoff["dataset_id"][:12]
                    schedule_editor = st.data_editor(
                        pd.DataFrame(editor_rows),
                        key=schedule_editor_key,
                        hide_index=True,
                        disabled=["Cracked joint"],
                        num_rows="fixed",
                        width="stretch",
                        column_config={
                            "Cracked joint": st.column_config.TextColumn(
                                "Cracked joint", help="Each row represents one physical pipe joint."
                            ),
                            "Manual excavation years": st.column_config.TextColumn(
                                "Manual excavation years",
                                help="Optional comma-separated years, such as 3, 5, 20.",
                                required=False,
                            ),
                            "Fixed interval (years)": st.column_config.NumberColumn(
                                "Fixed interval (years)",
                                min_value=1,
                                max_value=int(horizon),
                                step=1,
                                format="%d",
                                required=False,
                                help="Enter one interval, for example 5, to excavate at years 5, 10, 15, and so on.",
                            ),
                        },
                    )
                    custom_joint_schedule_records = schedule_editor.to_dict(orient="records")
                    saved_planning[schedule_field] = custom_joint_schedule_records

            prior_default_years = ", ".join(
                str(year) for year in range(
                    int(prior_interval_start), int(horizon) + 1, int(prior_interval_start)
                )
            ) or str(min(int(prior_interval_start), int(horizon)))
            if not custom_prior_per_joint:
                custom_prior_year_text = settings.text_input(
                    "Prior excavation years for all cracked joints (comma-separated)",
                    value=prior_default_years,
                    help="This common prior schedule applies to each initially cracked joint.",
                )

            try:
                custom_ili_years = parse_manual_years(
                    custom_ili_year_text, "ILI inspection schedule", int(horizon)
                )
                if custom_prior_per_joint:
                    if not cracked_joint_models:
                        raise ValueError("Per-joint excavation schedules require at least one cracked joint.")
                    custom_joint_schedule_map = {}
                    descriptions = []
                    for row in custom_joint_schedule_records:
                        joint_name = str(row.get("Cracked joint", ""))
                        manual_value = row.get("Manual excavation years", "")
                        if manual_value is None or pd.isna(manual_value):
                            manual_value = ""
                        manual_text = str(manual_value).strip()
                        fixed_value = row.get("Fixed interval (years)")
                        if fixed_value is not None and pd.isna(fixed_value):
                            fixed_value = None
                        if manual_text and fixed_value is not None:
                            raise ValueError(
                                f"{joint_name}: enter manual years or a fixed interval, not both."
                            )
                        if manual_text:
                            years = parse_manual_years(
                                manual_text, f"{joint_name} schedule", int(horizon)
                            )
                            descriptions.append(f"{joint_name}: " + ", ".join(map(str, years)))
                        elif fixed_value is not None:
                            fixed_number = float(fixed_value)
                            if not np.isfinite(fixed_number) or not fixed_number.is_integer():
                                raise ValueError(f"{joint_name}: fixed interval must be a whole number of years.")
                            interval_years = int(fixed_number)
                            if interval_years < 1 or interval_years > int(horizon):
                                raise ValueError(
                                    f"{joint_name}: fixed interval must be from 1 to {int(horizon)} years."
                                )
                            years = list(range(interval_years, int(horizon) + 1, interval_years))
                            descriptions.append(f"{joint_name}: every {interval_years} years")
                        else:
                            raise ValueError(
                                f"{joint_name}: enter manual excavation years or a fixed interval."
                            )
                        custom_joint_schedule_map[joint_name] = years
                    custom_prior_years = sorted({
                        year for years in custom_joint_schedule_map.values() for year in years
                    })
                    custom_prior_description = "; ".join(descriptions)
                else:
                    custom_prior_years = parse_manual_years(
                        custom_prior_year_text, "Prior excavation schedule", int(horizon)
                    )
                    custom_prior_description = ", ".join(map(str, custom_prior_years))
                custom_ili_description = ", ".join(map(str, custom_ili_years))
                custom_schedule_config = {
                    "prior_name": custom_prior_plan_name.strip() or "Prior plan",
                    "ili_name": custom_ili_plan_name.strip() or "ILI plan",
                    "prior_years": custom_prior_years,
                    "prior_by_joint": custom_joint_schedule_map,
                    "prior_description": custom_prior_description,
                    "ili_years": custom_ili_years,
                    "ili_description": custom_ili_description,
                }
            except (TypeError, ValueError) as exc:
                custom_schedule_error = str(exc)
                st.error(custom_schedule_error)


    expected_new_cracks = sum(
        joint["count"] * joint["birth_rate"] * horizon for joint in joints
    )
    metric_columns = st.columns(5)
    metric_columns[0].metric("Physical joints", total_joints)
    metric_columns[1].metric("Initial cracks", total_initial_cracks)
    metric_columns[2].metric(
        "Expected new cracks",
        f"{expected_new_cracks:.3f}",
        help="Poisson mean over all represented joints and the full analysis horizon.",
    )
    metric_columns[3].metric(
        "Prior / ILI intervals", f"{len(prior_intervals)} / {len(ili_intervals)}"
    )
    metric_columns[4].metric("Monte Carlo samples", f"{samples:,}")

    simulation_units = len(joints)
    work_units = (
        simulation_units
        * samples
        * (horizon + 1)
        * max(len(prior_intervals) + len(ili_intervals), 1)
    )
    actual_batch_size = effective_batch_size(joints, horizon, 1, sample_batch_size)
    st.caption(f'Memory-efficient execution: up to {min(samples,actual_batch_size):,} samples per batch. '
        'All requested samples are processed. Completed batches and intervals can be resumed in this session. '
        'A server restart clears session checkpoints.')
    if work_units > 2_000_000:
        st.info('This is a larger calculation. Batching reduces peak memory, but CPU time still increases with '
            'samples, defects, analysis years and interval candidates. Shared hosting may remain a bottleneck.')

    model = {
        "samples": int(samples),
        "batch_size": int(actual_batch_size),
        "execution_revision": EXECUTION_REVISION,
        "horizon": int(horizon),
        "seed": int(random_seed),
        "birth_rate": float(default_birth_rate),
        "initial_length_std": float(initial_length_std),
        "initial_depth_std": float(initial_depth_std),
        "length_error": float(length_error),
        "depth_error": float(depth_error),
        "q_pod": float(q_pod),
        "costs": {
            "Cr1": float(repair_1_cost),
            "Cr2": float(repair_2_cost),
            "Cf_leak": float(leak_cost),
            "Cf_burst": float(burst_cost),
            "inspection_cost_per_km": float(inspection_cost_per_km),
            "pipe_length_km": float(pipe_length),
            "rate": float(discount_percent) / 100,
        },
        "sim": {
            "dS": float(delta_s),
            "m": float(paris_m),
            "Di": 20 * 25.4,  # Legacy fallback; saved per-joint OD takes precedence.
            "FPR_rep1": float(fpr_rep1),
            "D_rep1_fraction": float(d_rep1) / 100,
            "FPR_rep2": float(fpr_rep2),
            "D_rep2_fraction": float(d_rep2) / 100,
            "lifetime_arr": [0, int(coat_period), int(sleeve_period)],
            "df_arr": [1, float(coat_df), float(sleeve_df)],
            "residual_depth_recoat_mm": [float(recoat_depth_min), float(recoat_depth_max)],
            "residual_depth_sleeve_mm": [float(sleeve_depth_min), float(sleeve_depth_max)],
            "threshold": 1e-3,
            "max_annual_leak_pof": (
                float(max_annual_leak_pof) if safety_criteria_valid else np.nan
            ),
            "max_annual_burst_pof": (
                float(max_annual_burst_pof) if safety_criteria_valid else np.nan
            ),
            "pod_model": pod_model,
            "pod_depth_coefficient": float(q_pod),
            "pod_length_coefficient": float(q_length_pod),
            "resample_growth_each_step": False,
        },
    }

    custom_plan_signature = None
    if custom_plan_enabled and custom_schedule_config is not None:
        custom_plan_signature = hashlib.sha256(
            repr((handoff["dataset_id"], model, joints, custom_schedule_config,
                  pipeline_class)).encode()
        ).hexdigest()

    run_signature = hashlib.sha256(repr((handoff["dataset_id"], model, joints,
        prior_intervals, ili_intervals, pipeline_class)).encode()).hexdigest()
    current_safety_signature = (
        pipeline_class,
        float(max_annual_leak_pof) if safety_criteria_valid else None,
        float(max_annual_burst_pof) if safety_criteria_valid else None,
    )
    current_interval_signature = (tuple(prior_intervals), tuple(ili_intervals))
    run_disabled = (
        not joints
        or not prior_intervals
        or not ili_intervals
        or not safety_criteria_valid
    )
    job = st.session_state.get('integrated_planning_job')
    resumable = bool(job and job.get('run_signature') == run_signature and not job.get('complete'))
    if resumable:
        finished_prior, finished_ili = len(job.get('prior_results', [])), len(job.get('ili_results', []))
        attempted = sum(checkpoint.get('processed', 0) for checkpoint in job.get('checkpoints', {}).values())
        st.info(f'Unfinished run: {finished_prior}/{len(prior_intervals)} prior intervals and '
            f'{finished_ili}/{len(ili_intervals)} ILI intervals completed. '
            f'{attempted:,} candidate-samples processed. Resume to continue from the last completed batch.')
        partial = [dict(Method=label, Interval=r['interval'], Cost=r['total_cpp'], Safe=r['is_safe'])
            for label, key in [('Prior','prior_results'),('ILI-informed','ili_results')]
            for r in job.get(key, [])]
        if partial:
            st.download_button('Download completed intervals (partial run)',
                pd.DataFrame(partial).to_csv(index=False), 'completed_planning_intervals.csv', 'text/csv')
    if st.button(
        "Resume prior + pre-posterior comparison" if resumable else "Run prior + pre-posterior comparison",
        type="primary", disabled=run_disabled, key='run_integrated_planning_comparison'
    ):
        if not resumable:
            job = dict(run_signature=run_signature, prior_results=[], ili_results=[], checkpoints={}, complete=False)
            st.session_state['integrated_planning_job'] = job
        try:
            with st.spinner("Running the prior excavation schedules…"):
                prior_results, prior_log = run_interval_study(
                    joints, prior_intervals, model, EXCAVATION_DECISION_MODE, job
                )
            with st.spinner("Running the ILI-informed schedules…"):
                ili_results, ili_log = run_interval_study(
                    joints, ili_intervals, model, ILI_DECISION_MODE, job
                )
            st.session_state["integrated_planning_comparison"] = {
                "prior_results": prior_results,
                "ili_results": ili_results,
                "prior_log": prior_log,
                "ili_log": ili_log,
                "joint_count": total_joints,
                "sample_count": samples,
                "pipeline_class": pipeline_class,
                "max_annual_leak_pof": float(max_annual_leak_pof),
                "max_annual_burst_pof": float(max_annual_burst_pof),
                "safety_signature": current_safety_signature,
                "interval_signature": current_interval_signature,
                "prior_intervals": prior_intervals,
                "ili_intervals": ili_intervals,
                "dataset_id": handoff["dataset_id"],
                "run_signature": run_signature,

            }
            job['complete'] = True
        except Exception as exc:
            st.error('The calculation did not finish. Completed batches are kept in this session. '
                'Select Resume to continue; changing inputs starts a new study.')
            st.exception(exc)


    if custom_plan_enabled and custom_schedule_config is not None:
        st.markdown("#### User-defined plan evaluation")
        st.caption(
            "This evaluates the two schedules exactly as entered. The prior plan may "
            "have different excavation years by joint; ILI remains system-wide."
        )
        custom_job = st.session_state.get("integrated_custom_schedule_job")
        custom_resumable = bool(
            custom_job
            and custom_job.get("signature") == custom_plan_signature
            and not custom_job.get("complete")
        )
        if st.button(
            "Resume user-defined plans" if custom_resumable else "Run user-defined plans",
            type="secondary",
            disabled=not joints or not safety_criteria_valid or custom_schedule_error is not None,
            key="run_integrated_custom_schedule_plans",
        ):
            if not custom_job or custom_job.get("signature") != custom_plan_signature:
                custom_job = {
                    "signature": custom_plan_signature,
                    "checkpoints": {},
                    "results": {},
                    "complete": False,
                }
                st.session_state["integrated_custom_schedule_job"] = custom_job
            progress = st.progress(0, text="Preparing user-defined plan simulations…")
            custom_runs = [
                (
                    "prior",
                    custom_schedule_config["prior_name"],
                    EXCAVATION_DECISION_MODE,
                    custom_schedule_config["prior_years"],
                    custom_schedule_config["prior_by_joint"],
                ),
                (
                    "ili",
                    custom_schedule_config["ili_name"],
                    ILI_DECISION_MODE,
                    custom_schedule_config["ili_years"],
                    None,
                ),
            ]
            try:
                for run_index, (run_key, plan_name, decision_mode, years, joint_map) in enumerate(custom_runs):
                    if run_key in custom_job["results"]:
                        continue
                    sim = copy.deepcopy(model["sim"])
                    sim.pop("inspection_interval", None)
                    sim["inspection_times"] = list(years)
                    if joint_map is not None:
                        sim["joint_inspection_times"] = joint_map
                    else:
                        sim.pop("joint_inspection_times", None)
                    checkpoint = custom_job["checkpoints"].setdefault(run_key, {})

                    def report(done, requested, retained, index=run_index, name=plan_name):
                        progress.progress(
                            (index + done / requested) / len(custom_runs),
                            text=f"{name}: {done:,}/{requested:,} samples processed "
                                 f"({retained:,} retained).",
                        )

                    raw = run_batched_flexible_simulation(
                        "equidistant",
                        model["horizon"],
                        1,
                        model["samples"],
                        joints,
                        model["costs"],
                        sim,
                        [model["depth_error"], model["length_error"]],
                        model["q_pod"],
                        default_birth_rate=model["birth_rate"],
                        property_seed=model["seed"],
                        crack_length_std=model["initial_length_std"],
                        crack_depth_std=model["initial_depth_std"],
                        track_debug=False,
                        decision_mode=decision_mode,
                        batch_size=model["batch_size"],
                        state=checkpoint,
                        on_progress=report,
                    )
                    result = unpack_result(raw, "User-defined schedule", decision_mode, sim)
                    result["plan_name"] = plan_name
                    result["schedule_description"] = (
                        custom_schedule_config["prior_description"]
                        if run_key == "prior"
                        else custom_schedule_config["ili_description"]
                    )
                    custom_job["results"][run_key] = result
                custom_job["complete"] = True
                progress.progress(1.0, text="User-defined plans complete")
            except Exception as exc:
                st.error(
                    "The user-defined plan run did not finish. Completed batches are saved "
                    "in this session; select Resume to continue."
                )
                st.exception(exc)

        custom_job = st.session_state.get("integrated_custom_schedule_job")
        if custom_job and custom_job.get("signature") == custom_plan_signature:
            custom_results = custom_job.get("results", {})
            if "prior" in custom_results and "ili" in custom_results:
                result_rows = []
                for run_key in ("prior", "ili"):
                    result = custom_results[run_key]
                    result_rows.append({
                        "Plan": result["plan_name"],
                        "Intervention years": result["schedule_description"],
                        "Expected lifecycle cost ($M)": result["total_cpp"],
                        "Failure cost Cf ($M)": result["failure_cost"],
                        "Repair cost Cr ($M)": result["repair_cost"],
                        "ILI cost Ci ($M)": result["inspection_cost"],
                        "Safety": "Safe" if result["is_safe"] else "Unsafe",
                        "Peak annual PfL": float(np.max(result["leak_annual_pof"])),
                        "Peak annual PfB": float(np.max(result["burst_annual_pof"])),
                    })
                custom_table = pd.DataFrame(result_rows)
                st.dataframe(
                    custom_table.style.format({
                        "Expected lifecycle cost ($M)": "{:.4f}",
                        "Failure cost Cf ($M)": "{:.4f}",
                        "Repair cost Cr ($M)": "{:.4f}",
                        "ILI cost Ci ($M)": "{:.4f}",
                        "Peak annual PfL": "{:.3e}",
                        "Peak annual PfB": "{:.3e}",
                    }),
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    "Safe means both peak annual whole-pipeline probabilities stay within "
                    "the selected limits over the full horizon. These manual plans are "
                    "separate from the fixed-interval cost-optimal search."
                )
            elif not custom_job.get("complete"):
                completed = ", ".join(sorted(custom_results)) or "none yet"
                st.info(f"Saved user-defined plan progress. Completed plans: {completed}.")

    study = st.session_state.get("integrated_planning_comparison")
    if study and study.get("run_signature") != run_signature:
        st.info("The saved dataset or planning settings changed. Run the comparison again to update the results.")
        study = None
    if study:
        prior_results = study["prior_results"]
        ili_results = study["ili_results"]
        prior_cost_optimal = select_lowest_cost_result(prior_results)
        ili_cost_optimal = select_lowest_cost_result(ili_results)
        prior_safe, prior_has_safe = select_optimal_result(prior_results)
        ili_safe, ili_has_safe = select_optimal_result(ili_results)
        voi = (
            calculate_value_of_information(prior_safe, ili_safe)
            if prior_safe is not None and ili_safe is not None
            else None
        )

        st.subheader("Cost-optimal and safe scheduling results")
        st.caption("Source dataset: " + study["dataset_id"][:10])
        with st.expander('Pipeline joint reliability profile', expanded=True):
            method = st.radio('Map planning method', ['Prior excavation', 'ILI-informed'], horizontal=True)
            candidates = prior_results if method == 'Prior excavation' else ili_results
            preferred = prior_safe if method == 'Prior excavation' else ili_safe
            intervals = [r['interval'] for r in candidates]
            selected = st.selectbox('Map interval (years)', intervals,
                index=intervals.index(preferred['interval']) if preferred else 0)
            result = next(r for r in candidates if r['interval'] == selected)
            st.caption('Red: above a selected POF limit. Yellow: 50–100% of a limit. '
                'Green: below 50%. A 1 km window slides by one nominal joint; boundary '
                'joints are included in full. These are reliability indicators, without '
                'consequences. The scheduling safety check remains the existing whole-route '
                'calculation; this display is not a verified CSA compliance assessment.')
            try:
                windows, spatial = sliding_window_reliability(result, handoff)
                st_folium(reliability_map(handoff['project']['route'], spatial), height=450,
                    returned_objects=[], key=f'integrated_result_map_{method}_{selected}')
                st.markdown('**Sliding one KM results**')
                st.dataframe(windows.sort_values('limit_ratio', ascending=False), hide_index=True)
                st.download_button('Download sliding 1 km results CSV', windows.to_csv(index=False),
                    'planning_sliding_1km_results.csv', 'text/csv')
                with st.expander('Individual joint results'):
                    st.dataframe(spatial, hide_index=True)
                    st.download_button('Download joint reliability CSV', spatial.to_csv(index=False),
                        'planning_joint_reliability.csv', 'text/csv')
            except ValueError as exc:
                st.warning('The probability map is unavailable for this run: ' + str(exc))
        retained = [(r['retained_samples'], r['requested_samples']) for r in prior_results + ili_results]
        st.caption('Time-zero survival conditioning: '
            + ', '.join(f'{n}/{total} samples retained' for n,total in sorted(set(retained)))
            + '. Future planning results are conditional on initial survival.')
        st.caption(
            f"{study['pipeline_class']} safety criteria: "
            f"PfL ≤ {study['max_annual_leak_pof']:.1e}; "
            f"PfB ≤ {study['max_annual_burst_pof']:.1e}."
        )
        st.html(
            recommendation_matrix(
                prior_cost_optimal, prior_safe, ili_cost_optimal, ili_safe
            )
        )
        with st.expander('Why an interval is Safe or Unsafe'):
            st.caption('Safety is checked at every simulated year over the full analysis horizon, '
                'including years after the first inspection. The table identifies the first '
                'exceedance and the peak values used for that decision.')
            safety_table = pd.DataFrame(interval_safety_rows(prior_results, 'Prior excavation')
                + interval_safety_rows(ili_results, 'ILI-informed'))
            st.dataframe(safety_table.style.format({
                'Peak annual whole-pipeline PfL': '{:.3e}',
                'Peak annual whole-pipeline PfB': '{:.3e}',
                'First limit exceedance (year)': '{:.0f}',
            }, na_rep='—'), hide_index=True, width='stretch')
            st.download_button('Download interval safety diagnostics', safety_table.to_csv(index=False),
                'planning_interval_safety.csv', 'text/csv')
            st.caption(f'Joint/group details below use the map selection: {method}, '
                f'{selected:g}-year interval. Each group is evaluated alone over the same '
                f'{pipe_length:.3f} km route; these group values cannot be added together.')
            groups_table = pd.DataFrame(joint_safety_rows(result, joints, pipe_length))
            st.dataframe(groups_table.style.format({
                'Peak group PfL / km-year': '{:.3e}',
                'Peak group PfB / km-year': '{:.3e}',
                'Approx. one-event increment / km': '{:.3e}',
            }), hide_index=True, width='stretch')
            st.caption('Initially crack-free groups can govern the result when new cracks initiate. '
                'Their common marginal POF is estimated from the retained samples and combined '
                'using the number of physical joints represented. The one-event increment is '
                'a sampling-resolution indicator, not a confidence interval.')
            st.download_button('Download joint/group probability diagnostics', groups_table.to_csv(index=False),
                'planning_joint_group_probabilities.csv', 'text/csv')
        if voi is not None:
            if voi["voi"] > 0:
                voi_class = "voi-positive"
            elif voi["voi"] < 0:
                voi_class = "voi-negative"
            else:
                voi_class = "voi-neutral"
            st.html(
                f'<div class="voi-card {voi_class}">'
                '<div class="voi-label">Net VoI of ILI</div>'
                f'<div class="voi-value">${voi["voi"]:.4f}M</div>'
                f'<div class="voi-message">{voi["interpretation"]}</div>'
                "</div>"
            )
            st.markdown(
                '<div class="note"><b>VoI = minimum safe prior excavation cost − minimum '
                'safe ILI-informed cost.</b> Each recommendation is the lowest-cost candidate '
                'that satisfies both safety criteria. The ILI-informed cost already includes '
                'discounted ILI inspection costs.</div>',
                unsafe_allow_html=True,
            )
        if not prior_has_safe or not ili_has_safe:
            missing = []
            if not prior_has_safe:
                missing.append("prior excavation")
            if not ili_has_safe:
                missing.append("ILI-informed")
            st.warning(
                "Minimum-cost safe interval: **Not found** for "
                + " and ".join(missing)
                + " within the tested range. The cost-optimal interval is still shown above "
                + "with its Safe/Unsafe status."
            )

        comparison_tab, prior_tab, ili_tab = st.tabs(
            ["VoI comparison", "Prior excavation (no ILI)", "Pre-posterior (ILI)"]
        )
        with comparison_tab:
            show_comparison_cost_figure(prior_results, ili_results)
            st.caption(
                "Each tested ILI interval is compared with the minimum-cost safe prior "
                "excavation solution. ILI is economically justified only when that ILI "
                "interval is safe and has a lower expected lifecycle cost."
            )
            combined = comparison_table(prior_safe, ili_results)
            combined["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                combined.style.format(
                    {
                        "Prior safe cost ($M)": format_optional_decimal,
                        "ILI cost ($M)": "{:.6f}",
                        "Cost difference / VoI ($M)": format_optional_decimal,
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Download VoI comparison",
                combined.to_csv(index=False).encode("utf-8"),
                "ili_intervals_vs_prior_safe.csv",
                "text/csv",
            )

        with prior_tab:
            prior_columns = st.columns(5)
            prior_columns[0].metric(
                "Cost-optimal interval",
                f"{prior_cost_optimal['interval']} years",
            )
            prior_columns[1].metric(
                "Lowest Cprior",
                f"${prior_cost_optimal['total_cpp']:.4f}M",
            )
            prior_columns[2].metric(
                "Safety at cost optimum",
                _safety_label(prior_cost_optimal),
            )
            prior_columns[3].metric(
                "Safe interval",
                f"{prior_safe['interval']} years" if prior_safe else "Not found",
            )
            prior_columns[4].metric(
                "Safe Cprior",
                f"${prior_safe['total_cpp']:.4f}M" if prior_safe else "—",
            )
            show_selectable_cost_figure(
                prior_results,
                "Prior lifecycle cost versus excavation interval",
                "Excavation interval (years)",
                "Cprior",
                "prior_cost_selection",
            )
            show_figure(annual_pof_figure(prior_cost_optimal, "Excavation"))
            prior_table = results_table(prior_results, "Cprior")
            prior_table["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                prior_table.style.format(
                    {
                        "Total Cprior ($M)": "{:.6f}",
                        "Cf — failure ($M)": "{:.6f}",
                        "Cr — repair ($M)": "{:.6f}",
                        "ILI inspection ($M)": "{:.6f}",
                        "Expected repairs": "{:.4f}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Download prior excavation results",
                prior_table.to_csv(index=False).encode("utf-8"),
                "prior_excavation_results.csv",
                "text/csv",
            )
            with st.expander("Prior simulation messages"):
                st.code(study["prior_log"] or "No simulation messages.")

        with ili_tab:
            ili_columns = st.columns(5)
            ili_columns[0].metric(
                "Cost-optimal interval",
                f"{ili_cost_optimal['interval']} years",
            )
            ili_columns[1].metric(
                "Lowest Cpp",
                f"${ili_cost_optimal['total_cpp']:.4f}M",
            )
            ili_columns[2].metric(
                "Safety at cost optimum",
                _safety_label(ili_cost_optimal),
            )
            ili_columns[3].metric(
                "Safe interval",
                f"{ili_safe['interval']} years" if ili_safe else "Not found",
            )
            ili_columns[4].metric(
                "Safe Cpp",
                f"${ili_safe['total_cpp']:.4f}M" if ili_safe else "—",
            )
            show_selectable_cost_figure(
                ili_results,
                "Pre-posterior lifecycle cost versus ILI interval",
                "ILI interval (years)",
                "Cpp",
                "ili_cost_selection",
            )
            show_figure(annual_pof_figure(ili_cost_optimal, "ILI inspection"))
            ili_table = results_table(ili_results, "Cpp")
            ili_table["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                ili_table.style.format(
                    {
                        "Total Cpp ($M)": "{:.6f}",
                        "Cf — failure ($M)": "{:.6f}",
                        "Cr — repair ($M)": "{:.6f}",
                        "ILI inspection ($M)": "{:.6f}",
                        "Expected repairs": "{:.4f}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Download ILI-informed results",
                ili_table.to_csv(index=False).encode("utf-8"),
                "ili_informed_results.csv",
                "text/csv",
            )
            with st.expander("ILI simulation messages"):
                st.code(study["ili_log"] or "No simulation messages.")
    else:
        st.info(
            "Adjust the inputs if needed, then select **Run prior + pre-posterior comparison**."
        )
