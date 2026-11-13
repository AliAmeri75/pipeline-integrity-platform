"""Fixed-interval and user-defined planning inside ALIRIM's shared-data session.

Simulation/results UI adapted from AliAmeri75/pipeline-inspection-app,
inspection_planner.py; shared-data integration replaces its separate input editor.
"""


def render_planner(*, show_header=True):
    import contextlib
    import copy
    import hashlib
    import html
    import io
    from threading import Event
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
        calculate_value_of_information,
        format_optional_decimal, select_lowest_cost_result, select_optimal_result,
    )
    from project_editor import get_project
    from planning_project import planning_handoff, planning_joints
    from profile_map import point_at_chainage
    from inspection_planning.risk_map import sliding_window_reliability, reliability_map
    from inspection_planning.schedule_editor import (
        parse_manual_years, prior_candidates, render_ili_rows, render_prior_plans,
    )
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


    def run_interval_study(joints, intervals, model, decision_mode, job):
        method_label = (
            "prior excavation"
            if decision_mode == EXCAVATION_DECISION_MODE
            else "ILI-informed inspection"
        )
        result_key = "prior_results" if decision_mode == EXCAVATION_DECISION_MODE else "ili_results"
        log_key = "prior_log" if decision_mode == EXCAVATION_DECISION_MODE else "ili_log"
        results = job.setdefault(result_key, [])
        if not intervals:
            return results, job.get(log_key, "")
        progress = st.progress(0, text=f"Preparing {method_label} simulations…")
        log = io.StringIO()
        log.write(job.get(log_key, ""))
        intervals = list(intervals)
        for index, interval in enumerate(intervals):
            candidate_id = f"{decision_mode}-fixed-{interval}"
            if any(result.get("candidate_id") == candidate_id for result in results):
                continue
            sim = copy.deepcopy(model["sim"])
            sim["inspection_interval"] = interval
            checkpoint = job.setdefault("checkpoints", {}).setdefault(
                f"{decision_mode}:fixed:{interval}", {}
            )

            def report(done, requested, retained):
                progress.progress(
                    (index + done / requested) / max(len(intervals), 1),
                    text=f"{method_label.capitalize()}: {interval}-year interval, "
                         f"{done:,}/{requested:,} samples processed ({retained:,} retained).",
                )

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
                    batch_size=model["batch_size"],
                    state=checkpoint,
                    on_progress=report,
                )
            result = unpack_result(raw, interval, decision_mode, sim)
            result.update(
                candidate_id=candidate_id,
                plan_name=f"Fixed interval — {interval} years",
                schedule_description=f"Every {interval} years",
                chart_interval=float(interval),
                is_user_defined=False,
            )
            results.append(result)
            checkpoint.clear()
            job[log_key] = log.getvalue()
        progress.progress(1.0, text=f"{method_label.capitalize()} candidates complete")
        return results, log.getvalue()


    def run_user_defined_studies(joints, plans, model, decision_mode, job):
        """Run each named schedule sequentially through the same batched engine."""
        result_key = "prior_results" if decision_mode == EXCAVATION_DECISION_MODE else "ili_results"
        log_key = "prior_log" if decision_mode == EXCAVATION_DECISION_MODE else "ili_log"
        method_label = "prior excavation" if decision_mode == EXCAVATION_DECISION_MODE else "ILI-informed"
        results = job.setdefault(result_key, [])
        plans = list(plans)
        if not plans:
            return results, job.get(log_key, "")
        progress = st.progress(0, text=f"Preparing user-defined {method_label} plans…")
        log = io.StringIO()
        log.write(job.get(log_key, ""))
        for index, plan in enumerate(plans):
            candidate_id = plan["candidate_id"]
            if any(result.get("candidate_id") == candidate_id for result in results):
                continue
            sim = copy.deepcopy(model["sim"])
            sim.pop("inspection_interval", None)
            sim["inspection_times"] = list(plan["years"])
            if plan.get("joint_schedules") is not None:
                sim["joint_inspection_times"] = plan["joint_schedules"]
            else:
                sim.pop("joint_inspection_times", None)
            checkpoint = job.setdefault("checkpoints", {}).setdefault(
                f"{decision_mode}:user:{candidate_id}", {}
            )

            def report(done, requested, retained):
                progress.progress(
                    (index + done / requested) / max(len(plans), 1),
                    text=f"{plan['plan_name']}: {done:,}/{requested:,} samples "
                         f"processed ({retained:,} retained).",
                )

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
                    batch_size=model["batch_size"],
                    state=checkpoint,
                    on_progress=report,
                )
            result = unpack_result(raw, plan["chart_interval"], decision_mode, sim)
            result.update(
                candidate_id=candidate_id,
                plan_name=plan["plan_name"],
                schedule_description=plan["schedule_description"],
                chart_interval=float(plan["chart_interval"]),
                is_user_defined=True,
            )
            results.append(result)
            checkpoint.clear()
            job[log_key] = log.getvalue()
        progress.progress(1.0, text=f"User-defined {method_label} plans complete")
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


    def _plan_label(result):
        if result.get("is_user_defined"):
            return f"{result.get('plan_name', 'User-defined plan')} — {result.get('schedule_description', '')}"
        return f"Fixed interval — {result['interval']:g} years"


    def _chart_interval(result):
        return float(result.get("chart_interval", result["interval"]))


    def recommendation_matrix(prior_cost_optimal, prior_safe, ili_cost_optimal, ili_safe):
        """Compare the lowest-cost and lowest-cost safe plans for both methods."""

        def row(method, cost_optimal, safe_result):
            safety = _safety_label(cost_optimal)
            badge_class = "badge-safe" if cost_optimal["is_safe"] else "badge-unsafe"
            safe_plan = (
                html.escape(_plan_label(safe_result))
                if safe_result is not None
                else '<span class="not-found">Not found</span>'
            )
            safe_cost = (
                "$" + f"{safe_result['total_cpp']:.4f}M"
                if safe_result is not None
                else "—"
            )
            return (
                "<tr>"
                f"<td>{method}</td>"
                f"<td><b>{html.escape(_plan_label(cost_optimal))}</b></td>"
                "<td>$" + f"{cost_optimal['total_cpp']:.4f}M</td>"
                f'<td><span class="{badge_class}">{safety}</span></td>'
                f"<td>{safe_plan}</td>"
                f"<td>{safe_cost}</td>"
                "</tr>"
            )

        prior_row = row("Prior excavation (no ILI)", prior_cost_optimal, prior_safe)
        ili_row = row("Pre-posterior (ILI-informed)", ili_cost_optimal, ili_safe)
        return (
            '<div class="result-matrix"><table><thead><tr>'
            "<th>Planning method</th>"
            "<th>Cost-optimal plan</th>"
            "<th>Lowest cost</th>"
            "<th>Safety at cost optimum</th>"
            "<th>Minimum-cost safe plan</th>"
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
                    _plan_label(result),
                    result.get("schedule_description", f"Every {result['interval']} years"),
                    result.get("candidate_id", ""),
                ]
                for result in results
            ],
            dtype=object,
        )


    def _cost_hover_template(total_label):
        return (
            "<b>%{customdata[5]}</b><br>"
            "Schedule: %{customdata[6]}<br>"
            + total_label + ": $%{customdata[0]:.6f}M<br>"
            "Cf (failure): $%{customdata[1]:.6f}M<br>"
            "Cr (repair): $%{customdata[2]:.6f}M<br>"
            "Ci (inspection): $%{customdata[3]:.6f}M<br>"
            "Safety: <b>%{customdata[4]}</b><extra></extra>"
        )


    def select_cost_plans(results, label, key, study_signature, *, show_method=False):
        labels = {}
        for result in results:
            name = result["plan_name"] if result.get("is_user_defined") else _plan_label(result)
            if show_method:
                method = "Prior" if result["decision_mode"] == EXCAVATION_DECISION_MODE else "ILI"
                name = f"{method} — {name}"
            labels[result["candidate_id"]] = name

        ids = list(labels)
        visible_ids = set(st.multiselect(
            label, options=ids, default=ids, format_func=labels.__getitem__,
            key=f"{key}_plans_{study_signature}",
        ))
        # A changed set of points invalidates a previous Plotly point selection.
        selection = hashlib.sha256(repr(sorted(visible_ids)).encode()).hexdigest()[:16]
        return visible_ids, f"{key}_{study_signature}_{selection}"


    def cost_plan_groups(results, visible_ids):
        named = [r for r in results if r.get("is_user_defined")]
        best = min(named, key=lambda r: (not r["is_safe"], r["total_cpp"]), default=None)
        fixed = [r for r in results if not r.get("is_user_defined") and r["candidate_id"] in visible_ids]
        visible_named = [r for r in named if r["candidate_id"] in visible_ids]
        return fixed, visible_named, best["candidate_id"] if best is not None else None


    def cost_figure(results, title, interval_label, total_label, visible_ids):
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
        fixed_results, custom_results, best_custom_id = cost_plan_groups(results, visible_ids)
        for label, key, color in styles:
            if fixed_results:
                figure.add_trace(
                    go.Scatter(
                        x=[_chart_interval(result) for result in fixed_results],
                        y=[result[key] for result in fixed_results],
                        name=label,
                        mode="lines+markers",
                        line={"color": color, "width": 2.6},
                        marker={
                            "size": 8,
                            "symbol": ["circle" if result["is_safe"] else "x" for result in fixed_results],
                        },
                        customdata=_cost_customdata(fixed_results),
                        hovertemplate=_cost_hover_template(total_label),
                    )
                )
            if custom_results:
                figure.add_trace(
                    go.Scatter(
                        x=[_chart_interval(result) for result in custom_results],
                        y=[result[key] for result in custom_results],
                        name=f"{label} — user-defined plans",
                        mode="markers",
                        marker={
                            "size": 12,
                            "symbol": [
                                "star" if label == total_label and result.get("candidate_id") == best_custom_id
                                else "diamond" if result["is_safe"] else "x"
                                for result in custom_results
                            ],
                            "color": color,
                            "line": {"color": "white", "width": 1},
                        },
                        customdata=_cost_customdata(custom_results),
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


    def _result_from_point(results, point, figure):
        data = point.get("customdata")
        if data is None:
            curve = point.get("curve_number", point.get("curveNumber"))
            index = point.get("point_index", point.get("pointIndex"))
            if curve is None or index is None or not 0 <= curve < len(figure.data):
                return None
            rows = figure.data[curve].customdata
            if rows is None or not 0 <= index < len(rows):
                return None
            data = rows[index]
        if len(data) < 8:
            return None
        return next((r for r in results if r["candidate_id"] == data[7]), None)


    def show_selected_cost(result, total_label):
        if result is None:
            return
        st.markdown(f"**Selected plan: {_plan_label(result)}**")
        st.caption("Schedule: " + str(result.get("schedule_description", "Fixed interval")))
        columns = st.columns(5)
        columns[0].metric(total_label, "$" + f"{result['total_cpp']:.6f}M")
        columns[1].metric("Cf — failure cost", "$" + f"{result['failure_cost']:.6f}M")
        columns[2].metric("Cr — repair cost", "$" + f"{result['repair_cost']:.6f}M")
        columns[3].metric("Ci — inspection cost", "$" + f"{result['inspection_cost']:.6f}M")
        columns[4].metric("Safety", _safety_label(result))
        if result["is_safe"]:
            st.success("Safe — this plan satisfies both probability-of-failure criteria.")
        else:
            st.error("Unsafe — this plan exceeds at least one probability-of-failure criterion.")
        st.caption(
            f"Limits used: PfL ≤ {result['max_annual_leak_pof']:.1e}; "
            f"PfB ≤ {result['max_annual_burst_pof']:.1e}."
        )


    def show_selectable_cost_figure(results, title, interval_label, total_label, key, study_signature):
        visible_ids, chart_key = select_cost_plans(
            results, f"Plans on the {total_label} chart", key, study_signature,
        )
        if not visible_ids:
            st.caption(f"Select a plan to show its {total_label} and cost components.")
            return
        st.caption(
            "Fixed intervals are connected as curves. User-defined schedules are separate points "
            "at their equivalent mean gap; hover for the exact schedule. Click a point for metrics. "
            "★ Lowest-cost safe user plan (or lowest-cost user plan if none are safe); ○ Safe   × Unsafe"
        )
        figure = cost_figure(results, title, interval_label, total_label, visible_ids)
        event = show_figure(figure, key=chart_key, selectable=True)
        points = _selected_points(event)
        if points:
            show_selected_cost(_result_from_point(results, points[0], figure), total_label)


    def annual_pof_figure(results, schedule_label, include_method=False):
        if not isinstance(results, (list, tuple)):
            results = [results]
        if not results:
            return base_figure(
                f"Annual system POF — {schedule_label}",
                "Year",
                "Annual probability of failure (whole pipeline)",
            )
        figure = base_figure(
            f"Annual system POF — selected {schedule_label.lower()} plans",
            "Year",
            "Annual probability of failure (whole pipeline)",
        )
        colors = [COLORS["navy"], COLORS["coral"], COLORS["teal"], COLORS["amber"],
                  COLORS["violet"], COLORS["blue"]]
        for index, result in enumerate(results):
            color = colors[index % len(colors)]
            name = _plan_label(result)
            if include_method:
                method_prefix = (
                    "Prior — " if result["decision_mode"] == EXCAVATION_DECISION_MODE
                    else "ILI — "
                )
                name = method_prefix + name
            figure.add_trace(
                go.Scatter(
                    x=result["times"],
                    y=np.maximum(result["leak_annual_pof"], 1e-12),
                    name=f"{name} — leakage",
                    mode="lines+markers",
                    line={"color": color, "width": 2.4},
                    marker={"size": 4},
                )
            )
            figure.add_trace(
                go.Scatter(
                    x=result["times"],
                    y=np.maximum(result["burst_annual_pof"], 1e-12),
                    name=f"{name} — burst",
                    mode="lines+markers",
                    line={"color": color, "width": 2.4, "dash": "dash"},
                    marker={"size": 4, "symbol": "square"},
                )
            )
        leak_limit = results[0]["max_annual_leak_pof"]
        burst_limit = results[0]["max_annual_burst_pof"]
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
        if len(results) == 1:
            for inspection in results[0]["inspections"]:
                figure.add_vline(
                    x=float(inspection),
                    line_dash="dot",
                    line_color=COLORS["teal"],
                    opacity=0.35,
                )
        figure.update_yaxes(type="log")
        figure.update_layout(hovermode="closest")
        return figure


    def results_table(results, total_label):
        total_column = f"Total {total_label} ($M)"
        return pd.DataFrame(
            [
                {
                    "Plan": _plan_label(result),
                    "Plan type": "User-defined" if result.get("is_user_defined") else "Fixed interval",
                    "Schedule": result.get("schedule_description", f"Every {result['interval']} years"),
                    "Fixed/equivalent mean gap (years)": _chart_interval(result),
                    total_column: result["total_cpp"],
                    "Cf — failure ($M)": result["failure_cost"],
                    "Cr — repair ($M)": result["repair_cost"],
                    "ILI inspection ($M)": result["inspection_cost"],
                    "Expected repairs": result["expected_repairs"],
                    "Peak annual whole-pipeline PfL": float(np.max(result["leak_annual_pof"])),
                    "Peak annual whole-pipeline PfB": float(np.max(result["burst_annual_pof"])),
                    "Safety": _safety_label(result),
                }
                for result in results
            ]
        )


    def comparison_cost_figure(prior_results, ili_results, visible_ids):
        figure = base_figure(
            "Prior excavation versus ILI-informed schedules",
            "Fixed interval / equivalent mean gap (years)",
            f"Expected lifecycle cost (million {handoff['consequence_unit'] or 'currency units'})",
        )
        for results, label, color, total_label in [
            (prior_results, "Prior: excavation without ILI", COLORS["amber"], "Cprior"),
            (ili_results, "Pre-posterior: ILI-informed", COLORS["teal"], "Cpp"),
        ]:
            fixed, custom, best_custom_id = cost_plan_groups(results, visible_ids)
            if fixed:
                figure.add_trace(
                    go.Scatter(
                        x=[_chart_interval(result) for result in fixed],
                        y=[result["total_cpp"] for result in fixed],
                        name=label,
                        mode="lines+markers",
                        line={"color": color, "width": 3},
                        marker={
                            "size": 8,
                            "symbol": ["circle" if result["is_safe"] else "x" for result in fixed],
                        },
                        customdata=_cost_customdata(fixed),
                        hovertemplate=_cost_hover_template(total_label),
                    )
                )
            if custom:
                figure.add_trace(
                    go.Scatter(
                        x=[_chart_interval(result) for result in custom],
                        y=[result["total_cpp"] for result in custom],
                        name=f"{label} — user-defined plans",
                        mode="markers",
                        marker={
                            "size": 12,
                            "symbol": [
                                "star" if result.get("candidate_id") == best_custom_id
                                else "diamond" if result["is_safe"] else "x"
                                for result in custom
                            ],
                            "color": color,
                            "line": {"color": "white", "width": 1},
                        },
                        customdata=_cost_customdata(custom),
                        hovertemplate=_cost_hover_template(total_label),
                    )
                )
        figure.update_layout(hovermode="closest", clickmode="event+select")
        return figure


    def show_comparison_cost_figure(prior_results, ili_results, study_signature):
        results = prior_results + ili_results
        visible_ids, chart_key = select_cost_plans(
            results, "Plans on the cost comparison chart", "comparison_cost_selection",
            study_signature, show_method=True,
        )
        if not visible_ids:
            st.caption("Select a prior or ILI plan to compare lifecycle costs.")
            return
        st.caption(
            "User-defined schedules appear as individual points at an equivalent mean gap. "
            "Hover to see each exact schedule and its Cf, Cr, Ci, and safety status."
        )
        figure = comparison_cost_figure(prior_results, ili_results, visible_ids)
        event = show_figure(figure, key=chart_key, selectable=True)
        points = _selected_points(event)
        if not points:
            return
        result = _result_from_point(results, points[0], figure)
        if result is not None:
            total_label = "Cprior" if result["decision_mode"] == EXCAVATION_DECISION_MODE else "Cpp"
            show_selected_cost(result, total_label)


    def comparison_table(prior_safe_result, ili_results):
        rows = []
        for result in ili_results:
            prior_cost = prior_safe_result["total_cpp"] if prior_safe_result is not None else np.nan
            cost_delta = (
                prior_cost - result["total_cpp"]
                if prior_safe_result is not None
                else np.nan
            )
            economically_justified = bool(
                prior_safe_result is not None
                and prior_safe_result["is_safe"]
                and result["is_safe"]
                and cost_delta > 0
            )
            rows.append({
                "ILI plan": _plan_label(result),
                "ILI schedule": result.get("schedule_description", ""),
                "ILI fixed/equivalent mean gap (years)": _chart_interval(result),
                "ILI total cost ($M)": result["total_cpp"],
                "ILI safety": _safety_label(result),
                "Prior minimum-cost safe plan": (
                    _plan_label(prior_safe_result) if prior_safe_result is not None else "Not found"
                ),
                "Prior safe cost ($M)": prior_cost,
                "Prior safe cost − ILI cost / Net VoI ($M)": cost_delta,
                "ILI economically justified?": "Yes" if economically_justified else "No",
            })
        return pd.DataFrame(rows)


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
    custom_plan_config = {"prior": [], "ili": []}
    custom_schedule_error = None
    cracked_joint_models = [joint for joint in joints if joint.get("cracks")]
    custom_prior_enabled = False
    custom_ili_enabled = False

    def _text_cell(value):
        return "" if value is None or pd.isna(value) else str(value).strip()

    plan_left, plan_right = st.columns(2)
    with plan_left:
        with st.expander("Prior plan", expanded=False):
            prior_intervals = []
            prior_default_interval = min(5, int(horizon))
            if settings.checkbox(
                "Include fixed excavation interval range",
                value=True,
                key="include_prior_interval_range",
            ):
                prior_interval_start = settings.number_input(
                    "First fixed excavation interval (years)", 1, 100, 5, 1
                )
                prior_interval_end = settings.number_input(
                    "Last fixed excavation interval (years)", 1, 100, 20, 1
                )
                prior_interval_step = settings.number_input(
                    "Fixed excavation interval step (years)", 1, 50, 5, 1
                )
                prior_intervals = list(range(
                    int(prior_interval_start), int(prior_interval_end) + 1, int(prior_interval_step)
                ))
                prior_default_interval = min(int(prior_interval_start), int(horizon))
            custom_prior_enabled = settings.checkbox(
                "Add user-defined schedules",
                value=False,
                key="include_named_prior_schedules",
            )
            if custom_prior_enabled:
                saved_prior_rows = render_prior_plans(
                    handoff["dataset_id"][:12], cracked_joint_models, int(horizon), prior_default_interval
                )
                try:
                    custom_plan_config["prior"] = prior_candidates(saved_prior_rows, cracked_joint_models, int(horizon))
                except (TypeError, ValueError) as exc:
                    custom_schedule_error = str(exc)
                    st.error(custom_schedule_error)

    with plan_right:
        with st.expander("Pre-posterior plan", expanded=False):
            ili_intervals = []
            ili_default_interval = min(5, int(horizon))
            if settings.checkbox(
                "Include fixed ILI interval range",
                value=True,
                key="include_ili_interval_range",
            ):
                ili_interval_start = settings.number_input(
                    "First fixed ILI interval (years)", 1, 100, 5, 1
                )
                ili_interval_end = settings.number_input(
                    "Last fixed ILI interval (years)", 1, 100, 20, 1
                )
                ili_interval_step = settings.number_input(
                    "Fixed ILI interval step (years)", 1, 50, 5, 1
                )
                ili_intervals = list(range(
                    int(ili_interval_start), int(ili_interval_end) + 1, int(ili_interval_step)
                ))
                ili_default_interval = min(int(ili_interval_start), int(horizon))
            custom_ili_enabled = settings.checkbox(
                "Add user-defined schedules",
                value=False,
                key="include_named_ili_schedules",
            )
            if custom_ili_enabled:
                st.caption(
                    "Add one row per ILI plan. Use the Actions cell in a row to duplicate or delete it."
                )
                ili_rows = render_ili_rows(handoff["dataset_id"][:12], int(horizon), ili_default_interval)

                try:
                    ili_groups = {}
                    ili_names_casefold = {}
                    for row in ili_rows:
                        name = _text_cell(row.get("Plan name"))
                        schedule_type = _text_cell(row.get("Schedule type")) or "Fixed interval"
                        manual_text = _text_cell(row.get("Manual inspection years"))
                        interval_value = row.get("Interval (years)")
                        if interval_value is not None and pd.isna(interval_value):
                            interval_value = None
                        if not name and not manual_text and interval_value is None:
                            continue
                        if not name:
                            raise ValueError("Every pre-posterior schedule row needs a plan name.")
                        name_key = name.casefold()
                        if name_key in ili_names_casefold:
                            raise ValueError("Pre-posterior plan names must be unique, ignoring capitalization.")
                        ili_names_casefold[name_key] = name
                        if schedule_type == "Fixed interval":
                            if interval_value is None:
                                raise ValueError(f"{name}: enter a fixed ILI interval.")
                            interval_value = float(interval_value)
                            if not np.isfinite(interval_value) or not interval_value.is_integer():
                                raise ValueError(f"{name}: interval must be a whole number of years.")
                            interval_value = int(interval_value)
                            if interval_value < 1 or interval_value > int(horizon):
                                raise ValueError(f"{name}: interval must be from 1 to {int(horizon)} years.")
                            years = list(range(interval_value, int(horizon) + 1, interval_value))
                            description = f"every {interval_value} years"
                        elif schedule_type == "Manual years":
                            years = parse_manual_years(
                                manual_text, f"{name} ILI schedule", int(horizon)
                            )
                            description = ", ".join(map(str, years))
                        else:
                            raise ValueError(f"{name}: choose Fixed interval or Manual years.")
                        ili_groups[name] = (years, description)

                    for name, (years, description) in ili_groups.items():
                        plan_id = hashlib.sha256(
                            repr(("ili", name, years)).encode()
                        ).hexdigest()[:12]
                        custom_plan_config["ili"].append({
                            "candidate_id": "ili-user-" + plan_id,
                            "plan_name": name,
                            "years": years,
                            "joint_schedules": None,
                            "schedule_description": description,
                            "chart_interval": float(horizon) / (len(years) + 1),
                        })
                except (TypeError, ValueError) as exc:
                    custom_schedule_error = str(exc)
                    st.error(custom_schedule_error)

    custom_plan_enabled = custom_prior_enabled or custom_ili_enabled
    user_plan_count = sum(len(plans) for plans in custom_plan_config.values())
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
        "Fixed candidates (prior / ILI)",
        f"{len(prior_intervals)} / {len(ili_intervals)}",
        help=f"{len(custom_plan_config['prior'])} prior and {len(custom_plan_config['ili'])} ILI user-defined plans are additional candidates.",
    )
    metric_columns[4].metric("Monte Carlo samples", f"{samples:,}")

    candidate_count = (
        len(prior_intervals) + len(ili_intervals) + user_plan_count
    )
    simulation_units = len(joints)
    work_units = (
        simulation_units
        * samples
        * (horizon + 1)
        * max(candidate_count, 1)
    )
    actual_batch_size = effective_batch_size(joints, horizon, 1, sample_batch_size)
    st.caption(
        f"Memory-efficient execution: up to {min(samples, actual_batch_size):,} samples per batch. "
        "Fixed candidates and user-defined plans run sequentially through the same engine. "
        "Each completed plan stores only annual and joint-level summary arrays; it does not retain "
        "individual Monte Carlo histories. CPU time grows roughly with the number of plans."
    )
    if work_units > 2_000_000:
        st.info(
            "This is a larger calculation. Batching limits peak simulation memory, but CPU time "
            "still increases with samples, defects, analysis years, and candidate plans. "
            "Shared hosting may remain a bottleneck."
        )

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

    run_signature = hashlib.sha256(
        repr((
            handoff["dataset_id"],
            model,
            joints,
            prior_intervals,
            ili_intervals,
            custom_plan_config,
            pipeline_class,
        )).encode()
    ).hexdigest()
    current_safety_signature = (
        pipeline_class,
        float(max_annual_leak_pof) if safety_criteria_valid else None,
        float(max_annual_burst_pof) if safety_criteria_valid else None,
    )
    current_interval_signature = (
        tuple(prior_intervals),
        tuple(ili_intervals),
        tuple(plan["candidate_id"] for plan in custom_plan_config["prior"]),
        tuple(plan["candidate_id"] for plan in custom_plan_config["ili"]),
    )
    run_disabled = (
        not joints
        or (not prior_intervals and not custom_plan_config["prior"])
        or (not ili_intervals and not custom_plan_config["ili"])
        or not safety_criteria_valid
        or custom_schedule_error is not None
    )
    def request_analysis_stop(active_job):
        # Clicking this full-page widget also asks Streamlit to rerun the script.
        if not active_job.get("complete"):
            active_job["stop_requested"] = True

    job = st.session_state.get("integrated_planning_job")
    # Fast reruns can start a new script while the previous one finishes a batch.
    # Wait for its checkpoint and exit before reading results or offering Resume.
    finishing = job.get("_run_finished") if job else None
    if finishing is not None and not finishing.is_set():
        with st.spinner("Finishing the current batch and saving progress…"):
            finishing.wait()
    resumable = bool(
        job and job.get("run_signature") == run_signature and not job.get("complete")
    )
    prior_candidate_total = len(prior_intervals) + len(custom_plan_config["prior"])
    ili_candidate_total = len(ili_intervals) + len(custom_plan_config["ili"])
    if not custom_schedule_error:
        for section, count in [("Prior plan", prior_candidate_total), ("Pre-posterior plan", ili_candidate_total)]:
            if count == 0:
                st.info(f"{section} needs at least one schedule. Choose a fixed interval range "
                        "that includes at least one interval, or enter a named schedule.")

    if resumable:
        finished_prior = len(job.get("prior_results", []))
        finished_ili = len(job.get("ili_results", []))
        attempted = sum(
            checkpoint.get("processed", 0)
            for checkpoint in job.get("checkpoints", {}).values()
        )
        status = "Analysis stopped." if job.get("stop_requested") else "Unfinished run."
        st.info(
            f"{status} {finished_prior}/{prior_candidate_total} prior plans and "
            f"{finished_ili}/{ili_candidate_total} ILI plans completed. "
            f"{attempted:,} samples saved for unfinished plans. Resume to continue from the last saved batch."
        )
        partial = [
            {
                "Method": label,
                "Plan": _plan_label(result),
                "Schedule": result.get("schedule_description", ""),
                "Equivalent mean gap (years)": result.get("chart_interval", result["interval"]),
                "Cost ($M)": result["total_cpp"],
                "Safe": result["is_safe"],
            }
            for label, key in [("Prior", "prior_results"), ("ILI-informed", "ili_results")]
            for result in job.get(key, [])
        ]
        if partial:
            st.download_button(
                "Download completed plans (partial run)",
                pd.DataFrame(partial).to_csv(index=False),
                "completed_planning_plans.csv",
                "text/csv",
            )

    if st.button(
        "Resume prior + pre-posterior comparison" if resumable else "Run prior + pre-posterior comparison",
        type="primary",
        disabled=run_disabled,
        key="run_integrated_planning_comparison",
    ):
        if not resumable:
            job = dict(
                run_signature=run_signature,
                prior_results=[],
                ili_results=[],
                checkpoints={},
                complete=False,
            )
            st.session_state["integrated_planning_job"] = job
        stop_control = st.empty()
        finished = Event()
        job["_run_finished"] = finished
        job["stop_requested"] = False
        try:
            st.session_state.pop("integrated_planning_comparison", None)
            stop_control.button(
                "Stop analysis", key="stop_integrated_planning_comparison",
                on_click=request_analysis_stop, args=(job,),
                help="Finish the current batch and save progress for Resume.",
            )
            with st.spinner("Running prior excavation candidates…"):
                prior_results, prior_log = run_interval_study(
                    joints, prior_intervals, model, EXCAVATION_DECISION_MODE, job
                )
                prior_results, prior_log = run_user_defined_studies(
                    joints, custom_plan_config["prior"], model, EXCAVATION_DECISION_MODE, job
                )
            with st.spinner("Running ILI-informed candidates…"):
                ili_results, ili_log = run_interval_study(
                    joints, ili_intervals, model, ILI_DECISION_MODE, job
                )
                ili_results, ili_log = run_user_defined_studies(
                    joints, custom_plan_config["ili"], model, ILI_DECISION_MODE, job
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
                "user_plan_config": custom_plan_config,
                "dataset_id": handoff["dataset_id"],
                "run_signature": run_signature,
            }
            job["complete"] = True
        except Exception as exc:
            st.error(
                "The calculation did not finish. Completed plans and batches are kept "
                "in this session. Select Resume to continue; changing inputs starts a new study."
            )
            st.exception(exc)
        finally:
            # Also runs when Streamlit interrupts this script at a progress update.
            job.pop("_run_finished", None)
            finished.set()
        stop_control.empty()

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
        with st.expander("Pipeline joint reliability profile", expanded=True):
            method = st.radio(
                "Map planning method",
                ["Prior excavation", "ILI-informed"],
                horizontal=True,
            )
            candidates = prior_results if method == "Prior excavation" else ili_results
            preferred = prior_safe if method == "Prior excavation" else ili_safe
            preferred_index = next(
                (i for i, candidate in enumerate(candidates)
                 if preferred is not None and candidate["candidate_id"] == preferred["candidate_id"]),
                0,
            )
            selected_index = st.selectbox(
                "Map plan",
                options=list(range(len(candidates))),
                index=preferred_index,
                format_func=lambda index: _plan_label(candidates[index]),
                key=f"map_plan_choice_{method}_{study['run_signature'][:8]}",
            )
            result = candidates[selected_index]
            st.caption(
                "Red: above a selected POF limit. Yellow: 50–100% of a limit. "
                "Green: below 50%. A 1 km window slides by one nominal joint; boundary "
                "joints are included in full. These are reliability indicators, without "
                "consequences. The scheduling safety check remains the existing whole-route "
                "calculation; this display is not a verified CSA compliance assessment."
            )
            try:
                windows, spatial = sliding_window_reliability(result, handoff)
                st_folium(
                    reliability_map(handoff["project"]["route"], spatial),
                    height=450,
                    returned_objects=[],
                    key=f"integrated_result_map_{method}_{result['candidate_id']}",
                )
                st.markdown("**Sliding one KM results**")
                st.dataframe(windows.sort_values("limit_ratio", ascending=False), hide_index=True)
                st.download_button(
                    "Download sliding 1 km results CSV",
                    windows.to_csv(index=False),
                    "planning_sliding_1km_results.csv",
                    "text/csv",
                )
                with st.expander("Individual joint results"):
                    st.dataframe(spatial, hide_index=True)
                    st.download_button(
                        "Download joint reliability CSV",
                        spatial.to_csv(index=False),
                        "planning_joint_reliability.csv",
                        "text/csv",
                    )
            except ValueError as exc:
                st.warning("The probability map is unavailable for this plan: " + str(exc))

        retained = [
            (result["retained_samples"], result["requested_samples"])
            for result in prior_results + ili_results
        ]
        st.caption(
            "Time-zero survival conditioning: "
            + ", ".join(f"{n}/{total} samples retained" for n, total in sorted(set(retained)))
            + ". Future planning results are conditional on initial survival."
        )
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
        with st.expander("Why a plan is Safe or Unsafe"):
            st.caption(
                "Safety is checked at every simulated year over the full analysis horizon, "
                "including years after the first intervention. The table identifies the first "
                "exceedance and peak values used for each plan."
            )
            safety_rows = []
            for method_label, method_results in [
                ("Prior excavation", prior_results),
                ("ILI-informed", ili_results),
            ]:
                for candidate in method_results:
                    row = interval_safety_rows([candidate], method_label)[0]
                    row["Plan"] = _plan_label(candidate)
                    row["Schedule"] = candidate.get("schedule_description", "")
                    row["Plan type"] = (
                        "User-defined" if candidate.get("is_user_defined") else "Fixed interval"
                    )
                    safety_rows.append(row)
            safety_table = pd.DataFrame(safety_rows)
            st.dataframe(
                safety_table.style.format({
                    "Peak annual whole-pipeline PfL": "{:.3e}",
                    "Peak annual whole-pipeline PfB": "{:.3e}",
                    "First limit exceedance (year)": "{:.0f}",
                    "Interval (years)": "{:.2f}",
                }, na_rep="—"),
                hide_index=True,
                width="stretch",
            )
            st.download_button(
                "Download plan safety diagnostics",
                safety_table.to_csv(index=False),
                "planning_plan_safety.csv",
                "text/csv",
            )
            st.caption(
                f"Joint/group details use the map selection: {method}, {_plan_label(result)}. "
                f"Each group is evaluated alone over the same {pipe_length:.3f} km route; "
                "these group values cannot be added together."
            )
            groups_table = pd.DataFrame(joint_safety_rows(result, joints, pipe_length))
            st.dataframe(
                groups_table.style.format({
                    "Peak group PfL / km-year": "{:.3e}",
                    "Peak group PfB / km-year": "{:.3e}",
                    "Approx. one-event increment / km": "{:.3e}",
                }),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Initially crack-free groups can govern the result when new cracks initiate. "
                "Their common marginal POF is estimated from the retained samples and combined "
                "using the number of physical joints represented. The one-event increment is "
                "a sampling-resolution indicator, not a confidence interval."
            )
            st.download_button(
                "Download joint/group probability diagnostics",
                groups_table.to_csv(index=False),
                "planning_joint_group_probabilities.csv",
                "text/csv",
            )

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
                '<div class="voi-value">' + "$" + f'{voi["voi"]:.4f}M</div>'
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
                "Minimum-cost safe plan: **Not found** for "
                + " and ".join(missing)
                + " within the tested fixed intervals and user-defined schedules. "
                "The lowest-cost plan is still shown above with its Safe/Unsafe status."
            )

        comparison_tab, prior_tab, ili_tab = st.tabs(
            ["VoI comparison", "Prior excavation (no ILI)", "Pre-posterior (ILI)"]
        )
        with comparison_tab:
            show_comparison_cost_figure(prior_results, ili_results, study["run_signature"])
            combined_candidates = prior_results + ili_results
            default_profile_indices = []
            for preferred_result in (prior_safe, ili_safe):
                if preferred_result is not None:
                    matching_index = next(
                        index for index, candidate in enumerate(combined_candidates)
                        if candidate["candidate_id"] == preferred_result["candidate_id"]
                    )
                    default_profile_indices.append(matching_index)
            if not default_profile_indices and combined_candidates:
                default_profile_indices = [0]
            selected_profile_indices = st.multiselect(
                "Annual POF plans to compare across prior and ILI methods",
                options=list(range(len(combined_candidates))),
                default=default_profile_indices,
                format_func=lambda index: (
                    ("Prior — " if combined_candidates[index]["decision_mode"] == EXCAVATION_DECISION_MODE
                     else "ILI — ")
                    + _plan_label(combined_candidates[index])
                ),
                key=f"combined_annual_pof_plans_{study['run_signature'][:8]}",
            )
            if selected_profile_indices:
                show_figure(
                    annual_pof_figure(
                        [combined_candidates[index] for index in selected_profile_indices],
                        "prior and ILI-informed",
                        include_method=True,
                    )
                )
            st.caption(
                "Every ILI plan is compared with the minimum-cost safe prior excavation plan. "
                "ILI is economically justified only when the ILI plan is safe and its expected "
                "lifecycle cost is lower than the prior safe plan. User-defined schedules are "
                "included in this comparison."
            )
            combined = comparison_table(prior_safe, ili_results)
            combined["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                combined.style.format(
                    {
                        "ILI fixed/equivalent mean gap (years)": "{:.2f}",
                        "ILI total cost ($M)": "{:.6f}",
                        "Prior safe cost ($M)": format_optional_decimal,
                        "Prior safe cost − ILI cost / Net VoI ($M)": format_optional_decimal,
                    },
                    na_rep="—",
                ),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "Download VoI comparison",
                combined.to_csv(index=False).encode("utf-8"),
                "ili_plans_vs_prior_safe.csv",
                "text/csv",
            )

        with prior_tab:
            prior_columns = st.columns(5)
            prior_columns[0].metric(
                "Cost-optimal plan",
                _plan_label(prior_cost_optimal),
            )
            prior_columns[1].metric(
                "Lowest Cprior",
                "$" + f"{prior_cost_optimal['total_cpp']:.4f}M",
            )
            prior_columns[2].metric(
                "Safety at cost optimum",
                _safety_label(prior_cost_optimal),
            )
            prior_columns[3].metric(
                "Minimum-cost safe plan",
                _plan_label(prior_safe) if prior_safe else "Not found",
            )
            prior_columns[4].metric(
                "Safe Cprior",
                "$" + f"{prior_safe['total_cpp']:.4f}M" if prior_safe else "—",
            )
            show_selectable_cost_figure(
                prior_results,
                "Prior lifecycle cost versus excavation interval",
                "Fixed interval / equivalent mean gap (years)",
                "Cprior",
                "prior_cost_selection", study["run_signature"],
            )
            prior_default_index = next(
                i for i, candidate in enumerate(prior_results)
                if candidate["candidate_id"] == prior_cost_optimal["candidate_id"]
            )
            prior_selected_indices = st.multiselect(
                "Annual POF profiles to compare",
                options=list(range(len(prior_results))),
                default=[prior_default_index],
                format_func=lambda index: _plan_label(prior_results[index]),
                key=f"prior_annual_pof_plans_{study['run_signature'][:8]}",
            )
            if prior_selected_indices:
                show_figure(
                    annual_pof_figure(
                        [prior_results[index] for index in prior_selected_indices],
                        "prior excavation",
                    )
                )
            else:
                st.info("Select at least one prior plan to display annual POF.")
            prior_table = results_table(prior_results, "Cprior")
            prior_table["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                prior_table.style.format(
                    {
                        "Fixed/equivalent mean gap (years)": "{:.2f}",
                        "Total Cprior ($M)": "{:.6f}",
                        "Cf — failure ($M)": "{:.6f}",
                        "Cr — repair ($M)": "{:.6f}",
                        "ILI inspection ($M)": "{:.6f}",
                        "Expected repairs": "{:.4f}",
                        "Peak annual whole-pipeline PfL": "{:.3e}",
                        "Peak annual whole-pipeline PfB": "{:.3e}",
                    },
                    na_rep="—",
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
                "Cost-optimal plan",
                _plan_label(ili_cost_optimal),
            )
            ili_columns[1].metric(
                "Lowest Cpp",
                "$" + f"{ili_cost_optimal['total_cpp']:.4f}M",
            )
            ili_columns[2].metric(
                "Safety at cost optimum",
                _safety_label(ili_cost_optimal),
            )
            ili_columns[3].metric(
                "Minimum-cost safe plan",
                _plan_label(ili_safe) if ili_safe else "Not found",
            )
            ili_columns[4].metric(
                "Safe Cpp",
                "$" + f"{ili_safe['total_cpp']:.4f}M" if ili_safe else "—",
            )
            show_selectable_cost_figure(
                ili_results,
                "Pre-posterior lifecycle cost versus ILI interval",
                "Fixed interval / equivalent mean gap (years)",
                "Cpp",
                "ili_cost_selection", study["run_signature"],
            )
            ili_default_index = next(
                i for i, candidate in enumerate(ili_results)
                if candidate["candidate_id"] == ili_cost_optimal["candidate_id"]
            )
            ili_selected_indices = st.multiselect(
                "Annual POF profiles to compare",
                options=list(range(len(ili_results))),
                default=[ili_default_index],
                format_func=lambda index: _plan_label(ili_results[index]),
                key=f"ili_annual_pof_plans_{study['run_signature'][:8]}",
            )
            if ili_selected_indices:
                show_figure(
                    annual_pof_figure(
                        [ili_results[index] for index in ili_selected_indices],
                        "ILI-informed",
                    )
                )
            else:
                st.info("Select at least one ILI-informed plan to display annual POF.")
            ili_table = results_table(ili_results, "Cpp")
            ili_table["Dataset ID"] = study["dataset_id"]
            st.dataframe(
                ili_table.style.format(
                    {
                        "Fixed/equivalent mean gap (years)": "{:.2f}",
                        "Total Cpp ($M)": "{:.6f}",
                        "Cf — failure ($M)": "{:.6f}",
                        "Cr — repair ($M)": "{:.6f}",
                        "ILI inspection ($M)": "{:.6f}",
                        "Expected repairs": "{:.4f}",
                        "Peak annual whole-pipeline PfL": "{:.3e}",
                        "Peak annual whole-pipeline PfB": "{:.3e}",
                    },
                    na_rep="—",
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
