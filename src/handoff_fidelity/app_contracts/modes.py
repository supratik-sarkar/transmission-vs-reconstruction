"""Application modes.

RESEARCH_MODE and DEMO_MODE are a TYPE, not a string comparison scattered through
the codebase, because the difference between them is a scientific boundary: in
research mode nothing may sit between the relay and the receiver, and no
component may rewrite scientific content.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AppMode(StrEnum):
    RESEARCH = "RESEARCH_MODE"
    DEMO = "DEMO_MODE"


class RunKind(StrEnum):
    MOCK = "MOCK"
    DEMO = "DEMO"
    CALIBRATION = "CALIBRATION"
    DEVELOPMENT = "DEVELOPMENT"
    FINAL_TEST = "FINAL_TEST"


class ModeViolation(RuntimeError):
    """A capability was requested that the active mode forbids. Always fatal:
    a silently downgraded scientific guarantee is worse than a crash."""


@dataclass(frozen=True, slots=True)
class ModePolicy:
    """What each mode permits. Read by the API, the orchestrator and the guards."""

    mode: AppMode

    @property
    def guardrails_allowed_in_inference_path(self) -> bool:
        # NEVER in research mode. Guardrails can modify or block model traffic,
        # which would silently alter the relay or receiver content the whole
        # measurement is about.
        return self.mode is AppMode.DEMO

    @property
    def external_tracing_allowed_by_default(self) -> bool:
        return False  # both modes; opt-in only, and never implicit

    @property
    def browser_may_mutate_frozen_parameters(self) -> bool:
        return False  # both modes

    @property
    def browser_may_launch_final_test(self) -> bool:
        return False  # both modes; final test is CLI + freeze-policy only

    @property
    def browser_may_launch_synthetic_run(self) -> bool:
        return self.mode is AppMode.DEMO

    @property
    def graph_topology_mutable(self) -> bool:
        return False  # the scientific graph is fixed in both modes

    def require(self, capability: str) -> None:
        allowed = {
            "guardrails_in_inference_path": self.guardrails_allowed_in_inference_path,
            "external_tracing": self.external_tracing_allowed_by_default,
            "mutate_frozen_parameters": self.browser_may_mutate_frozen_parameters,
            "launch_final_test": self.browser_may_launch_final_test,
            "launch_synthetic_run": self.browser_may_launch_synthetic_run,
            "mutate_graph_topology": self.graph_topology_mutable,
        }
        if capability not in allowed:
            raise ModeViolation(f"unknown capability {capability!r}")
        if not allowed[capability]:
            raise ModeViolation(
                f"{capability!r} is not permitted in {self.mode.value}. This is a "
                "scientific boundary, not a configuration default."
            )
