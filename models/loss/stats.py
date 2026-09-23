"""Intervals, the weighted multinomial logit and the metric-object helper used by the loss engine.

Interval methods are the ones fixed in VALIDATION_PLAN.md section 4.
"""

import numpy as np
from scipy import stats

from tests import contracts as C

SEED = 20260923
N_BOOT = 1000
Z = 1.959963984540054


def metric(value, lo=None, hi=None, n=0, method=None) -> dict:
    """Metric object. A percentile interval that misses the point estimate (possible for skewed
    draws) is widened to include it, so that ci_low <= value <= ci_high always holds."""
    if value is None or not np.isfinite(value):
        return C.metric(None, n=int(n), ci_method=method if lo is None else "none: not computable")
    value = float(value)
    if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)):
        return C.metric(value, n=int(n), ci_method=method or "none: population total")
    return C.metric(value, float(min(lo, value)), float(max(hi, value)), int(n), method)


def wilson(k, n, method="wilson_95") -> dict:
    k, n = int(k), int(n)
    if n == 0:
        return metric(None, n=0, method="none: no observations")
    p = k / n
    den = 1 + Z * Z / n
    mid = (p + Z * Z / (2 * n)) / den
    half = Z * np.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return metric(p, max(0.0, mid - half), min(1.0, mid + half), n, method)


def jeffreys_bounds(k, n) -> tuple[float, float]:
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k + 0.5, n - k + 0.5))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 0.5, n - k + 0.5))
    return lo, hi


def jeffreys(k, n) -> dict:
    k, n = int(k), int(n)
    if n == 0:
        return metric(None, n=0, method="none: no observations")
    return metric(k / n, *jeffreys_bounds(k, n), n, "jeffreys_95")


def percentile(value, draws, n, method) -> dict:
    """Point estimate with the 2.5% and 97.5% percentiles of its draws."""
    d = np.asarray(draws, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return metric(value, n=n, method="none: no valid draws")
    return metric(value, np.percentile(d, 2.5), np.percentile(d, 97.5), n, method)


def boot_weights(n_obs: int, seed: int = SEED, n_boot: int = N_BOOT) -> np.ndarray:
    """Resample counts (n_boot x n_obs): each row is one bootstrap resample of the observations."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_obs, np.full(n_obs, 1 / n_obs), size=n_boot).astype(float)


def boot_mean(x, w_boot, mask=None) -> tuple[float, np.ndarray, int]:
    """Mean of x (over mask) and its bootstrap means under the resample counts w_boot."""
    x = np.asarray(x, dtype=float)
    mask = np.ones(len(x), bool) if mask is None else np.asarray(mask, bool)
    wb = w_boot[:, mask]
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = wb @ x[mask] / wb.sum(1)
    return float(x[mask].mean()) if mask.any() else float("nan"), draws, int(mask.sum())


def vasicek_quantile(q, pd_, rho=0.15):
    """Quantile of the Vasicek one-factor default-rate distribution (E3)."""
    g = stats.norm
    return g.cdf((np.sqrt(rho) * g.ppf(q) + g.ppf(pd_)) / np.sqrt(1 - rho))


def fit_mnlogit(X, Y, max_iter=100, tol=1e-9):
    """Multinomial logit by Newton-Raphson on grouped counts.

    X: cells x p design matrix. Y: cells x K outcome counts (column 0 is the reference outcome);
    fractional counts are allowed, which gives the fractional logit for K = 2. Frequency weights
    through the counts give exactly the loan-level maximum likelihood estimate.
    Returns (beta (K-1 x p), covariance of beta.ravel(), converged).
    """
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    c, p = X.shape
    k1 = Y.shape[1] - 1
    N = Y.sum(1)
    b = np.zeros(k1 * p)
    converged = False
    for _ in range(max_iter):
        P = probs(X, b.reshape(k1, p))
        grad = np.concatenate([X.T @ (Y[:, j + 1] - N * P[:, j + 1]) for j in range(k1)])
        H = np.zeros((k1 * p, k1 * p))
        for j in range(k1):
            for m in range(k1):
                w = N * P[:, j + 1] * ((j == m) - P[:, m + 1])
                H[j * p : (j + 1) * p, m * p : (m + 1) * p] = (X * w[:, None]).T @ X
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        b += step
        if np.max(np.abs(step)) < tol:
            converged = True
            break
    try:
        cov = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        cov, converged = np.full((k1 * p, k1 * p), np.nan), False
    if np.max(np.abs(b)) > 25:  # a level with no events: the estimate runs off to infinity
        converged = False
    return b.reshape(k1, p), cov, converged


def probs(X, B):
    """Outcome probabilities (cells x K) of a multinomial logit with reference outcome 0."""
    eta = np.column_stack([np.zeros(len(X)), X @ B.T])
    eta -= eta.max(1, keepdims=True)
    e = np.exp(eta)
    return e / e.sum(1, keepdims=True)


def design(df, cats: dict, cont=()):
    """Dummy-coded design matrix: intercept, one column per non-reference level, then the
    continuous columns. cats maps column -> ordered levels; the first level is the reference."""
    cols = [np.ones(len(df))]
    names = ["intercept"]
    for col, levels in cats.items():
        v = df[col].to_numpy()
        for lev in levels[1:]:
            cols.append((v == lev).astype(float))
            names.append(f"{col}={lev}")
    for col in cont:
        cols.append(df[col].to_numpy(float))
        names.append(col)
    return np.column_stack(cols), names


def independent_columns(X) -> list[int]:
    """Columns kept in order while each adds rank (drops aliased dummies, e.g. an MI band that
    is implied by an LTV band)."""
    keep = []
    for j in range(X.shape[1]):
        if np.linalg.matrix_rank(X[:, keep + [j]]) == len(keep) + 1:
            keep.append(j)
    return keep
