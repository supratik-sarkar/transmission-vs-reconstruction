"""NeMo Guardrails boundary.

Guardrails may modify or block model traffic. Placing them between the relay and
the receiver would mean the measured message is not the message the relay
produced -- silently invalidating T, R^-, D^+ and every quantity built on them.

They are therefore a DEMO PERIMETER only, and research mode fails closed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..app_contracts.modes import AppMode, ModeViolation

GUARDRAILS_ENV_FLAG = "NEMO_GUARDRAILS_ENABLED"

#: Positions guardrails may never occupy.
SCIENTIFIC_INFERENCE_PATH: frozenset[str] = frozenset(
    {
        "relay_to_receiver",
        "intervention_to_receiver",
        "counterfactual_receiver",
        "natural_receiver",
        "prior_probe",
    }
)

#: Positions that are legitimate in a public demo.
DEMO_PERIMETER: frozenset[str] = frozenset(
    {
        "demo_input",
        "demo_output",
        "demo_pii",
        "demo_jailbreak",
        "demo_topic",
    }
)


@dataclass(frozen=True, slots=True)
class GuardrailsStatus:
    requested: bool
    enabled: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"requested": self.requested, "enabled": self.enabled, "reason": self.reason}


def _requested_from_env() -> bool:
    return os.environ.get(GUARDRAILS_ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve(mode: AppMode, *, explicit: bool | None = None) -> GuardrailsStatus:
    requested = _requested_from_env() if explicit is None else bool(explicit)
    if not requested:
        return GuardrailsStatus(False, False, "disabled by default")
    if mode is AppMode.RESEARCH:
        return GuardrailsStatus(
            True,
            False,
            "refused: guardrails may not run in RESEARCH_MODE, where they could "
            "alter scientific relay or receiver content",
        )
    return GuardrailsStatus(True, True, "enabled as a DEMO_MODE perimeter")


def assert_position_allowed(position: str, mode: AppMode, *, enabled: bool) -> None:
    """The hard boundary. Called wherever a guardrail could be attached."""
    if not enabled:
        return
    if position in SCIENTIFIC_INFERENCE_PATH:
        raise ModeViolation(
            f"NeMo Guardrails cannot be attached at {position!r}: it is on the "
            "scientific inference path, where a guardrail could modify or block the "
            "very message being measured."
        )
    if mode is AppMode.RESEARCH:
        raise ModeViolation(
            f"NeMo Guardrails cannot be enabled in RESEARCH_MODE (position {position!r})."
        )
    if position not in DEMO_PERIMETER:
        raise ModeViolation(
            f"unknown guardrail position {position!r}; allowed demo positions: "
            f"{sorted(DEMO_PERIMETER)}"
        )
