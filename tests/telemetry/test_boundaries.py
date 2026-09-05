"""Research/demo boundary tests.

These encode scientific boundaries, not preferences: a guardrail on the
inference path or an external tracer in research mode would change or export the
very messages being measured.
"""

from __future__ import annotations

import os

from handoff_fidelity.app_contracts.modes import AppMode, ModePolicy, ModeViolation
from handoff_fidelity.telemetry import guardrails, langsmith
from handoff_fidelity.telemetry.spans import InMemoryTracer, build_tracer

RAISED = "expected ModeViolation"


def test_langsmith_is_off_by_default_in_both_modes():
    for flag in langsmith.LANGSMITH_ENV_FLAGS:
        os.environ.pop(flag, None)
    for mode in (AppMode.RESEARCH, AppMode.DEMO):
        status = langsmith.resolve(mode)
        assert status.enabled is False
        assert status.requested is False


def test_langsmith_refused_in_research_mode_even_when_requested():
    """No real research trace may leave the machine merely because the
    orchestration library supports it."""
    os.environ["LANGSMITH_TRACING"] = "true"
    try:
        status = langsmith.resolve(AppMode.RESEARCH)
        assert status.requested is True
        assert status.enabled is False
        assert "RESEARCH_MODE" in status.reason
        try:
            langsmith.enforce_disabled_in_research(AppMode.RESEARCH)
            raise AssertionError(RAISED)
        except ModeViolation:
            pass
    finally:
        os.environ.pop("LANGSMITH_TRACING", None)


def test_langsmith_may_be_enabled_in_demo_mode():
    os.environ["LANGSMITH_TRACING"] = "true"
    try:
        assert langsmith.resolve(AppMode.DEMO).enabled is True
    finally:
        os.environ.pop("LANGSMITH_TRACING", None)


def test_guardrails_off_by_default():
    os.environ.pop(guardrails.GUARDRAILS_ENV_FLAG, None)
    for mode in (AppMode.RESEARCH, AppMode.DEMO):
        assert guardrails.resolve(mode).enabled is False


def test_guardrails_refused_in_research_mode():
    os.environ[guardrails.GUARDRAILS_ENV_FLAG] = "true"
    try:
        status = guardrails.resolve(AppMode.RESEARCH)
        assert status.enabled is False
        assert "RESEARCH_MODE" in status.reason
    finally:
        os.environ.pop(guardrails.GUARDRAILS_ENV_FLAG, None)


def test_guardrails_never_allowed_on_the_scientific_inference_path():
    """The hard boundary. Denied even in demo mode."""
    for position in sorted(guardrails.SCIENTIFIC_INFERENCE_PATH):
        for mode in (AppMode.RESEARCH, AppMode.DEMO):
            try:
                guardrails.assert_position_allowed(position, mode, enabled=True)
                raise AssertionError(f"{position} in {mode} was allowed")
            except ModeViolation:
                pass


def test_guardrails_allowed_at_a_demo_perimeter_position():
    guardrails.assert_position_allowed("demo_input", AppMode.DEMO, enabled=True)


def test_disabled_guardrails_are_a_no_op_anywhere():
    guardrails.assert_position_allowed("relay_to_receiver", AppMode.RESEARCH, enabled=False)


def test_mode_policy_forbids_browser_final_test_in_both_modes():
    for mode in (AppMode.RESEARCH, AppMode.DEMO):
        policy = ModePolicy(mode)
        assert policy.browser_may_launch_final_test is False
        assert policy.browser_may_mutate_frozen_parameters is False
        assert policy.graph_topology_mutable is False
        try:
            policy.require("launch_final_test")
            raise AssertionError(RAISED)
        except ModeViolation:
            pass


def test_default_tracer_is_in_memory_and_offline():
    assert isinstance(build_tracer(), InMemoryTracer)
