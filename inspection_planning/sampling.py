"""Independent Monte Carlo sampling with the original research sampler's stream.

The CDF/quantile transformation and Gumbel Euler constant preserve Sampling_2's
legacy results. Deterministic values (including any zero SD) are explicit.
"""
import math
import numpy as np
from scipy.stats import norm, lognorm, gumbel_r


def MC(names, distributions, means, stds, correlation1, correlation2,
       correlation_factors, count, Seed=0, CoV=0.02):
    del names, CoV
    if correlation1 or correlation2 or correlation_factors:
        raise ValueError('This planning sampler supports independent inputs only.')
    n = len(distributions)
    # Original sampler resets the global NumPy stream; maintain its run behavior.
    np.random.seed(Seed)
    standard = np.random.multivariate_normal(np.zeros(n), np.identity(n), count)
    samples = np.empty_like(standard)
    for j, (kind, mean, sd) in enumerate(zip(distributions, means, stds)):
        if not np.isfinite(mean) or not np.isfinite(sd) or sd < 0:
            raise ValueError('Property means and SDs must be finite; SD must be nonnegative.')
        if kind == 'Deterministic' or sd == 0:
            samples[:, j] = mean
            continue
        probability = norm.cdf(standard[:, j])
        if kind == 'Normal':
            samples[:, j] = norm.ppf(probability, mean, sd)
        elif kind == 'Lognormal':
            if mean <= 0:
                raise ValueError('A lognormal variable needs a positive mean.')
            shape = math.sqrt(math.log1p((sd / mean) ** 2))
            scale = math.exp(math.log(mean) - .5 * math.log1p((sd / mean) ** 2))
            samples[:, j] = lognorm.ppf(probability, shape, 0, scale)
        elif kind == 'Gumbel':
            scale = sd * math.sqrt(6) / math.pi
            samples[:, j] = gumbel_r.ppf(probability, mean - scale * .5772, scale)
        else:
            raise ValueError(f'Unsupported planning distribution: {kind}')
    return samples, standard
