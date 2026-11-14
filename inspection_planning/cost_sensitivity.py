"""Reprice static planning outcomes using the same retained Monte Carlo events."""
import numpy as np


def cost_quantities(raw, joints, costs, ili):
    """Expected undiscounted quantities at each simulation time, one vector per price."""
    times, inspections, repairs, debug = raw[0], raw[5], raw[14], raw[16]
    counts = np.asarray([j.get("count", 1) for j in joints], dtype=float)
    names = [joint.get("name", f"Joint {i + 1}") for i, joint in enumerate(joints)]
    if names != list(debug["joint_names"]):
        raise ValueError("Cost quantities and simulated joint groups must agree.")
    result = {
        "Cr1": np.asarray(repairs),
        "Cr2": debug["type2_repair_means"],
        "inspection_cost_per_km": np.zeros_like(times, dtype=float),
    }
    if ili:
        for year in inspections:
            result["inspection_cost_per_km"][np.isclose(times, year)] = costs["pipe_length_km"]
    for mode, key in (("leak", "Cf_leak"), ("burst", "Cf_burst")):
        # Step event means include repeated failures. A whole-route POF would
        # undercount costs when several physical joints fail in the same year.
        step_events = debug[f"joint_{mode}_step_pofs"]
        overrides = [joint.get("costs", {}) for joint in joints]
        fallback = np.array([key not in values for values in overrides])
        assigned = np.array([values.get(key, 0.0) for values in overrides])
        result[key] = (counts * fallback) @ step_events
        result["segment_" + mode] = (counts * assigned) @ step_events
    return result


def reprice(result, prices):
    """Return a priced view of a completed plan without changing its baseline or POF."""
    events = result["cost_quantities"]
    discount = (1.0 + prices["rate"]) ** -np.asarray(result["times"], dtype=float)
    repair = discount * (events["Cr1"] * prices["Cr1"] + events["Cr2"] * prices["Cr2"])
    inspection = discount * events["inspection_cost_per_km"] * prices["inspection_cost_per_km"]
    failure = discount * (
        events["Cf_leak"] * prices["Cf_leak"] + events["Cf_burst"] * prices["Cf_burst"]
        + events["segment_leak"] * prices.get("segment_leak", 1.0)
        + events["segment_burst"] * prices.get("segment_burst", 1.0)
    )
    total = failure + repair + inspection
    return {**result, "cpp": total, "total_cpp": float(total.sum()),
            "failure_cost": float(failure.sum()), "repair_cost": float(repair.sum()),
            "inspection_cost": float(inspection.sum())}


def annual_counts(result, joints, length_km):
    """Annual expected event counts for the entire route, before discounting."""
    events = result["cost_quantities"]
    counts = np.array([joint.get("count", 1) for joint in joints])
    return {
        "Year": result["times"],
        "Leaks": counts @ result["joint_leak_step_pofs"],
        "Bursts": counts @ result["joint_burst_step_pofs"],
        "Type 1 only": events["Cr1"] - events["Cr2"],
        "Type 2": events["Cr2"],
        "ILI runs": events["inspection_cost_per_km"] / length_km,
        "Discounted cost ($M)": result["cpp"],
    }


def scenario_prices(baseline, joints, signature):
    import streamlit as st

    fields = [
        ("Cr1", "Base repair / excavation ($M per intervention)", 0.05),
        ("Cr2", "Additional type 2 repair ($M per intervention)", 0.05),
        ("inspection_cost_per_km", "ILI ($M per km per run)", 0.001),
    ]
    for mode, key in (("leak", "Cf_leak"), ("burst", "Cf_burst")):
        assigned = [key in joint.get("costs", {}) for joint in joints]
        if not all(assigned):
            label = f"Fallback {mode}" if any(assigned) else mode.capitalize()
            fields.append((key, f"{label} loss ($M per failure)", 0.1))
        if any(assigned):
            fields.append(("segment_" + mode, f"Saved segment {mode} losses (multiplier)", 0.1))
    fields.append(("discount_percent", "Annual discount rate (%)", 0.5))

    defaults = {**baseline, "segment_leak": 1.0, "segment_burst": 1.0,
                "discount_percent": 100.0 * baseline["rate"]}
    prices = defaults.copy()
    prefix = f"planning_cost_scenario_{signature}_"

    def reset():
        for key, _, _ in fields:
            st.session_state[prefix + key] = defaults[key]

    st.caption("Change costs or the discount rate here to update the results immediately. "
               "Each tested plan keeps its annual failure probabilities. Changing repair "
               "effectiveness or a schedule requires a new simulation.")
    columns = st.columns(3)
    for i, (key, label, step) in enumerate(fields):
        widget_key = prefix + key
        if widget_key not in st.session_state:
            st.session_state[widget_key] = float(defaults[key])
        prices[key] = columns[i % len(columns)].number_input(
            label, min_value=0.0, step=step,
            max_value=100.0 if key == "discount_percent" else None,
            format="%.4f", key=widget_key)
    st.button("Restore original costs", key=prefix + "reset", on_click=reset)
    if prices["discount_percent"] != defaults["discount_percent"]:
        prices["rate"] = prices["discount_percent"] / 100.0
    changed = any(prices[key] != defaults[key] for key, _, _ in fields)
    return prices, changed
