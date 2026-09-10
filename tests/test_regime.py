"""Decoder-regime state machine, replication rule, and the predictor-family guard.

These tests encode the two corrections that motivated them:

1. Documentation may not assign a decoder regime, in either direction.
2. ``causalrelay.primary_family`` is a regressor family, not a vendor.
"""

from __future__ import annotations

import pathlib

from handoff_fidelity.causalrelay.families import (
    PREDICTOR_FAMILY_RESOLUTION_STAGE,
    ModelPin,
    ModelRole,
    PredictorFamily,
    PredictorFamilyResolutionError,
    assert_not_a_provider_family,
    resolve_predictor_family_from_provider_evidence,
)
from handoff_fidelity.providers.capabilities import REGIME_D_STATUS, REGISTRY, VersionClass
from handoff_fidelity.providers.regime import (
    AUDIT_REQUIRED_INPUTS,
    AUDIT_REQUIRED_REPEATS,
    DecoderRegime,
    ReceiverConfiguration,
    RegimeAssignmentError,
    RegimeLedger,
    ReproducibilityAudit,
    RunIdentity,
    regime_from_documentation,
    select_replication,
)

from ._support import raises

CONFIG = ReceiverConfiguration(provider="mock", model_id="stub-1", configuration_hash="cfg-abc")


# ---------------------------------------------------------------- state machine


def test_the_regime_starts_not_audited_not_false():
    """The shipped state is ternary and begins at NOT_AUDITED.

    A boolean here would force a claim in one direction before the experiment
    that distinguishes the cases has been run.
    """
    assert REGIME_D_STATUS is DecoderRegime.NOT_AUDITED
    assert RegimeLedger().regime_for(CONFIG) is DecoderRegime.NOT_AUDITED


def test_documentation_may_not_assign_a_regime():
    with raises(RegimeAssignmentError):
        regime_from_documentation(provider="anthropic", pinned_snapshots=True)


def test_a_complete_unanimous_audit_confirms_D():
    audit = ReproducibilityAudit(
        configuration=CONFIG,
        n_inputs=AUDIT_REQUIRED_INPUTS,
        n_repeats=AUDIT_REQUIRED_REPEATS,
        inputs_with_disagreement=0,
        byte_identical_repeat_rate=0.42,  # bytes may differ; canonical output did not
        completed=True,
    )
    assert audit.regime() is DecoderRegime.D_CONFIRMED


def test_one_disagreeing_input_out_of_a_hundred_forces_S():
    """The (D) rule is strict. There is no majority vote and no rounding."""
    audit = ReproducibilityAudit(
        configuration=CONFIG,
        n_inputs=AUDIT_REQUIRED_INPUTS,
        n_repeats=AUDIT_REQUIRED_REPEATS,
        inputs_with_disagreement=1,
        completed=True,
    )
    assert audit.regime() is DecoderRegime.S_CONFIRMED


def test_an_undersized_audit_confirms_nothing():
    """Not even (S). Not observing a disagreement in 8 calls is weak evidence."""
    audit = ReproducibilityAudit(
        configuration=CONFIG,
        n_inputs=1,
        n_repeats=8,
        inputs_with_disagreement=0,
        completed=True,
    )
    assert audit.regime() is DecoderRegime.NOT_AUDITED


def test_byte_identity_is_a_diagnostic_not_the_criterion():
    """Canonical outcome is the theoretical object; raw bytes are reported beside it."""
    audit = ReproducibilityAudit(
        configuration=CONFIG,
        n_inputs=AUDIT_REQUIRED_INPUTS,
        n_repeats=AUDIT_REQUIRED_REPEATS,
        inputs_with_disagreement=0,
        byte_identical_repeat_rate=0.0,
        completed=True,
    )
    assert audit.regime() is DecoderRegime.D_CONFIRMED


def test_atom_level_probability_claims_need_D_or_a_repeated_design():
    ledger = RegimeLedger()
    ok, why = ledger.atom_level_probability_claims_permitted(CONFIG)
    assert ok is False and "not audited" in why

    ledger.record(
        ReproducibilityAudit(
            configuration=CONFIG,
            n_inputs=AUDIT_REQUIRED_INPUTS,
            n_repeats=AUDIT_REQUIRED_REPEATS,
            inputs_with_disagreement=3,
            completed=True,
        )
    )
    ok, why = ledger.atom_level_probability_claims_permitted(CONFIG)
    assert ok is False and "repeated-measure" in why


# ------------------------------------------------------------- run identity


def test_run_identity_flags_alias_drift():
    same = RunIdentity(requested_model_id="m-1", returned_model_id="m-1")
    drifted = RunIdentity(requested_model_id="alias", returned_model_id="m-1")
    assert same.alias_drift_risk is False
    assert drifted.alias_drift_risk is True
    assert set(drifted.to_dict()) >= {
        "requested_model_id",
        "returned_model_id",
        "provider_backend_version",
        "system_fingerprint",
        "request_id",
        "timestamp_utc",
        "sdk_version",
        "configuration_hash",
    }


# --------------------------------------------------- regime-(S) replication rule


def test_replication_rule_is_frozen_and_picks_the_smallest_sufficient_m():
    # decode variance already below 10% of document variance -> no replication
    assert select_replication(0.05, 1.0).m_star == 1
    # needs 2x averaging to clear the threshold
    assert select_replication(0.15, 1.0).m_star == 2
    # needs 3x
    assert select_replication(0.25, 1.0).m_star == 3
    # needs 5x
    assert select_replication(0.45, 1.0).m_star == 5


def test_exact_replication_grid_selector_with_gpt51_audit_values():
    """Regression test of the exact frozen grid selector:
    m* = min {m in [1, 2, 3, 5] : sigma_decode^2 / m <= 0.10 * sigma_document^2}

    Under GPT-5.1 receiver audit values:
      sigma_decode^2 = 0.014100
      sigma_document^2 = 0.138416
      threshold = 0.10 * 0.138416 = 0.0138416

    Mechanical candidate evaluation:
      m=1: 0.014100 / 1 = 0.014100 > 0.0138416 (ratio = 0.101867 > 0.10) -> FAILS
      m=2: 0.014100 / 2 = 0.007050 <= 0.0138416 (ratio = 0.050933 <= 0.10) -> SATISFIED -> m* = 2
      m=3: 0.014100 / 3 = 0.004700 <= 0.0138416
      m=5: 0.014100 / 5 = 0.002820 <= 0.0138416

    Explicitly verify distinction:
      raw variance ratio: sigma_decode^2 / sigma_document^2 = 0.101867 (10.19% > 10%)
      post-replication ratio: (sigma_decode^2 / m*) / sigma_document^2 = 0.050933 (5.09% <= 10%)
    """
    sigma2_decode = 0.014100
    sigma2_document = 0.138416

    # 1. Raw variance ratio is ~0.101867 > 0.10
    raw_ratio = sigma2_decode / sigma2_document
    assert abs(raw_ratio - 0.101866836) < 1e-6
    assert raw_ratio > 0.10

    # 2. Candidate-by-candidate evaluations
    grid = [1, 2, 3, 5]
    threshold = 0.10 * sigma2_document
    evaluations = {m: (sigma2_decode / m) <= threshold for m in grid}
    assert evaluations == {1: False, 2: True, 3: True, 5: True}

    # 3. Grid selector picks the smallest m that satisfies the inequality -> m* = 2
    decision = select_replication(sigma2_decode, sigma2_document)
    assert decision.m_star == 2
    assert decision.criterion_met is True
    assert decision.hierarchical_bootstrap_required is False

    # 4. Post-replication variance ratio is ~0.050933 <= 0.10
    post_ratio = (sigma2_decode / decision.m_star) / sigma2_document
    assert abs(post_ratio - 0.0509334) < 1e-6
    assert post_ratio <= 0.10


def test_when_no_m_suffices_the_bootstrap_keeps_the_decode_level():
    decision = select_replication(5.0, 1.0)
    assert decision.m_star == 5
    assert decision.criterion_met is False
    assert decision.hierarchical_bootstrap_required is True
    assert decision.ratio == 5.0


def test_replication_decision_is_serialisable_for_the_freeze_record():
    d = select_replication(0.15, 1.0).to_dict()
    assert set(d) == {
        "sigma2_decode",
        "sigma2_document",
        "ratio",
        "m_star",
        "criterion_met",
        "hierarchical_bootstrap_required",
    }


# ------------------------------------------- provider vs predictor family (F)


def test_provider_results_may_not_resolve_the_predictor_family():
    with raises(PredictorFamilyResolutionError):
        resolve_predictor_family_from_provider_evidence(canary={"latency": 1.2})


def test_a_provider_name_is_rejected_as_a_predictor_family():
    for vendor in ("openai", "Anthropic", "deepseek", "GEMINI"):
        with raises(PredictorFamilyResolutionError):
            assert_not_a_provider_family(vendor)
    # The real search space is accepted.
    for family in PredictorFamily:
        assert_not_a_provider_family(family.value)


def test_predictor_family_search_space_and_stage_are_unchanged():
    assert [f.value for f in PredictorFamily] == [
        "HistGradientBoostingRegressor",
        "Ridge",
        "ExtraTreesRegressor",
    ]
    assert PREDICTOR_FAMILY_RESOLUTION_STAGE == "DEVELOPMENT"


def test_model_pins_carry_provider_identity_separately_per_role():
    relay = ModelPin(role=ModelRole.RELAY, provider="vendor-a", model_id="m-1")
    receiver = ModelPin(role=ModelRole.RECEIVER, provider="vendor-b", model_id="m-2")
    assert relay.provider != receiver.provider
    assert relay.to_dict()["role"] == "relay"
    assert receiver.to_dict()["role"] == "receiver"


# ------------------------------------------------------- version semantics (D/E)


def test_canonical_id_documented_as_snapshot_is_admissible_as_primary():
    assert VersionClass.CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT.admissible_as_primary_confirmatory
    assert VersionClass.IMMUTABLE_DATELESS_SNAPSHOT.admissible_as_primary_confirmatory


def test_moving_aliases_and_previews_are_not_admissible_as_primary():
    assert not VersionClass.MOVING_ALIAS_WITH_RECORDED_BACKEND_VERSION.admissible_as_primary_confirmatory
    assert not VersionClass.PREVIEW_SHORT_NOTICE.admissible_as_primary_confirmatory
    assert not VersionClass.STABLE_LABEL_NO_WEIGHT_GUARANTEE.admissible_as_primary_confirmatory


def test_every_provider_capability_record_serialises():
    for name, caps in REGISTRY.items():
        d = caps.to_dict()
        assert d["provider"] == name
        assert isinstance(d["version_class"], str)
        assert all(isinstance(v, str | int | bool | type(None)) for v in d.values())


def test_the_two_openai_style_corrections_are_in_place():
    """Version pinning and deterministic decoding are recorded separately."""
    openai = REGISTRY["openai"]
    assert openai.version_class is VersionClass.CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT
    assert openai.pinned_model_snapshots.value == "YES"
    # ...and pinning still says nothing about decoding.
    assert openai.temperature_support.value == "UNKNOWN"
    assert openai.seed_support.value == "UNKNOWN"


def test_no_provider_is_marked_resolved_while_fields_remain_unknown():
    for name, caps in REGISTRY.items():
        if name == "mock":
            continue
        assert caps.resolved is False
        assert caps.unresolved_fields


# ------------------------------------------- pre-registration amendment log


def test_preregistration_amendments_are_all_pre_outcome():
    import yaml

    doc = yaml.safe_load(pathlib.Path("configs/preregistration_v1_2.yaml").read_text())
    amendments = doc["amendments"]
    assert [a["id"] for a in amendments] == ["P-5", "P-6", "P-7", "P-8", "P-9"]
    for a in amendments:
        # The count is what distinguishes an amendment from a rationalisation.
        assert a["benchmark_outcomes_observed_before_amendment"] == 0
        assert a["reason"].strip()
        assert a["date"] in ("2026-09-06", "2026-09-09")

    p6 = amendments[1]
    assert p6["original_primary_set"] == ["provence", "adaptive_queryselect", "cpc", "llmlingua2"]
    assert p6["amended_primary_set"] == ["provence", "cpc", "llmlingua2", "dac"]
    # Theory is preserved, not rewritten.
    assert "remains a live theoretical case" in amendments[0]["theory_unchanged"]


def test_the_accounting_script_rejects_a_post_outcome_amendment():
    from scripts.prereg_accounting import check_amendments

    clean = {
        "amendments": [
            {
                "id": "X",
                "date": "2026-09-06",
                "kind": "k",
                "reason": "r",
                "benchmark_outcomes_observed_before_amendment": 0,
            }
        ]
    }
    assert check_amendments(clean) == []

    post_hoc = {
        "amendments": [
            {
                "id": "Y",
                "date": "2026-09-06",
                "kind": "k",
                "reason": "r",
                "benchmark_outcomes_observed_before_amendment": 7,
            }
        ]
    }
    problems = check_amendments(post_hoc)
    assert problems and "POST-OUTCOME" in problems[0]

    missing = {"amendments": [{"id": "Z"}]}
    assert len(check_amendments(missing)) == 4


def test_the_predictor_family_leaf_is_labelled_as_not_provider_resolvable():
    import yaml

    doc = yaml.safe_load(pathlib.Path("configs/preregistration_v1_2.yaml").read_text())
    leaf = doc["causalrelay"]["primary_family"]
    assert leaf["status"] == "proposed"
    assert leaf["resolution_stage"] == "DEVELOPMENT"
    assert leaf["parameter_kind"] == "utility_predictor_estimator_family"
    assert leaf["resolvable_from_provider_evidence"] is False
    assert leaf["search_space"] == [f.value for f in PredictorFamily]


def test_the_budget_rule_names_its_tokenizer():
    import yaml

    doc = yaml.safe_load(pathlib.Path("configs/preregistration_v1_2.yaml").read_text())
    budget = doc["budget"]
    assert budget["f_i_tokenizer"]["value"] == "primary_relay_model_tokenizer"
    assert budget["recompute_B_star_on_relay_model_change"]["value"] is True
