"""The endpoint-fidelity decomposition and its diagnostics.

    A = Rbar_0 + Tbar * Deltabar + Cov(T, Delta^av)

The identity is elementary -- it is the law of total expectation for a binary
treatment -- and no algebraic novelty is claimed for it. Its content is that
each term is separately identifiable by intervention, and that the three answer
different questions.

The covariance term is named ASSIGNMENT-EFFECT ALIGNMENT. A positive value says
transmitted atoms tend to carry larger surplus. That is an association, not
evidence of deliberate or efficient allocation; whether a scarce budget is
allocated well is answered only by the budget-neutral benchmark.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ..models import AtomCausalRecord
from .weighting import design_weights, hajek, weighted_covariance


@dataclass(frozen=True, slots=True)
class Decomposition:
    n_atoms: int
    n_documents: int
    endpoint_fidelity: float  # A
    r_bar_zero: float  # Rbar_0   reconstruction
    t_bar: float  # Tbar
    delta_bar: float  # Deltabar
    volume: float  # Tbar * Deltabar
    alignment: float  # Cov(T, Delta)
    c_comm: float  # A - Rbar_0   (signed)
    c_recon: float  # E[(1-T) R^-]
    phi: float | None  # C_comm / A, only when A > 0
    r_observational: float | None  # E[R^- | T=0]
    selection_bias: float | None  # R_obs - Rbar_0, by definition
    selection_bias_identity: float | None  # -Cov(T, R^-) / (1 - Tbar)
    selection_bias_conditional: float | None  # Tbar * (E[R^-|T=0] - E[R^-|T=1])
    selection_bias_max_discrepancy: float | None
    prob_delta_negative: float | None
    identity_residual: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decompose(
    records: Sequence[AtomCausalRecord],
    *,
    use_two_phase: bool = False,
    atom_level_statistics: bool = True,
) -> Decomposition:
    """Design-weighted (Hajek) decomposition.

    ``atom_level_statistics`` must be False under decoder regime (S) with a
    single draw per availability: P[Delta < 0] is a nonlinear function of an
    atom-level quantity and is inconsistent there, because with binary draws the
    realised difference lies in {-1, 0, 1} and estimates a smeared quantity.
    """
    if not records:
        raise ValueError("records must be non-empty")

    pi = np.array([r.pi for r in records], dtype=float)
    q = np.array([r.q for r in records], dtype=float) if use_two_phase else None
    w = design_weights(pi, q)

    t = np.array([float(r.transmitted) for r in records])
    r_minus = np.array([r.r_minus for r in records])
    d_plus = np.array([r.d_plus for r in records])
    delta = d_plus - r_minus
    y_obs = np.where(t == 1.0, d_plus, r_minus)

    a = hajek(y_obs, w)
    r0 = hajek(r_minus, w)
    t_bar = hajek(t, w)
    d_bar = hajek(delta, w)
    align = weighted_covariance(t, delta, w)
    volume = t_bar * d_bar
    c_comm = a - r0
    c_recon = hajek((1.0 - t) * r_minus, w)

    # The selection bias is computed THREE ways and the maximum discrepancy is
    # carried in the result. The three routes are algebraically identical under
    # Hajek weighting but computationally independent:
    #
    #   (a) by definition           R^obs - Rbar_0
    #   (b) covariance form        -Cov(T, R^-) / (1 - Tbar)
    #   (c) conditional-mean form   Tbar * (E[R^-|T=0] - E[R^-|T=1])
    #
    # (b) goes through the weighted covariance; (c) goes through two conditional
    # Hajek means. A weighting defect in either path would separate them, which a
    # single-route check could not detect.
    omitted = t == 0.0
    transmitted = t == 1.0

    # These two quantities have DIFFERENT existence conditions, and conflating
    # them would misreport one as undefined whenever the other is.
    #
    #   R^obs = E[R^- | T=0]  needs only the OMITTED arm.
    #   the selection BIAS    is a contrast against Rbar_0, so it additionally
    #                         needs the transmitted arm and Tbar in (0,1).
    #
    # A sample with no transmitted atom therefore still has a well-defined
    # R^obs, and reporting it as None would hide a quantity we can measure.
    r_obs: float | None = hajek(r_minus[omitted], w[omitted]) if omitted.any() else None
    sel_bias: float | None = None
    sel_identity: float | None = None
    sel_conditional: float | None = None
    sel_discrepancy: float | None = None

    # `r_obs is not None` is exactly `omitted.any()` by the line above. Writing
    # the guard this way narrows the type without an assertion, and states the
    # dependency: the bias exists only where R^obs does.
    if r_obs is not None and transmitted.any() and 0.0 < t_bar < 1.0:
        sel_bias = r_obs - r0
        sel_identity = -weighted_covariance(t, r_minus, w) / (1.0 - t_bar)
        r_transmitted = hajek(r_minus[transmitted], w[transmitted])
        sel_conditional = t_bar * (r_obs - r_transmitted)
        sel_discrepancy = max(
            abs(sel_bias - sel_identity),
            abs(sel_bias - sel_conditional),
            abs(sel_identity - sel_conditional),
        )

    residual = a - (r0 + volume + align)

    return Decomposition(
        n_atoms=len(records),
        n_documents=len({r.document_id for r in records}),
        endpoint_fidelity=a,
        r_bar_zero=r0,
        t_bar=t_bar,
        delta_bar=d_bar,
        volume=volume,
        alignment=align,
        c_comm=c_comm,
        c_recon=c_recon,
        phi=(c_comm / a) if a > 0 else None,
        r_observational=r_obs,
        selection_bias=sel_bias,
        selection_bias_identity=sel_identity,
        selection_bias_conditional=sel_conditional,
        selection_bias_max_discrepancy=sel_discrepancy,
        prob_delta_negative=(
            float(hajek((delta < 0).astype(float), w)) if atom_level_statistics else None
        ),
        identity_residual=float(residual),
    )


def decompose_by_class(
    records: Sequence[AtomCausalRecord], **kwargs: Any
) -> dict[str, Decomposition]:
    """Per-role estimates. Reported alongside the weighted pooled estimate --
    never a single unweighted pooled number."""
    out: dict[str, Decomposition] = {}
    roles = sorted({r.role.value for r in records})
    for role in roles:
        subset = [r for r in records if r.role.value == role]
        if subset:
            out[role] = decompose(subset, **kwargs)
    return out
