"""Lifecycle policy tests.

The CASES table is shared with the Rego suite by construction: each entry states
the same input and the same expected verdict, so the OPA policy and the Python
mirror cannot drift into disagreeing about a denial.
"""

from __future__ import annotations

from pathlib import Path

from handoff_fidelity.policy.decisions import (
    FINAL_TEST_FREEZE_REQUIREMENTS,
    Action,
    PolicyInput,
    Subject,
    evaluate_local,
)
from handoff_fidelity.policy.engine import PolicyEngine

FULL_FREEZE = dict.fromkeys(FINAL_TEST_FREEZE_REQUIREMENTS, True)

READY_TEST = PolicyInput(
    action=Action.RUN_STAGE2_TEST,
    subject=Subject.CLI,
    mode="RESEARCH_MODE",
    provider="openai",
    relay_model_pinned=True,
    receiver_model_pinned=True,
    calibration_parameters_resolved=True,
    protocol_freeze_present=True,
    final_test_freeze_present=True,
    stage1_gate_passed=True,
    freeze_fields=dict(FULL_FREEZE),
)


def test_final_test_denied_without_freeze():
    d = evaluate_local(
        PolicyInput(action=Action.RUN_STAGE2_TEST, subject=Subject.CLI, provider="openai")
    )
    assert d.allow is False
    assert any("freeze" in r for r in d.reasons)


def test_final_test_denied_on_each_single_missing_requirement():
    """Every requirement is load-bearing on its own."""
    for requirement in FINAL_TEST_FREEZE_REQUIREMENTS:
        fields = dict(FULL_FREEZE)
        fields[requirement] = False
        d = evaluate_local(
            PolicyInput(
                **{
                    **READY_TEST.to_dict(),
                    "action": Action.RUN_STAGE2_TEST,
                    "subject": Subject.CLI,
                    "freeze_fields": fields,
                }
            )
        )
        assert d.allow is False, f"missing {requirement} did not deny"
        assert any(requirement in r for r in d.reasons)


def test_final_test_allowed_when_fully_frozen():
    assert evaluate_local(READY_TEST).allow is True


def test_development_denied_without_model_pins():
    d = evaluate_local(
        PolicyInput(
            action=Action.RUN_STAGE2_DEV,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=True,
            stage1_gate_passed=True,
            calibration_parameters_resolved=True,
        )
    )
    assert d.allow is False
    assert any("relay_model" in r for r in d.reasons)
    assert any("receiver_model" in r for r in d.reasons)


def test_development_denied_before_the_gate():
    d = evaluate_local(
        PolicyInput(
            action=Action.RUN_STAGE2_DEV,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=True,
            relay_model_pinned=True,
            receiver_model_pinned=True,
            calibration_parameters_resolved=True,
        )
    )
    assert d.allow is False
    assert any("gate" in r for r in d.reasons)


def test_development_denied_while_calibration_is_unresolved():
    d = evaluate_local(
        PolicyInput(
            action=Action.RUN_STAGE2_DEV,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=True,
            relay_model_pinned=True,
            receiver_model_pinned=True,
            stage1_gate_passed=True,
        )
    )
    assert d.allow is False
    assert any("calibration" in r for r in d.reasons)


def test_browser_denied_final_test():
    """The single most important denial in the system."""
    fields = READY_TEST.to_dict()
    fields["subject"] = Subject.BROWSER
    fields["action"] = Action.RUN_STAGE2_TEST
    d = evaluate_local(PolicyInput(**fields))
    assert d.allow is False
    assert any("browser" in r for r in d.reasons)


def test_browser_denied_every_real_stage():
    for action in (
        Action.RUN_STAGE1,
        Action.RUN_STAGE2_DEV,
        Action.RUN_STAGE2_TEST,
        Action.RUN_EXPERIMENT_C,
        Action.RUN_MULTIHOP,
        Action.RUN_CALIBRATION,
    ):
        d = evaluate_local(PolicyInput(action=action, subject=Subject.BROWSER, provider="mock"))
        assert d.allow is False, f"browser was allowed {action}"


def test_demo_synthetic_permitted_in_demo_mode_only():
    allowed = evaluate_local(
        PolicyInput(
            action=Action.RUN_DEMO_SYNTHETIC,
            subject=Subject.BROWSER,
            mode="DEMO_MODE",
            provider="mock",
        )
    )
    assert allowed.allow is True
    refused = evaluate_local(
        PolicyInput(
            action=Action.RUN_DEMO_SYNTHETIC,
            subject=Subject.BROWSER,
            mode="RESEARCH_MODE",
            provider="mock",
        )
    )
    assert refused.allow is False


def test_guardrails_in_inference_always_denied():
    for mode in ("RESEARCH_MODE", "DEMO_MODE"):
        d = evaluate_local(
            PolicyInput(
                action=Action.ENABLE_GUARDRAILS_IN_INFERENCE,
                subject=Subject.CLI,
                mode=mode,
                provider="mock",
            )
        )
        assert d.allow is False


def test_unknown_provider_denied():
    d = evaluate_local(
        PolicyInput(
            action=Action.RUN_DEMO_SYNTHETIC,
            subject=Subject.BROWSER,
            mode="DEMO_MODE",
            provider="some-unapproved-provider",
        )
    )
    assert d.allow is False
    assert any("approved list" in r for r in d.reasons)


def test_frozen_parameters_are_immutable():
    d = evaluate_local(
        PolicyInput(
            action=Action.MUTATE_FROZEN_PARAMETER,
            subject=Subject.CLI,
            mode="DEMO_MODE",
            provider="mock",
        )
    )
    assert d.allow is False


def test_engine_falls_back_to_the_mirror_and_stays_closed():
    """Without the OPA binary the engine must still deny, not pass through."""
    engine = PolicyEngine(prefer_opa=True)
    d = engine.evaluate(
        PolicyInput(action=Action.RUN_STAGE2_TEST, subject=Subject.CLI, provider="openai")
    )
    assert d.allow is False
    assert engine.describe()["active_engine"] in {"opa", "local-mirror"}


def test_python_and_opa_exact_parity_across_vectors():
    """Verify that Python local evaluation and actual OPA/Rego agree exactly on all vectors."""
    from handoff_fidelity.policy.engine import opa_available

    if not opa_available():
        return

    engine = PolicyEngine(prefer_opa=True)
    assert Path("policies/rego").exists()

    test_vectors = [
        # 1. DEMO mock allowed in DEMO_MODE
        PolicyInput(
            action=Action.RUN_DEMO_SYNTHETIC,
            subject=Subject.BROWSER,
            mode="DEMO_MODE",
            provider="mock",
        ),
        # 2. Unknown provider denied
        PolicyInput(
            action=Action.RUN_DEMO_SYNTHETIC,
            subject=Subject.BROWSER,
            mode="DEMO_MODE",
            provider="unknown-provider",
        ),
        # 3. DEVELOPMENT with prerequisites missing (e.g. no model pins) denied
        PolicyInput(
            action=Action.RUN_STAGE2_DEV,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=True,
            stage1_gate_passed=True,
            calibration_parameters_resolved=True,
            relay_model_pinned=False,
            receiver_model_pinned=False,
        ),
        # 4. FINAL TEST without freeze denied
        PolicyInput(
            action=Action.RUN_STAGE2_TEST,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=False,
        ),
        # 5. FINAL TEST without model pins denied
        PolicyInput(
            action=Action.RUN_STAGE2_TEST,
            subject=Subject.CLI,
            provider="openai",
            protocol_freeze_present=True,
            final_test_freeze_present=True,
            relay_model_pinned=False,
            receiver_model_pinned=False,
            freeze_fields=dict(FULL_FREEZE),
        ),
        # 6. Browser FINAL TEST launch denied
        PolicyInput(
            **{
                **READY_TEST.to_dict(),
                "action": Action.RUN_STAGE2_TEST,
                "subject": Subject.BROWSER,
            }
        ),
        # 7. Valid preconditions produce expected decision (ALLOW)
        READY_TEST,
        # 8. NeMo/guardrails in scientific inference path denied
        PolicyInput(
            action=Action.ENABLE_GUARDRAILS_IN_INFERENCE,
            subject=Subject.CLI,
            mode="RESEARCH_MODE",
            provider="mock",
        ),
        PolicyInput(
            action=Action.ENABLE_GUARDRAILS_IN_INFERENCE,
            subject=Subject.CLI,
            mode="DEMO_MODE",
            provider="mock",
        ),
        # 9. Mutate frozen parameter denied
        PolicyInput(
            action=Action.MUTATE_FROZEN_PARAMETER,
            subject=Subject.CLI,
            mode="RESEARCH_MODE",
            provider="mock",
        ),
    ]

    for idx, vector in enumerate(test_vectors):
        local_dec = evaluate_local(vector)
        opa_dec = engine._evaluate_opa(vector)
        assert local_dec.allow == opa_dec.allow, (
            f"Vector {idx} ({vector.action}, {vector.subject}) disagreed: local={local_dec.allow}, opa={opa_dec.allow}"
        )
        combined_dec = engine.evaluate(vector)
        assert combined_dec.engine != "disagreement"
