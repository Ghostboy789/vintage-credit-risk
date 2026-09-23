"""Discrimination, calibration and stability statistics with the intervals fixed in
VALIDATION_PLAN.md section 4.

Every function takes plain arrays. Bootstraps resample loans (never loan-months), 1,000 times,
with seed 20260923, and use the percentile interval.
"""

import numpy as np
from scipy import stats

SEED = 20260923
N_BOOT = 1000
PSI_FLOOR = 0.0001  # share used for an empty bin (S5)
STABLE_BELOW, RED_ABOVE = 0.10, 0.25


def jeffreys(k: int, n: int) -> tuple[float, float]:
    """Jeffreys 95% interval of k events in n loans; the bound is 0 (1) when k = 0 (k = n)."""
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k + 0.5, n - k + 0.5))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 0.5, n - k + 0.5))
    return lo, hi


def wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson 95% score interval of k events in n loans."""
    z = stats.norm.ppf(0.975)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def auc_ks_from_counts(pos: np.ndarray, neg: np.ndarray) -> tuple[float, float]:
    """AUC and KS from default (pos) and non-default (neg) counts per risk cell, the cells
    ordered from lowest to highest risk. Ties count one half towards the AUC."""
    n_pos, n_neg = pos.sum(), neg.sum()
    neg_below = np.cumsum(neg) - neg
    auc = float((pos * (neg_below + 0.5 * neg)).sum() / (n_pos * n_neg))
    ks = float(np.abs(np.cumsum(pos) / n_pos - np.cumsum(neg) / n_neg).max())
    return auc, ks


def auc_ks(risk, y) -> tuple[float, float]:
    """AUC and KS of a risk measure (higher means riskier) against a 0/1 outcome."""
    codes = np.unique(np.asarray(risk), return_inverse=True)[1]
    y = np.asarray(y)
    m = codes.max() + 1
    return auc_ks_from_counts(
        np.bincount(codes[y == 1], minlength=m), np.bincount(codes[y == 0], minlength=m)
    )


def bootstrap_auc_ks(y, risks: list, seed: int = SEED, n_boot: int = N_BOOT):
    """AUC and KS of each risk array on the sample and on n_boot resamples of loans stratified by
    outcome. Every risk array sees the same resamples, so differences between them are paired.

    Returns (point, draws): point has shape (n_models, 2), draws (n_boot, n_models, 2), where the
    last axis is (AUC, KS).
    """
    y = np.asarray(y)
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    codes = [np.unique(np.asarray(r), return_inverse=True)[1] for r in risks]
    sizes = [c.max() + 1 for c in codes]

    def stat(p, q):
        return [
            auc_ks_from_counts(np.bincount(c[p], minlength=m), np.bincount(c[q], minlength=m))
            for c, m in zip(codes, sizes)
        ]

    point = np.array(stat(pos, neg))
    rng = np.random.default_rng(seed)
    draws = np.array(
        [
            stat(pos[rng.integers(0, len(pos), len(pos))], neg[rng.integers(0, len(neg), len(neg))])
            for _ in range(n_boot)
        ]
    )
    return point, draws


def percentile_interval(draws) -> tuple[float, float]:
    lo, hi = np.percentile(np.asarray(draws), [2.5, 97.5])
    return float(lo), float(hi)


def psi(expected_counts, actual_counts) -> float:
    """Population stability index; an empty bin takes a share of 0.0001 (S5)."""
    e = np.asarray(expected_counts, float)
    a = np.asarray(actual_counts, float)
    e = np.where(e == 0, PSI_FLOOR, e / e.sum())
    a = np.where(a == 0, PSI_FLOOR, a / a.sum())
    return float(((a - e) * np.log(a / e)).sum())


def bootstrap_psi(expected_counts, actual_counts, seed: int = SEED, n_boot: int = N_BOOT):
    """PSI on n_boot resamples of loans drawn separately from each sample, bin edges fixed.

    The bin counts of a with-replacement resample of n loans are multinomial(n, observed shares),
    so the resample is drawn on the counts directly.
    """
    e = np.asarray(expected_counts, float)
    a = np.asarray(actual_counts, float)
    rng = np.random.default_rng(seed)
    e_draws = rng.multinomial(int(e.sum()), e / e.sum(), size=n_boot)
    a_draws = rng.multinomial(int(a.sum()), a / a.sum(), size=n_boot)
    return np.array([psi(x, z) for x, z in zip(e_draws, a_draws)])


def decile_edges(reference_scores) -> np.ndarray:
    """S5 decile edges of the reference scores; repeated edges are dropped."""
    q = np.quantile(np.asarray(reference_scores), np.arange(1, 10) / 10, method="inverted_cdf")
    return np.unique(q)


def decile_bins(scores, edges) -> np.ndarray:
    """Bin index: score <= e1 is 0, e1 < score <= e2 is 1, ..., score > e_last is len(edges)."""
    return np.searchsorted(edges, np.asarray(scores), side="left")


def rag(value: float) -> str:
    """S5 stability RAG: below 0.10 green, 0.10 to 0.25 amber, above 0.25 red."""
    return "green" if value < STABLE_BELOW else ("amber" if value <= RED_ABOVE else "red")


def gini_drop_rag(relative_drop: float) -> str:
    """S2 RAG: at or below 10% green, above 10% and at or below 25% amber, above 25% red."""
    return "green" if relative_drop <= 0.10 else ("amber" if relative_drop <= 0.25 else "red")
