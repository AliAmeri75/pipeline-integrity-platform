"""Bounded-memory execution of fixed-interval Monte Carlo planning.

Each batch calls the existing physical model. Costs, joint first-event CDFs and
operating-step failure counts are pooled over retained realizations before
rebuilding system POF and annual operating POF.
System probabilities and batch Safe/Unsafe flags must never be averaged.
Threshold scheduling is deliberately excluded: its decisions need the whole
population's probability at each time step.
"""
from copy import deepcopy
import hashlib
import time

import numpy as np

from inspection_planning import engine


EXECUTION_REVISION = 'fixed-interval-pof-v5-technique-residual-depth'
MEAN_OUTPUTS = (6, 7, 8, 9, 12, 13, 14)


def effective_batch_size(joints, horizon, dt, requested, *, memory_target_mb=32):
    """Conservative array estimate; server/Python overhead is additional."""
    if int(requested) != requested or requested < 1:
        raise ValueError('Samples per batch must be a positive integer.')
    rates = [float(joint.get('birth_rate', 0.)) for joint in joints]
    worst = int(np.ceil(engine.exp_num(horizon, max(rates, default=0.)))) + 40
    times = len(np.arange(0, horizon + dt, dt))
    initial = sum(len(joint.get('cracks', [])) for joint in joints)
    # Six dense crack-state arrays plus sample properties, action history and
    # an allowance for the corresponding Python lists/objects.
    per_sample = (6 * (initial + len(joints) * worst) * 8 +
                  len(joints) * (times + 512) + initial * 16)
    affordable = max(1, int(memory_target_mb * 1024**2 / max(per_sample, 1)))
    return min(int(requested), affordable)


def _pooled_result(state, joints, costs, sim):
    retained = state['retained']
    if not retained:
        raise RuntimeError('All Monte Carlo samples failed at time zero.')
    times = state['times']
    joint_leak = state['joint_leak_counts'] / retained
    joint_burst = state['joint_burst_counts'] / retained
    counts = np.asarray([joint.get('count', 1) for joint in joints], dtype=int)
    length = float(costs['pipe_length_km'])
    joint_leak_steps = state['joint_leak_step_counts'] / retained
    joint_burst_steps = state['joint_burst_step_counts'] / retained
    leak, _ = engine.grouped_system_pof_history(joint_leak, counts, times, length)
    burst, _ = engine.grouped_system_pof_history(joint_burst, counts, times, length)
    leak_step, leak_per_km = engine.grouped_annual_failure_pofs(
        joint_leak_steps, counts, times, length)
    burst_step, burst_per_km = engine.grouped_annual_failure_pofs(
        joint_burst_steps, counts, times, length)
    leak_annual = engine.annualize_system_step_pofs(leak_step, times)
    burst_annual = engine.annualize_system_step_pofs(burst_step, times)
    unsafe = [(float(t), float(l), float(b)) for t, l, b in
              zip(times, leak_annual, burst_annual)
              if engine.exceeds_safety_criteria(l, b, sim)]
    outputs = [None] * 17
    outputs[:6] = [times.copy(), leak, burst, leak_per_km, burst_per_km,
                   state['inspections'].copy()]
    for index in MEAN_OUTPUTS:
        outputs[index] = state['sums'][index] / retained
    outputs[10], outputs[11], outputs[15] = not unsafe, unsafe, []
    outputs[16] = dict(times=times.copy(), crack_depths=None, crack_lengths=None,
        active_cracks=None, wall_thickness=None, inspection_times=state['inspections'].copy(),
        sample_idx=0, crack_count_group=len(joints[0].get('cracks', [])),
        joint_name=state['joint_names'][0], joint_names=list(state['joint_names']),
        joint_leak_pofs=joint_leak, joint_burst_pofs=joint_burst,
        joint_leak_step_pofs=joint_leak_steps, joint_burst_step_pofs=joint_burst_steps,
        system_leak_annual_pof=leak_annual, system_burst_annual_pof=burst_annual,
        safety_probability_basis='Annual probability of at least one failure anywhere on the full route',
        requested_samples=state['requested'], retained_samples=retained,
        initial_survival_conditioning=True, batch_size=state['batch_size'],
        probability_basis='At least one failure of each mode per joint realization',
        annual_probability_basis='Actual failures in each operating time step, including repeat failures',
        completed_batches=state['batches'], execution_revision=EXECUTION_REVISION)
    for key in ('joint_leak_event_means', 'joint_burst_event_means'):
        if key + '_sum' in state:
            outputs[16][key] = state[key + '_sum'] / retained
    return tuple(outputs)


def run_batched_flexible_simulation(
    approach, T, dt, nx, joints, costs, sim_params, S_err, q_pod,
    *, default_birth_rate=0., property_seed=0, crack_length_std=15.6,
    crack_depth_std=.74, track_debug=False, decision_mode=engine.ILI_DECISION_MODE,
    batch_size=250, state=None, on_progress=None,
):
    """Run/resume one fixed-interval candidate without retaining sample histories.

    ``state`` is a small accumulator the caller may keep in session storage.
    It is updated only after a batch completes. A server restart still erases
    session storage. Fixed seeds reproduce a run for the same batch size; changing
    batch size changes the Monte Carlo realizations, not the model equations.
    """
    if approach != 'equidistant':
        raise ValueError('Batched execution supports fixed/equidistant planning only.')
    if track_debug:
        raise ValueError('Use the original engine when full sample histories are needed.')
    if int(nx) != nx or nx < 1:
        raise ValueError('Monte Carlo sample count must be a positive integer.')
    if not joints or T <= 0 or dt <= 0 or float(costs['pipe_length_km']) <= 0:
        raise ValueError('Provide joints, a positive horizon/time step and pipeline length.')
    if decision_mode not in engine.DECISION_MODES:
        raise ValueError('Choose prior excavation or ILI-informed planning.')
    engine.safety_limits(sim_params)
    joints = deepcopy(joints)
    for joint in joints:
        joint.setdefault('birth_rate', default_birth_rate)
    batch_size = min(int(nx), effective_batch_size(joints, T, dt, batch_size))
    signature = hashlib.sha256(repr((EXECUTION_REVISION, T, dt, nx, joints, costs,
        sim_params, S_err, q_pod, default_birth_rate, property_seed,
        crack_length_std, crack_depth_std, decision_mode, batch_size)).encode()).hexdigest()
    state = {} if state is None else state
    if state and state.get('signature') != signature:
        raise ValueError('The saved execution checkpoint belongs to different planning inputs.')
    if not state:
        state.update(signature=signature, requested=int(nx), processed=0, retained=0,
                     batches=0, batch_size=batch_size, elapsed_seconds=0.)
    while state['processed'] < nx:
        number = min(batch_size, int(nx) - state['processed'])
        index = state['batches']
        if index == 0:
            random_seed = sample_seed = int(property_seed)
        else:
            random_seed, sample_seed = map(int, np.random.SeedSequence(
                [int(property_seed), index, 0xA11]).generate_state(2))
        if on_progress is not None:
            on_progress(state['processed'], int(nx), state['retained'])
        started = time.perf_counter()
        np.random.seed(random_seed)
        try:
            raw = engine.run_flexible_simulation(approach, T, dt, number, joints,
                costs, sim_params, S_err, q_pod, default_birth_rate=default_birth_rate,
                property_seed=sample_seed, crack_length_std=crack_length_std,
                crack_depth_std=crack_depth_std, track_debug=False, decision_mode=decision_mode)
        except RuntimeError as error:
            if str(error) != 'All Monte Carlo samples failed at time zero.':
                raise
            raw = None
        update = dict(processed=state['processed'] + number, batches=index + 1,
            elapsed_seconds=state['elapsed_seconds'] + time.perf_counter() - started)
        if raw is not None:
            debug = raw[16]
            weight = int(debug['retained_samples'])
            if state['retained']:
                if not np.array_equal(state['times'], raw[0]) or state['joint_names'] != debug['joint_names']:
                    raise ValueError('Batch time axes or joint populations differ.')
            update.update(retained=state['retained'] + weight,
                times=np.asarray(raw[0]).copy(), inspections=np.asarray(raw[5]).copy(),
                joint_names=list(debug['joint_names']))
            update['sums'] = {i: state.get('sums', {}).get(i, 0.) + weight * np.asarray(raw[i])
                              for i in MEAN_OUTPUTS}
            update['joint_leak_counts'] = state.get('joint_leak_counts', 0.) + weight * np.asarray(debug['joint_leak_pofs'])
            update['joint_burst_counts'] = state.get('joint_burst_counts', 0.) + weight * np.asarray(debug['joint_burst_pofs'])
            update['joint_leak_step_counts'] = state.get('joint_leak_step_counts', 0.) + weight * np.asarray(debug['joint_leak_step_pofs'])
            update['joint_burst_step_counts'] = state.get('joint_burst_step_counts', 0.) + weight * np.asarray(debug['joint_burst_step_pofs'])
            for key in ('joint_leak_event_means', 'joint_burst_event_means'):
                if key in debug:
                    update[key + '_sum'] = state.get(key + '_sum', 0.) + weight * np.asarray(debug[key])
        # Commit small sufficient statistics, then release the batch's raw outputs.
        state.update(update)
        del raw
    if on_progress is not None:
        on_progress(int(nx), int(nx), state['retained'])
    return _pooled_result(state, joints, costs, sim_params)
