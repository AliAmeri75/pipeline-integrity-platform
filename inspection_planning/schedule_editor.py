"""Named excavation plans and schedule-table editing for static planning."""
import hashlib
from pathlib import Path

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


_schedule_table = st.components.v2.component(
    "alirim_schedule_table",
    html='<div class="schedule-table"></div>',
    js=Path(__file__).with_name("schedule_table.js").read_text(encoding="utf-8"),
    css=""".schedule-table { font: inherit; color: var(--st-text-color, inherit); }
.scroll { overflow-x: auto; border-radius: .4rem; border: 1px solid var(--st-border-color, #bdc9c4); }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { padding: .35rem; text-align: left; vertical-align: middle; }
th { background: var(--st-secondary-background-color, #edf1ef); font-size: .82rem; }
tbody tr + tr { border-top: 1px solid var(--st-border-color, #bdc9c4); }
input, select, button { font: inherit; color: inherit; background: var(--st-background-color, white);
    border: 1px solid var(--st-border-color, #aab8b0); border-radius: .3rem; padding: .35rem; }
input, select { box-sizing: border-box; width: 100%; }
input { min-width: 5rem; }
td:last-child { min-width: 7rem; }
select.actions { width: 3.3rem; }
label span { display: block; font-size: .75rem; margin-bottom: .15rem; }
button { margin-top: .4rem; cursor: pointer; }
:focus-visible { outline: 2px solid var(--st-primary-color, #207357); outline-offset: 1px; }""",
)


def edit_schedule_rows(rows_key, widget_key, rows, horizon, default_interval, *, prior):
    """Render one mode-specific value field per row; retain both drafts in session."""
    manual = MANUAL if prior else "Manual inspection years"
    identity = JOINT if prior else PLAN

    def normalized(row):
        value = row.get(INTERVAL)
        return {identity: cell(row.get(identity)), KIND: cell(row.get(KIND)) or FIXED,
                INTERVAL: None if pd.isna(value) else float(value), manual: cell(row.get(manual))}

    initial = [normalized(row) for row in rows]
    result = _schedule_table(
        key=widget_key,
        data={"instance": widget_key, "rows": initial, "prior": prior,
              "horizon": int(horizon), "defaultInterval": int(default_interval)},
        default={"rows": initial}, on_rows_change=lambda: None,
    )
    edited = [normalized(row) for row in result.rows]
    if prior and [r[JOINT] for r in edited] != [r[JOINT] for r in initial]:
        raise ValueError("Excavation rows must match the cracked joints in this plan.")
    st.session_state[rows_key] = edited
    return edited


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


def render_ili_rows(dataset, horizon, default_interval):
    rows_key = "custom_ili_plan_rows_v2_" + dataset
    default_row = {PLAN: "Pre-posterior plan 1", KIND: FIXED,
                   INTERVAL: default_interval, "Manual inspection years": ""}
    return edit_schedule_rows(
        rows_key, "ili_schedule_table_" + dataset, st.session_state.get(rows_key, [default_row]),
        horizon, default_interval, prior=False,
    )


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
    rows = edit_schedule_rows(table_key, editor_key, state[table_key], horizon, default_interval, prior=True)

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
