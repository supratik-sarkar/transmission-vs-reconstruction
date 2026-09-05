"""Closed-book prior probe (auxiliary measurement).

The primary causal receiver is pinned deterministic, under which one closed-book
probe returns only {0,1} -- too coarse for a dose-response. The probe therefore
uses STOCHASTIC decoding with m_prior independent fresh-context draws. That is
consistent with a pinned deterministic causal receiver because the probe
measures the receiver's prior, not the availability contrast.

P_hat is a binomial proportion with variance P(1-P)/m_prior: a mismeasured
regressor. Regressing R^- on P_hat would attenuate the slope toward zero, so
the paper does NOT depend on an errors-in-variables model. The primary
Experiment-B result is the matched-skeleton contrast, which involves no
prior-probe regressor at all; the dose-response is secondary and reported as a
RELIABILITY-AWARE STRATIFICATION across pre-registered bins whose width is large
relative to the binomial standard error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

M_PRIOR_DEFAULT = 10
#: Pre-registered cut-points. Bin width 1/3 versus a worst-case binomial SE of
#: 0.5/sqrt(10) ~ 0.158 at m_prior = 10.
PRIOR_BINS: tuple[tuple[float, float, str], ...] = (
    (0.0, 1 / 3, "low"),
    (1 / 3, 2 / 3, "medium"),
    (2 / 3, 1.0 + 1e-9, "high"),
)


@dataclass(frozen=True, slots=True)
class PriorProbeEstimate:
    atom_id: str
    successes: int
    m_prior: int

    @property
    def p_hat(self) -> float:
        return self.successes / self.m_prior if self.m_prior else float("nan")

    @property
    def binomial_se(self) -> float:
        p = self.p_hat
        return (
            float(np.sqrt(max(p * (1 - p), 0.0) / self.m_prior)) if self.m_prior else float("nan")
        )

    @property
    def bin_label(self) -> str:
        p = self.p_hat
        for lo, hi, label in PRIOR_BINS:
            if lo <= p < hi:
                return label
        return PRIOR_BINS[-1][2]


def estimate(atom_id: str, outcomes: Sequence[int]) -> PriorProbeEstimate:
    if not outcomes:
        raise ValueError("m_prior must be at least 1")
    if any(o not in (0, 1) for o in outcomes):
        raise ValueError("probe outcomes must be binary")
    return PriorProbeEstimate(atom_id, int(sum(outcomes)), len(outcomes))


@dataclass(frozen=True, slots=True)
class StratifiedTrend:
    bins: tuple[str, ...]
    means: tuple[float, ...]
    counts: tuple[int, ...]
    monotone_increasing: bool
    caveat: str


def stratified_dose_response(
    probes: Sequence[PriorProbeEstimate], r_minus: Sequence[float]
) -> StratifiedTrend:
    """Trend of R^- across prior-access bins.

    Reported instead of a slope on a mismeasured regressor. Bin assignment is
    itself noisy, which attenuates the observed trend; that limitation is stated
    with the result rather than corrected away.
    """
    if len(probes) != len(r_minus):
        raise ValueError("probe and outcome vectors must align")
    labels = [b[2] for b in PRIOR_BINS]
    means: list[float] = []
    counts: list[int] = []
    for label in labels:
        vals = [r for p, r in zip(probes, r_minus, strict=False) if p.bin_label == label]
        counts.append(len(vals))
        means.append(float(np.mean(vals)) if vals else float("nan"))
    populated = [m for m in means if not np.isnan(m)]
    monotone = all(a <= b + 1e-12 for a, b in zip(populated, populated[1:], strict=False))
    return StratifiedTrend(
        tuple(labels),
        tuple(means),
        tuple(counts),
        monotone,
        "Bin assignment is measured with binomial error P(1-P)/m_prior, which "
        "attenuates the observed trend toward flatness.",
    )


def order_invariance_check(
    outcomes_forward: Sequence[int], outcomes_shuffled: Sequence[int]
) -> float:
    """Agreement between probes issued in fixed and in randomised slot order.

    A batched autoregressive vector would let earlier slots condition later
    ones, so the probe would partly measure self-conditioning rather than prior
    access. One focal atom per query is the primary protocol; this check
    quantifies the residual risk when batching is used.
    """
    if len(outcomes_forward) != len(outcomes_shuffled) or not outcomes_forward:
        raise ValueError("order-invariance vectors must be non-empty and aligned")
    agree = sum(1 for a, b in zip(outcomes_forward, outcomes_shuffled, strict=False) if a == b)
    return agree / len(outcomes_forward)
