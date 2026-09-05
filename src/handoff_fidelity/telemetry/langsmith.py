"""LangSmith integration — optional, and OFF by default.

Enabling it would send trace content to a third-party service. In research mode
that could mean real source text and real model output leaving the machine
merely because the orchestration library supports it, so the default is off and
research mode refuses to turn it on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..app_contracts.modes import AppMode, ModeViolation

LANGSMITH_ENV_FLAGS: tuple[str, ...] = (
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
)


@dataclass(frozen=True, slots=True)
class LangSmithStatus:
    requested: bool
    enabled: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"requested": self.requested, "enabled": self.enabled, "reason": self.reason}


def _requested_from_env() -> bool:
    return any(
        os.environ.get(flag, "").strip().lower() in {"1", "true", "yes", "on"}
        for flag in LANGSMITH_ENV_FLAGS
    )


def resolve(mode: AppMode, *, explicit: bool | None = None) -> LangSmithStatus:
    requested = _requested_from_env() if explicit is None else bool(explicit)
    if not requested:
        return LangSmithStatus(False, False, "disabled by default")
    if mode is AppMode.RESEARCH:
        return LangSmithStatus(
            True,
            False,
            "refused: external tracing is not permitted in RESEARCH_MODE, because "
            "real source text and model output would leave the machine",
        )
    return LangSmithStatus(True, True, "enabled in DEMO_MODE by explicit request")


def enforce_disabled_in_research(mode: AppMode) -> None:
    if mode is AppMode.RESEARCH and _requested_from_env():
        raise ModeViolation(
            "LangSmith tracing is requested via the environment but RESEARCH_MODE "
            "is active. Unset the flag or switch to DEMO_MODE."
        )
