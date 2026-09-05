"""Design-based weighting.

Two estimators are provided and are NOT interchangeable:

* Horvitz-Thompson  E_HT[g] = |N|^-1 * sum_S g / pi          -- needs |N|
* Hajek             E[g]    = sum_S g/pi  /  sum_S 1/pi      -- ratio form

The Hajek form is the manuscript default, because |N| is known only up to
atomiser behaviour and the ratio is invariant to that. Reporting an unweighted
pooled mean is never correct here: role strata are sampled at equal sizes while
their inventory frequencies differ, so an unweighted mean estimates the
stratum-balanced population, and R^- varies strongly across roles.

Two-phase weighting supports a randomised intervention subsample with known
q_iz > 0: population identification does not require instrumenting every
sampled atom, only atom-level effects do.
"""

from __future__ import annotations

import numpy as np


class PositivityError(ValueError):
    pass


def _check(pi: np.ndarray) -> None:
    if pi.size == 0:
        raise ValueError("empty sample")
    if np.any(pi <= 0):
        raise PositivityError(
            "inclusion probability <= 0 for a sampled atom: the design violates "
            "positivity and the estimator is undefined on part of the target population"
        )
    if np.any(pi > 1 + 1e-12):
        raise PositivityError("inclusion probability greater than 1")


def design_weights(pi: np.ndarray, q: np.ndarray | None = None) -> np.ndarray:
    pi = np.asarray(pi, dtype=float)
    _check(pi)
    if q is None:
        return 1.0 / pi
    q = np.asarray(q, dtype=float)
    if np.any(q <= 0):
        raise PositivityError("second-phase probability q <= 0")
    return 1.0 / (pi * q)


def hajek(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    denom = float(weights.sum())
    if denom <= 0:
        raise ValueError("non-positive Hajek denominator")
    return float(np.sum(weights * values) / denom)


def horvitz_thompson(values: np.ndarray, weights: np.ndarray, population_size: int) -> float:
    if population_size <= 0:
        raise ValueError("population_size must be positive for the HT form")
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    return float(np.sum(weights * values) / population_size)


def weighted_covariance(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> float:
    """Cov(x, y) under the design measure, computed as E[xy] - E[x]E[y] with all
    three expectations taken in Hajek form so the decomposition identity closes
    exactly."""
    return hajek(np.asarray(x) * np.asarray(y), weights) - hajek(x, weights) * hajek(y, weights)


def stratum_balance_discrepancy(
    values: np.ndarray, weights: np.ndarray, strata: np.ndarray
) -> float:
    """E[g] - E_balanced[g] = sum_s (w_s - b_s) E[g | s].

    Non-zero exactly when g varies across roles. Reported so that a weighted and
    an unweighted pooled number are never confused for one another.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    strata = np.asarray(strata)
    labels = np.unique(strata)
    total_w = weights.sum()
    n = len(values)
    out = 0.0
    for lab in labels:
        mask = strata == lab
        if not mask.any():
            continue
        w_s = weights[mask].sum() / total_w
        b_s = mask.sum() / n
        mean_s = hajek(values[mask], weights[mask])
        out += (w_s - b_s) * mean_s
    return float(out)
