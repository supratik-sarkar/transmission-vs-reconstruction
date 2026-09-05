"""Runtime guards that gate real execution.

Nothing in this repository performs a real model call. These guards are what a
future execution path must pass through, and they fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, require_frozen_models
from ..models import GateResult
from .spec import STAGES, Stage, StageGuardError


class DryRunOnly(RuntimeError):
    """Raised when execution is attempted without an explicit opt-in."""


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    stage: Stage
    execute: bool = False
    protocol_freeze: Path | None = None
    test_freeze: Path | None = None
    gate: GateResult | None = None


def authorise(request: ExecutionRequest, settings: Settings) -> list[str]:
    """Return the list of satisfied checks, or raise on the first failure.

    Ordering matters: model pinning is checked before anything touches a
    provider, so an unpinned run cannot spend a single token.
    """
    spec = STAGES[request.stage]
    checks: list[str] = []

    if not request.execute:
        raise DryRunOnly(
            f"{request.stage} was planned but not executed. Pass execute=True only "
            "after every freeze and gate condition below is satisfied."
        )

    require_frozen_models(settings)
    checks.append("models pinned")

    if spec.requires_protocol_freeze:
        if request.protocol_freeze is None or not Path(request.protocol_freeze).exists():
            raise StageGuardError(
                f"{request.stage} requires a valid protocol freeze record; none was supplied"
            )
        checks.append("protocol freeze present")

    if spec.requires_test_freeze:
        if request.test_freeze is None or not Path(request.test_freeze).exists():
            raise StageGuardError(
                f"{request.stage} requires the FINAL TEST freeze record; none was supplied. "
                "No final-test runner may execute without it."
            )
        checks.append("test freeze present")

    if spec.requires_gate_passed:
        if request.gate is None:
            raise StageGuardError(f"{request.stage} is post-gate but no gate result was supplied")
        if not request.gate.proceed:
            raise StageGuardError(
                f"{request.stage} is post-gate and the Stage-1 gate did not pass: "
                f"{request.gate.reason}"
            )
        checks.append("stage-1 gate passed")

    if spec.proposed:
        checks.append(
            "WARNING: this stage's size is PROPOSED, not frozen; approve it before running"
        )
    return checks
