"""Explain a planning safety decision using the same annual operating POFs."""
import numpy as np

from inspection_planning.engine import grouped_annual_failure_pofs


def interval_safety_rows(results, method):
    """Report the limiting mode and year without substituting cost optimality."""
    rows = []
    for result in results:
        times = np.asarray(result['times'])
        leak = np.asarray(result['leak_hazard'])
        burst = np.asarray(result['burst_hazard'])
        leak_limit = float(result['max_annual_leak_pof'])
        burst_limit = float(result['max_annual_burst_pof'])
        leak_exceeded, burst_exceeded = leak > leak_limit, burst > burst_limit
        exceeded = np.flatnonzero(leak_exceeded | burst_exceeded)
        modes = [name for name, mask in [('Leakage', leak_exceeded), ('Burst', burst_exceeded)] if mask.any()]
        rows.append({
            'Method': method,
            'Interval (years)': result['interval'],
            'Status': 'Unsafe' if len(exceeded) else 'Safe',
            'Peak annual PfL / km-year': float(np.max(leak)),
            'Leakage peak year': float(times[np.argmax(leak)]),
            'Peak annual PfB / km-year': float(np.max(burst)),
            'Burst peak year': float(times[np.argmax(burst)]),
            'First limit exceedance (year)': float(times[exceeded[0]]) if len(exceeded) else None,
            'Exceeded criterion': ' and '.join(modes) if modes else 'None',
        })
    return rows


def joint_safety_rows(result, joints, pipe_length_km):
    """Evaluate each group alone over the route length, not additive contributions.

    A counted clean group estimates one common marginal distribution for its
    physical joints. The one-event increment is a resolution indicator, not a
    confidence interval or a guaranteed error bound.
    """
    definitions = {joint['name']: joint for joint in joints}
    if set(definitions) != set(result['joint_names']):
        raise ValueError('Joint definitions do not match the result names.')
    retained = int(result['retained_samples'])
    if retained <= 0:
        raise ValueError('Retained sample count must be positive.')
    rows = []
    for index, name in enumerate(result['joint_names']):
        joint = definitions[name]
        count = int(joint.get('count', 1))
        peaks = []
        for key in ['joint_leak_step_pofs', 'joint_burst_step_pofs']:
            _, annual = grouped_annual_failure_pofs(
                np.asarray(result[key])[index:index + 1], [count],
                result['times'], pipe_length_km)
            peaks.append(float(np.max(annual)))
        rows.append({
            'Joint / group': name,
            'Physical joints represented': count,
            'Initial cracks per joint': len(joint.get('cracks', [])),
            'Peak group PfL / km-year': peaks[0],
            'Peak group PfB / km-year': peaks[1],
            'Approx. one-event increment / km': count / retained / pipe_length_km,
        })
    return sorted(rows, key=lambda row: max(row['Peak group PfL / km-year'],
                                           row['Peak group PfB / km-year']), reverse=True)
