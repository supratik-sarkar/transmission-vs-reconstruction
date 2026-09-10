"""The Stage-1 discovery gate.

This is an EFFECT-SIZE threshold governing whether the programme continues, not
a null-hypothesis test. Two reasons, both pre-registered:

  * the pilot is sized for effect estimation, not power: at roughly 200 paired
    focal atoms a five-point binary contrast has a Wilson interval wide enough
    to be interpretively ambiguous, whereas a ten-point effect is separable;
  * a significance criterion would invite optional stopping across atom classes,
    which a fixed effect size on a predeclared class does not.

Intervals are reported throughout and no p-value gates any decision.

A low R^- in the randomised arm ALONE is evidence that the manipulation worked
and is explicitly not grounds to halt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..models import GateResult

RECONSTRUCTION_GATE = 0.10
PRIOR_GATE = 0.10
DEFAULT_ELIGIBLE_CLASSES: tuple[str, ...] = ("scope", "period", "numeric")


def evaluate_stage1_gate(
    *,
    reconstruction_contribution: float,
    prior_effects: Mapping[str, float | None],
    eligible_prior_classes: Sequence[str] = DEFAULT_ELIGIBLE_CLASSES,
    reconstruction_gate: float = RECONSTRUCTION_GATE,
    prior_gate: float = PRIOR_GATE,
) -> GateResult:
    eligible = tuple(eligible_prior_classes)
    cleared = [
        c
        for c in eligible
        if prior_effects.get(c) is not None and float(prior_effects[c]) >= prior_gate  # type: ignore[arg-type]
    ]
    prior_pass = bool(cleared)
    recon_pass = reconstruction_contribution >= reconstruction_gate
    proceed = prior_pass or recon_pass

    if proceed:
        parts = []
        if prior_pass:
            parts.append(f"matched prior-access effect >= {prior_gate:.2f} on {', '.join(cleared)}")
        if recon_pass:
            parts.append(
                f"reconstruction contribution {reconstruction_contribution:.3f} >= {reconstruction_gate:.2f}"
            )
        reason = "Proceed: " + "; ".join(parts) + "."
    else:
        reason = (
            f"Halt: neither gate cleared. Reconstruction contribution "
            f"{reconstruction_contribution:.3f} < {reconstruction_gate:.2f}, and no "
            f"eligible class reached the {prior_gate:.2f} matched prior-access threshold."
        )

    return GateResult(
        reconstruction_contribution=reconstruction_contribution,
        prior_effects=dict(prior_effects),
        reconstruction_gate=reconstruction_gate,
        prior_gate=prior_gate,
        eligible_prior_classes=eligible,
        proceed=proceed,
        reason=reason,
    )


class PostGateError(RuntimeError):
    """Experiment C, CausalRelay fitting and the depth sweep are post-gate. This
    is raised if they are invoked before the gate has been evaluated and
    passed."""


def require_gate_passed(gate: GateResult | None) -> None:
    if gate is None:
        raise PostGateError("post-gate work attempted before the Stage-1 gate was evaluated")
    if not gate.proceed:
        raise PostGateError(f"post-gate work attempted after a failed gate: {gate.reason}")
