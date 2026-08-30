from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .models import AtomCausalRecord


@dataclass(frozen=True)
class Decomposition:
    endpoint_fidelity: float
    r_bar: float
    t_bar: float
    delta_bar: float
    volume: float
    alignment: float
    c_comm: float
    reconstruction_contribution: float
    r_obs: float | None
    observational_bias: float | None


def _hajek(values: np.ndarray, weights: np.ndarray) -> float:
    denom = weights.sum()
    if denom <= 0:
        raise ValueError("Non-positive Hájek denominator")
    return float(np.sum(weights * values) / denom)


def decompose(records: Sequence[AtomCausalRecord]) -> Decomposition:
    if not records:
        raise ValueError("records must be non-empty")
    w = np.asarray([1.0 / r.pi for r in records], dtype=float)
    t = np.asarray([r.transmitted for r in records], dtype=float)
    rminus = np.asarray([r.r_minus for r in records], dtype=float)
    dplus = np.asarray([r.d_plus for r in records], dtype=float)
    delta = dplus - rminus
    yobs = np.where(t == 1, dplus, rminus)

    a = _hajek(yobs, w)
    r_bar = _hajek(rminus, w)
    t_bar = _hajek(t, w)
    d_bar = _hajek(delta, w)
    etd = _hajek(t * delta, w)
    alignment = etd - t_bar * d_bar
    volume = t_bar * d_bar
    c_comm = a - r_bar
    recon = _hajek((1 - t) * rminus, w)

    omitted = t == 0
    if omitted.any():
        r_obs = _hajek(rminus[omitted], w[omitted])
        obs_bias = r_obs - r_bar
    else:
        r_obs = None
        obs_bias = None

    return Decomposition(
        endpoint_fidelity=a,
        r_bar=r_bar,
        t_bar=t_bar,
        delta_bar=d_bar,
        volume=volume,
        alignment=alignment,
        c_comm=c_comm,
        reconstruction_contribution=recon,
        r_obs=r_obs,
        observational_bias=obs_bias,
    )
