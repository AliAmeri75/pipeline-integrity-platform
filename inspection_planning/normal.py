"""Legacy normal-distribution API without mutating SciPy's shared objects."""
from scipy.stats import norm


def Normal_Samples(mean_value, std_value, seed_value, Num_samples):
    return norm.rvs(loc=mean_value, scale=std_value, size=Num_samples, random_state=seed_value)


def Normal_PDF(x, mean_value, std_value):
    return norm.pdf(x, loc=mean_value, scale=std_value)


def Normal_CDF(x, mean_value, std_value):
    return norm.cdf(x, loc=mean_value, scale=std_value)


def Normal_CDFInverse(p, mean_value, std_value):
    return norm.ppf(p, loc=mean_value, scale=std_value)
