"""Sham-edit correction and partial identification.

The artefact is modelled on the MEAN-RESPONSE scale, not on realisations:
realised outcomes are binary, so an additive model on realisations is not
closed in [0,1].

    mu^E_iz(w) - mu_iz(w) = eps_m + u_iz,   E[u_iz | m] = 0

with m in {del, ins}. The placebo estimates the mechanism-average eps_m.

The correction is MECHANISM-DEPENDENT IN SIGN. For a transmitted atom the
edited side produces R^-, which enters Delta = D^+ - R^- negatively; for an
omitted atom the edited side produces D^+, which enters positively. Writing

    s_iz = 2 T_iz - 1  in  {-1, +1}

both cases collapse to Delta = Delta_hat + s_iz * eps_m(z). Applying a common
offset to both arms would double-count the artefact on one arm and cancel it on
the other -- an error an earlier draft of the analysis contained.

The region is a POPULATION statement. The placebo estimates the mechanism
average; the per-atom artefact is eps_m + u_iz with u_iz mean-zero but not
bounded by anything the placebo measures. An atom-level interval therefore
requires a separate, explicitly stated bound on |u_iz|.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..models import AtomCausalRecord
from .weighting import design_weights, hajek

SIGN_DEL = +1
SIGN_INS = -1


def sign_for(transmitted: int) -> int:
    """s = 2T - 1."""
    return 2 * transmitted - 1


@dataclass(frozen=True, slots=True)
class ShamEstimate:
    mechanism: str
    epsilon_mechanical: float
    n: int


@dataclass(frozen=True, slots=True)
class PartialRegion:
    mechanism: str
    point_raw: float
    point_corrected: float
    lower: float
    upper: float
    epsilon_bar: float
    n: int

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def excludes_zero(self) -> bool:
        return self.lower > 0.0 or self.upper < 0.0


def estimate_sham(
    outcomes_sham: Sequence[float], outcomes_natural: Sequence[float], mechanism: str
) -> ShamEstimate:
    """eps_mech_m = E[Y(M^sham,m) - Y(M^obs)] over the sham subset.

    The sham subset is drawn independently of T.
    """
    a = np.asarray(outcomes_sham, dtype=float)
    b = np.asarray(outcomes_natural, dtype=float)
    if a.shape != b.shape:
        raise ValueError("sham and natural outcome vectors must align")
    if a.size == 0:
        raise ValueError("empty sham subset")
    return ShamEstimate(mechanism, float(np.mean(a - b)), int(a.size))


def corrected_delta(record: AtomCausalRecord, epsilon_mech: float) -> float:
    """Delta_iz = Delta_hat_iz + s_iz * eps_m(z)."""
    return record.delta_avail + sign_for(record.transmitted) * epsilon_mech


def population_region(
    records: Sequence[AtomCausalRecord],
    *,
    epsilon_del: float,
    epsilon_ins: float,
    epsilon_bar: float,
    mechanism: str = "pooled",
) -> PartialRegion:
    """Design-weighted region for the population-average surplus.

    Conclusions are those that survive across the whole region, reported as a
    function of ``epsilon_bar``, the assumed bound on the residual SEMANTIC
    component that the placebo does NOT measure.
    """
    if epsilon_bar < 0:
        raise ValueError("epsilon_bar must be non-negative")
    if mechanism == "del":
        subset = [r for r in records if r.transmitted == 1]
    elif mechanism == "ins":
        subset = [r for r in records if r.transmitted == 0]
    elif mechanism == "pooled":
        subset = list(records)
    else:
        raise ValueError(f"unknown mechanism {mechanism!r}")
    if not subset:
        raise ValueError(f"no records for mechanism {mechanism!r}")

    w = design_weights(np.array([r.pi for r in subset], dtype=float))
    raw = hajek(np.array([r.delta_avail for r in subset]), w)
    corrected = hajek(
        np.array(
            [corrected_delta(r, epsilon_del if r.transmitted == 1 else epsilon_ins) for r in subset]
        ),
        w,
    )
    lower = max(-1.0, corrected - epsilon_bar)
    upper = min(1.0, corrected + epsilon_bar)
    return PartialRegion(mechanism, raw, corrected, lower, upper, epsilon_bar, len(subset))


def atom_region(
    record: AtomCausalRecord, *, epsilon_mech: float, epsilon_bar: float, u_bar: float
) -> tuple[float, float]:
    """Atom-level interval. Requires the ADDITIONAL bound |u_iz| <= u_bar, which
    the placebo does not supply. Never present an atom-level guarantee from a
    mechanism-average placebo alone."""
    if u_bar < 0 or epsilon_bar < 0:
        raise ValueError("bounds must be non-negative")
    centre = corrected_delta(record, epsilon_mech)
    half = epsilon_bar + u_bar
    return (max(-1.0, centre - half), min(1.0, centre + half))
