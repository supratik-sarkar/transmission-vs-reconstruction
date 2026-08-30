from __future__ import annotations

from .models import GateResult


def evaluate_stage1_gate(
    *,
    reconstruction_contribution: float,
    prior_effects: dict[str, float],
    eligible_prior_classes: tuple[str, ...] = ("scope", "numeric"),
    reconstruction_gate: float = 0.10,
    prior_gate: float = 0.10,
) -> GateResult:
    prior_pass = any(
        prior_effects.get(c, float("-inf")) >= prior_gate for c in eligible_prior_classes
    )
    recon_pass = reconstruction_contribution >= reconstruction_gate
    proceed = prior_pass or recon_pass
    reason = (
        "Proceed: at least one preregistered effect-size gate cleared."
        if proceed
        else "Halt: both preregistered effect-size gates failed."
    )
    return GateResult(
        reconstruction_contribution=reconstruction_contribution,
        prior_effects=prior_effects,
        reconstruction_gate=reconstruction_gate,
        prior_gate=prior_gate,
        eligible_prior_classes=list(eligible_prior_classes),
        proceed=proceed,
        reason=reason,
    )
