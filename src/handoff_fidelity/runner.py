from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .integrity import verify_freeze


class ProtocolNotFrozenError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagePlan:
    stage: str
    documents: int
    focal_atoms_per_document: int
    execute: bool


def require_frozen(settings: Settings) -> None:
    ok, failures = verify_freeze(settings.private_home.expanduser())
    if not ok:
        raise ProtocolNotFrozenError(
            "Real experimental execution refused because the protocol is not frozen:\n- "
            + "\n- ".join(failures)
        )


def stage1_plan(*, execute: bool) -> StagePlan:
    return StagePlan(stage="stage1", documents=100, focal_atoms_per_document=3, execute=execute)


def run_stage1(settings: Settings, *, execute: bool) -> StagePlan:
    plan = stage1_plan(execute=execute)
    if execute:
        require_frozen(settings)
        # The production orchestrator is intentionally gated until the final
        # prompts/source pool/context-tuple spec are frozen. This call site is
        # where provider execution is connected after preregistration approval.
        raise NotImplementedError(
            "Freeze verified, but production provider orchestration remains intentionally disabled "
            "until the final preregistration bundle is approved and integrated."
        )
    return plan
