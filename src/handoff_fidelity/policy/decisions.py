"""Lifecycle policy.

OPA answers LIFECYCLE questions -- may this stage start, is the provider
approved, is the freeze valid. It never answers SCIENTIFIC ones: it cannot
decide which result is favourable, whether to discard an observation, or whether
a method wins.

The local mirror below implements the same rules in Python and is authoritative
when OPA is unavailable. That is deliberate: the CLI's fail-closed guards must
not become dependent on an external binary being installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Action(StrEnum):
    RUN_CALIBRATION = "run_calibration"
    RUN_STAGE1 = "run_stage1"
    RUN_STAGE2_DEV = "run_stage2_dev"
    RUN_STAGE2_TEST = "run_stage2_test"
    RUN_EXPERIMENT_C = "run_experiment_c"
    RUN_MULTIHOP = "run_multihop"
    RUN_DEMO_SYNTHETIC = "run_demo_synthetic"
    MUTATE_FROZEN_PARAMETER = "mutate_frozen_parameter"
    ENABLE_GUARDRAILS_IN_INFERENCE = "enable_guardrails_in_inference"


class Subject(StrEnum):
    CLI = "cli"
    BROWSER = "browser"
    SCHEDULER = "scheduler"


#: Everything the final-test freeze must bind before the sealed test may run.
FINAL_TEST_FREEZE_REQUIREMENTS: tuple[str, ...] = (
    "relay_model_pinned",
    "receiver_model_pinned",
    "causalrelay_artifact_frozen",
    "calibration_parameters_resolved",
    "focal_sampling_frozen",
    "renderer_frozen",
    "matcher_frozen",
    "sota_revisions_frozen",
    "analysis_revision_frozen",
    "bootstrap_frozen",
    "source_manifest_frozen",
    "test_manifest_frozen",
    "final_test_freeze_present",
)

APPROVED_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "deepseek", "anthropic", "gemini", "mock"}
)


@dataclass(frozen=True, slots=True)
class PolicyInput:
    action: Action
    subject: Subject
    mode: str = "RESEARCH_MODE"
    provider: str = "mock"
    relay_model_pinned: bool = False
    receiver_model_pinned: bool = False
    calibration_parameters_resolved: bool = False
    protocol_freeze_present: bool = False
    final_test_freeze_present: bool = False
    stage1_gate_passed: bool = False
    freeze_fields: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__slots__}
        d["action"] = self.action.value
        d["subject"] = self.subject.value
        return d


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allow: bool
    reasons: tuple[str, ...]
    engine: str

    def to_dict(self) -> dict[str, Any]:
        return {"allow": self.allow, "reasons": list(self.reasons), "engine": self.engine}


def evaluate_local(inp: PolicyInput) -> PolicyDecision:
    """Fail-closed Python mirror of policies/rego/lifecycle.rego.

    Kept in lockstep with the Rego by a shared test-case table, so the two cannot
    drift into disagreeing about a denial.
    """
    deny: list[str] = []

    if inp.provider not in APPROVED_PROVIDERS:
        deny.append(f"provider {inp.provider!r} is not on the approved list")

    # The browser is read-only for anything scientific.
    if inp.subject is Subject.BROWSER and inp.action not in {
        Action.RUN_DEMO_SYNTHETIC,
    }:
        deny.append(
            f"subject 'browser' may not perform {inp.action.value!r}; the browser is "
            "read-only for research actions"
        )

    if inp.action is Action.MUTATE_FROZEN_PARAMETER:
        deny.append("frozen parameters are immutable through any interface")

    if inp.action is Action.ENABLE_GUARDRAILS_IN_INFERENCE:
        deny.append("guardrails may never be attached to the scientific inference path")

    if inp.action is Action.RUN_DEMO_SYNTHETIC and inp.mode != "DEMO_MODE":
        deny.append("synthetic demo runs require DEMO_MODE")

    real_stages = {
        Action.RUN_STAGE1,
        Action.RUN_STAGE2_DEV,
        Action.RUN_STAGE2_TEST,
        Action.RUN_EXPERIMENT_C,
        Action.RUN_MULTIHOP,
    }
    if inp.action in real_stages:
        if not inp.protocol_freeze_present:
            deny.append("protocol freeze record is absent")
        if not inp.relay_model_pinned:
            deny.append("relay_model is not pinned")
        if not inp.receiver_model_pinned:
            deny.append("receiver_model is not pinned")

    post_gate = {
        Action.RUN_STAGE2_DEV,
        Action.RUN_STAGE2_TEST,
        Action.RUN_EXPERIMENT_C,
        Action.RUN_MULTIHOP,
    }
    if inp.action in post_gate and not inp.stage1_gate_passed:
        deny.append("the Stage-1 discovery gate has not passed")

    if (
        inp.action in {Action.RUN_STAGE2_DEV, Action.RUN_STAGE2_TEST}
        and not inp.calibration_parameters_resolved
    ):
        deny.append("calibration-selected parameters are unresolved")

    if inp.action is Action.RUN_STAGE2_TEST:
        for requirement in FINAL_TEST_FREEZE_REQUIREMENTS:
            if not inp.freeze_fields.get(requirement, False):
                deny.append(f"final-test freeze requirement unmet: {requirement}")

    return PolicyDecision(
        allow=not deny,
        reasons=tuple(deny) if deny else ("allowed",),
        engine="local-mirror",
    )
