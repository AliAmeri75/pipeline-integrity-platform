"""Named excavation plans and schedule-table editing for static planning."""
import hashlib

import numpy as np
import pandas as pd
import streamlit as st


JOINT = "Cracked joint"
KIND = "Schedule type"
INTERVAL = "Interval (years)"
MANUAL = "Manual excavation years"
PLAN = "Plan name"
ALL = "All cracked joints"
FIXED = "Fixed interval"
LISTED = "Manual years"
NONE = "No excavation"


def cell(value):
    return "" if value is None or pd.isna(value) else str(value).strip()


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


def schedule_editor_input(rows_key, editor_key, default_row, horizon, joint_options=()):
    # A dynamic data editor applies all cell and row edits to its original input.
    # Only start a new baseline when reopening the editor or changing its schema.
    baseline_key = rows_key + "_baseline"
    config = (int(horizon), tuple(joint_options))
    baseline = st.session_state.get(baseline_key)
    if editor_key not in st.session_state or baseline is None or baseline[0] != config:
        rows = st.session_state.get(rows_key, [default_row])
        frame = pd.DataFrame.from_records(rows, columns=list(default_row))
        frame = frame.astype({
            column: "Int64" if column == "Interval (years)" else "string"
            for column in default_row
        })
        baseline = (config, frame)
        st.session_state[baseline_key] = baseline
    return baseline[1]


def prior_candidates(rows, joints, horizon):
    """Compile saved rows for the existing engine, including legacy all-joint plans."""
    groups = {}
    spellings = {}
    names = [joint["name"] for joint in joints]
    for row in rows:
        name = cell(row.get(PLAN))
        target = cell(row.get(JOINT))
        interval = row.get(INTERVAL)
        manual = cell(row.get(MANUAL))
        if not name and not manual and pd.isna(interval):
            continue
        if not names:
            raise ValueError("Prior schedules need at least one initially cracked joint.")
        if not name:
            raise ValueError("Every prior schedule needs a plan name.")
        if spellings.setdefault(name.casefold(), name) != name:
            raise ValueError("Prior plan names must be unique, ignoring capitalization.")
        if target != ALL and target not in names:
            raise ValueError(f"{name}: choose a valid cracked joint.")
        assignments = groups.setdefault(name, {})
        if target in assignments or (assignments and (target == ALL or ALL in assignments)):
            raise ValueError(f"{name}: each joint can have only one schedule.")
        kind = cell(row.get(KIND)) or FIXED
        if kind == NONE:
            years, description = [], "no excavation"
        elif kind == FIXED:
            if pd.isna(interval):
                raise ValueError(f"{name} / {target}: enter a fixed interval.")
            value = float(interval)
            if not value.is_integer() or not 1 <= value <= horizon:
                raise ValueError(f"{name} / {target}: enter a whole interval from 1 to {horizon} years.")
            years = list(range(int(value), horizon + 1, int(value)))
            description = f"every {int(value)} years"
        elif kind == LISTED:
            years = parse_manual_years(manual, f"{name} / {target} excavation schedule", horizon)
            description = ", ".join(map(str, years))
        else:
            raise ValueError(f"{name} / {target}: choose a schedule type.")
        assignments[target] = (years, description)

    candidates = []
    for name, assignments in groups.items():
        if ALL in assignments:
            schedules = {joint: assignments[ALL][0] for joint in names}
        else:
            schedules = {joint: item[0] for joint, item in assignments.items()}
        mean_gap = np.average(
            [horizon / (len(schedules.get(joint, [])) + 1) for joint in names],
            weights=[max(int(joint.get("count", 1)), 1) for joint in joints],
        )
        plan_id = hashlib.sha256(repr(("prior", name, schedules)).encode()).hexdigest()[:12]
        candidates.append({
            "candidate_id": "prior-user-" + plan_id,
            "plan_name": name,
            "years": sorted({year for years in schedules.values() for year in years}),
            "joint_schedules": schedules,
            "schedule_description": "; ".join(
                f"{target}: {description}" for target, (_, description) in assignments.items()
            ),
            "chart_interval": float(mean_gap),
        })
    return candidates


def copy_name(name, names):
    used = {existing.casefold() for existing in names}
    base = name + " copy"
    result = base
    number = 2
    while result.casefold() in used:
        result = f"{base} {number}"
        number += 1
    return result


def duplicate_ili_row(rows, rows_key):
    if not rows:
        return
    index = st.selectbox("ILI row to duplicate", range(len(rows)),
        format_func=lambda i: f"{i + 1}. {cell(rows[i].get(PLAN)) or 'Unnamed plan'}",
        key=rows_key + "_copy_source")
    if st.button("Duplicate ILI row", key=rows_key + "_copy"):
        duplicate = dict(rows[index])
        duplicate[PLAN] = copy_name(cell(duplicate.get(PLAN)) or "ILI plan",
                                    [cell(r.get(PLAN)) for r in rows])
        st.session_state[rows_key] = rows[:index + 1] + [duplicate] + rows[index + 1:]
        revision = rows_key + "_revision"
        st.session_state[revision] = st.session_state.get(revision, 0) + 1
        st.rerun()


def render_prior_plans(dataset, joints, horizon, default_interval):
    rows_key = "custom_prior_plan_rows_v2_" + dataset
    draft_key = rows_key + "_draft"
    table_key = draft_key + "_rows"
    revision_key = draft_key + "_revision"
    state = st.session_state
    saved = state.setdefault(rows_key, [])
    names = list(dict.fromkeys(cell(r.get(PLAN)) for r in saved if cell(r.get(PLAN))))
    joint_names = [j["name"] for j in joints]
    default = {JOINT: "", KIND: FIXED, INTERVAL: default_interval, MANUAL: ""}
    message = state.pop(draft_key + "_notice", None)
    if message:
        st.success(message)
    if not joint_names:
        st.info("Add a cracked joint in Data Exploration to create an excavation plan.")
        return saved

    def open_draft(name, source=None, *, edit_existing=False):
        assignments = {cell(r.get(JOINT)): r for r in saved if cell(r.get(PLAN)) == source}
        state[draft_key] = {"original": source if edit_existing else None, "name": name}
        rows = []
        for joint in joint_names:
            row = dict(default)
            if source is not None:
                previous = assignments.get(joint, assignments.get(ALL))
                if previous is None:
                    row[KIND] = NONE
                else:
                    row.update({col: previous.get(col) for col in (KIND, INTERVAL, MANUAL)})
            row[JOINT] = joint
            rows.append(row)
        state[table_key] = rows
        state[revision_key] = state.get(revision_key, 0) + 1
        st.rerun()

    draft = state.get(draft_key)
    if draft is None:
        if names:
            selected = st.selectbox("Saved prior plans", names, key=rows_key + "_selected")
            edit, duplicate, remove = st.columns(3)
            if edit.button("Edit plan", key=rows_key + "_edit"):
                open_draft(selected, selected, edit_existing=True)
            if duplicate.button("Duplicate plan", key=rows_key + "_duplicate"):
                open_draft(copy_name(selected, names), selected)
            if remove.button("Remove plan", key=rows_key + "_remove"):
                state[rows_key] = [r for r in saved if cell(r.get(PLAN)) != selected]
                st.rerun()
        idx = 1
        used = {n.casefold() for n in names}
        while f"prior plan {idx}" in used:
            idx += 1
        name = st.text_input("New prior plan name", value=f"Prior plan {idx}",
                             key=draft_key + "_new_" + str(state.get(revision_key, 0))).strip()
        if st.button("Create joint table", key=rows_key + "_create"):
            if not name or name.casefold() in used:
                st.error("Enter a unique prior plan name.")
            else:
                open_draft(name)
        return saved

    if names:
        st.caption("Saved for comparison: " + ", ".join(names))
    st.caption("Set one excavation schedule per cracked joint. Save this plan to include it in the comparison.")
    # Keep plan-name edits when leaving the page and returning to this draft.
    name = st.text_input("Prior plan name", value=draft["name"], key=draft_key + "_name").strip()
    draft["name"] = name
    editor_key = draft_key + "_table_" + str(state[revision_key])
    table = st.data_editor(
        schedule_editor_input(table_key, editor_key, default, horizon, joint_names),
        key=editor_key, hide_index=True, num_rows="fixed", width="stretch", disabled=[JOINT],
        column_config={
            KIND: st.column_config.SelectboxColumn(KIND, options=[FIXED, LISTED, NONE], required=True),
            INTERVAL: st.column_config.NumberColumn(INTERVAL, min_value=1, max_value=horizon,
                                                    step=1, format="%d"),
            MANUAL: st.column_config.TextColumn(MANUAL, help="For Manual years, enter years such as 3, 5, 20."),
        },
    )
    rows = table.to_dict(orient="records")
    state[table_key] = rows
    if len(rows) > 1:
        with st.expander("Duplicate a joint schedule"):
            source = st.selectbox("Copy schedule from", joint_names, key=draft_key + "_source")
            destinations = st.multiselect("Replace schedule for", [j for j in joint_names if j != source],
                                          key=draft_key + "_targets_" + source)
            if st.button("Copy schedule", disabled=not destinations, key=draft_key + "_copy"):
                template = next(r for r in rows if r[JOINT] == source)
                state[table_key] = [dict(template, **{JOINT: r[JOINT]}) if r[JOINT] in destinations
                                    else r for r in rows]
                state[revision_key] += 1
                st.rerun()

    save, cancel = st.columns(2)
    if save.button("Save prior plan", key=rows_key + "_save", type="primary"):
        try:
            if not name or any(n != draft["original"] and n.casefold() == name.casefold() for n in names):
                raise ValueError("Enter a unique prior plan name.")
            replacement = [{PLAN: name, **r} for r in rows]
            prior_candidates(replacement, joints, horizon)
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
        else:
            # Keep the order of saved candidates when updating an existing plan.
            position = next((i for i, r in enumerate(saved) if cell(r.get(PLAN)) == draft["original"]), len(saved))
            others = [r for r in saved if cell(r.get(PLAN)) != draft["original"]]
            state[rows_key] = others[:position] + replacement + others[position:]
            state.pop(draft_key)
            state[draft_key + "_notice"] = f"Saved {name} for comparison."
            st.rerun()
    if cancel.button("Discard draft", key=rows_key + "_cancel"):
        state.pop(draft_key)
        st.rerun()
    return saved
