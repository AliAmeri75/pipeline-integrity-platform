"""Vectorized lifecycle-cost helpers used by Cpp_Calculator_parallel.py.

The original :mod:`Cost` module is intentionally left unchanged.  These
functions evaluate all Monte Carlo paths in one NumPy call and cache the
true-path costs that do not depend on inspection time, measurement quality,
or the policy threshold.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TrueCostCache:
    """Discounted true-path cost prefixes for every Monte Carlo sample."""

    prefix: np.ndarray
    no_repair: np.ndarray
    discount: np.ndarray
    horizon: int


def _paths(values, horizon, name):
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[1] < horizon + 1:
        raise ValueError(
            f"{name} must have shape (n_samples, at least {horizon + 1}); "
            f"received {array.shape}"
        )
    return array[:, : horizon + 1]


def build_true_cost_cache(
    pfx_leak,
    pfx_burst,
    cf_leak,
    cf_burst,
    rate,
    horizon,
):
    """Precompute true-path costs shared by every policy calculation.

    ``prefix[:, t]`` is the discounted expected failure cost accumulated from
    year 0 up to repair time ``t``.  ``prefix[:, 0]`` is zero and
    ``prefix[:, horizon]`` is the cost of no repair.
    """

    pfx_leak = _paths(pfx_leak, horizon, "pfx_leak")
    pfx_burst = _paths(pfx_burst, horizon, "pfx_burst")
    if pfx_leak.shape != pfx_burst.shape:
        raise ValueError("pfx_leak and pfx_burst must have the same shape")

    discount = np.power(1.0 + rate, -np.arange(horizon + 1, dtype=float))
    leak_without_burst = (1.0 - pfx_burst) * pfx_leak

    delta_leak = np.diff(leak_without_burst, axis=1)
    delta_burst = np.diff(pfx_burst, axis=1)
    annual_cost = cf_leak * delta_leak + cf_burst * delta_burst
    discounted_cost = annual_cost * discount[1 : horizon + 1]

    prefix = np.empty((pfx_leak.shape[0], horizon + 1), dtype=float)
    prefix[:, 0] = 0.0
    np.cumsum(discounted_cost, axis=1, out=prefix[:, 1:])

    return TrueCostCache(
        prefix=prefix,
        no_repair=prefix[:, horizon],
        discount=discount,
        horizon=horizon,
    )


def _validate_updated_paths(pf_y_leak, pf_y_burst, cache):
    pf_y_leak = _paths(pf_y_leak, cache.horizon, "pf_y_leak")
    pf_y_burst = _paths(pf_y_burst, cache.horizon, "pf_y_burst")
    if pf_y_leak.shape != pf_y_burst.shape:
        raise ValueError("pf_y_leak and pf_y_burst must have the same shape")
    if pf_y_leak.shape[0] != cache.prefix.shape[0]:
        raise ValueError("updated and true paths must have the same sample count")
    return pf_y_leak, pf_y_burst


def _detected_cost(repair_time, cache, repair_cost):
    """Evaluate true-path cost for one or more repair-time rows."""

    repair_time = np.asarray(repair_time, dtype=np.intp)
    sample_count = cache.prefix.shape[0]

    if repair_time.ndim == 1:
        sample_index = np.arange(sample_count)
    elif repair_time.ndim == 2:
        sample_index = np.broadcast_to(
            np.arange(sample_count), repair_time.shape
        )
    else:
        raise ValueError("repair_time must be a one- or two-dimensional array")

    detected = (
        cache.prefix[sample_index, repair_time]
        + repair_cost * cache.discount[repair_time]
    )
    return np.where(repair_time < cache.horizon, detected, cache.no_repair)


def cp_pi2_batch(
    pod,
    cache,
    pf_y_leak,
    pf_y_burst,
    cf_leak,
    cf_burst,
    repair_cost,
    inspection_time,
    thresholds,
    return_details=False,
):
    """Evaluate policy pi2 for all samples and thresholds at once.

    Returns one population-mean cost per threshold.  The policy searches for
    the first future year where

        Hf_comb = Hf_burst + Hf_leak * Cf_leak / Cf_burst

    exceeds the threshold, and performs that search for every sample in a
    batch.
    """

    pf_y_leak, pf_y_burst = _validate_updated_paths(
        pf_y_leak, pf_y_burst, cache
    )
    inspection_time = int(inspection_time)
    if not 0 <= inspection_time < cache.horizon:
        raise ValueError("inspection_time must be in [0, horizon)")
    if cf_burst == 0:
        raise ValueError("cf_burst must be nonzero for the combined hazard")

    pod = np.asarray(pod, dtype=float)
    if pod.shape != (cache.prefix.shape[0],):
        raise ValueError("pod must contain one value per sample")

    thresholds = np.atleast_1d(np.asarray(thresholds, dtype=float))
    pf_burst_after_inspection = pf_y_burst[:, inspection_time:]
    pf_leak_after_inspection = pf_y_leak[:, inspection_time:]
    with np.errstate(divide="ignore", invalid="ignore"):
        burst_hazard = np.diff(pf_burst_after_inspection, axis=1) / (
            1.0 - pf_burst_after_inspection[:, :-1]
        )
        leak_hazard = np.diff(pf_leak_after_inspection, axis=1) / (
            1.0 - pf_leak_after_inspection[:, :-1]
        )
    combined_hazard = burst_hazard + leak_hazard * (cf_leak / cf_burst)

    above = combined_hazard[None, :, :] > thresholds[:, None, None]
    has_repair = np.any(above, axis=2)
    first_offset = np.argmax(above, axis=2)
    repair_time = np.where(
        has_repair,
        inspection_time + first_offset,
        cache.horizon,
    )

    detected = _detected_cost(repair_time, cache, repair_cost)
    expected = detected * pod[None, :] + cache.no_repair * (1.0 - pod[None, :])
    means = np.mean(expected, axis=1)

    if return_details:
        return means, expected, repair_time
    return means


def cp_pi1_batch(
    pod,
    cache,
    pf_y_leak,
    pf_y_burst,
    cf_leak,
    cf_burst,
    repair_cost,
    inspection_time,
    return_details=False,
):
    """Evaluate policy pi1 for every sample using cumulative candidate costs."""

    pf_y_leak, pf_y_burst = _validate_updated_paths(
        pf_y_leak, pf_y_burst, cache
    )
    inspection_time = int(inspection_time)
    if not 0 <= inspection_time < cache.horizon:
        raise ValueError("inspection_time must be in [0, horizon)")

    pod = np.asarray(pod, dtype=float)
    if pod.shape != (cache.prefix.shape[0],):
        raise ValueError("pod must contain one value per sample")

    remaining = cache.horizon - inspection_time
    leak_without_burst = (1.0 - pf_y_burst) * pf_y_leak
    delta_leak = np.diff(leak_without_burst, axis=1)[
        :, inspection_time : cache.horizon
    ]
    delta_burst = np.diff(pf_y_burst, axis=1)[
        :, inspection_time : cache.horizon
    ]

    relative_failure_cost = (
        cf_leak * delta_leak + cf_burst * delta_burst
    ) * cache.discount[1 : remaining + 1]

    # Column k is the failure cost tolerated before a repair k years after the
    # inspection.  The last column is the no-repair alternative.
    relative_prefix = np.empty(
        (pf_y_leak.shape[0], remaining + 1), dtype=float
    )
    relative_prefix[:, 0] = 0.0
    np.cumsum(relative_failure_cost, axis=1, out=relative_prefix[:, 1:])

    repair_candidates = (
        relative_prefix[:, :remaining]
        + repair_cost * cache.discount[:remaining]
    )
    candidate_costs = np.concatenate(
        (repair_candidates, relative_prefix[:, -1:]), axis=1
    )
    best_offset = np.argmin(candidate_costs, axis=1)
    repair_time = np.where(
        best_offset == remaining,
        cache.horizon,
        inspection_time + best_offset,
    )

    detected = _detected_cost(repair_time, cache, repair_cost)
    expected = detected * pod + cache.no_repair * (1.0 - pod)
    mean = float(np.mean(expected))

    if return_details:
        return mean, expected, repair_time
    return mean
