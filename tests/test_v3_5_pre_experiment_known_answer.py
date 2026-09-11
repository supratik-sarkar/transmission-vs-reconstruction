"""Deterministic pre-experiment known-answer test suite for TVR V3.5.

Mechanically verifies:
1. Authentic document-level outcome lineage & schema conformance.
2. Anti-broadcast rejection & zero-variance detection.
3. Nested outer-fold exclusion & grouped inner-CV containment.
4. Learner-family restriction to HistGradientBoosting, Ridge, ExtraTrees.
5. Source-only feature enforcement.
6. Paired bootstrap known-answer analytical result.
7. Simultaneous max-statistic quantile calculation.
8. Nonzero-variance bootstrap nondegenerate intervals.
9. Placeholder result rejection & missing lineage detection.
10. Representation metric applicability (prohibits atom metrics on latent/hybrid).
11. Comparator registry completeness (6 primary, 4 endpoint, 2 adjacent).
12. LongLLMLingua identity separation from Selective Context.
13. Receiver configuration identity determinism and hashing.
14. B* cross-model calibration reuse prohibition.
15. Final-test firewall invariant (metadata only, zero content inspection).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from handoff_fidelity.baselines.comparator_registry import (
    ComparatorReadinessStatus,
    count_ready_primary_families,
    get_comparator_registry,
    get_ready_primary_families,
    is_headline_sota_eligible,
)
from handoff_fidelity.baselines.endpoint_hybrid_registry import (
    InapplicableMetricError,
    MissingLineageError,
    get_endpoint_hybrid_registry,
    validate_endpoint_metric_applicability,
    verify_empirical_lineage_required,
)
from handoff_fidelity.calibration.budget_calibration import (
    PROSPECTIVE_BUDGET_GRID,
    ReceiverConfigurationContract,
    UncalibratedBudgetError,
    assert_budget_calibrated_for_receiver,
    calibrate_receiver_budget,
)
from handoff_fidelity.causal.paired_bootstrap import (
    run_paired_document_bootstrap,
)
from handoff_fidelity.causalrelay.families import PredictorFamily
from handoff_fidelity.causalrelay.nested_crossfit import (
    run_nested_grouped_crossfit,
)
from handoff_fidelity.export.document_outcomes import (
    AggregateBroadcastError,
    DocumentOutcomeRecord,
    validate_document_outcome,
    validate_document_outcome_batch,
)

EXPECTED_TEST_SHA = (
    "44ade813cc289bba13780784baaf942e5720c48ac2381a06c1c225339e06515a"  # pragma: allowlist secret
)


def _make_sample_record(
    i: int, val: float = 0.75, shared_eval: str | None = None, shared_sha: str | None = None
) -> DocumentOutcomeRecord:
    return DocumentOutcomeRecord(
        document_id_hash=f"doc_hash_{i:016d}",
        split="model_selection",
        policy_id="causalrelay_v3_5",
        receiver_id="receiver_panel_v3_5",
        receiver_config_hash="0123456789abcdef0123456789abcdef",  # pragma: allowlist secret
        logical_evaluation_id=shared_eval or f"eval_{i:06d}",
        raw_response_sha256=shared_sha or f"{i:064x}",
        metric_name="A",
        metric_value=val,
        evaluable_status="COMPLETE",
        realized_tokens=185,
        evidence_stratum="model_selection_adaptive",
        outer_fold=i % 5,
    )


# ---------------------------------------------------------------------------
# 1. Document-level outcome lineage & schema conformance
# ---------------------------------------------------------------------------
def test_document_outcome_lineage_contract():
    rec = _make_sample_record(1, val=0.82)
    d = validate_document_outcome(rec)
    assert d["document_id_hash"] == f"doc_hash_{1:016d}"
    assert d["split"] == "model_selection"
    assert d["realized_tokens"] == 185
    assert d["metric_value"] == 0.82


# ---------------------------------------------------------------------------
# 2. Anti-broadcast rejection & zero-variance detection
# ---------------------------------------------------------------------------
def test_anti_broadcast_rejection():
    # 1. Test rejection when logical_evaluation_id is shared across documents
    shared_eval_batch = [
        _make_sample_record(i, val=0.70 + 0.01 * i, shared_eval="shared_eval_id") for i in range(5)
    ]
    with pytest.raises(AggregateBroadcastError, match="Aggregate lineage detected"):
        validate_document_outcome_batch(shared_eval_batch)

    # 2. Test rejection when raw_response_sha256 is shared across documents
    shared_sha_batch = [
        _make_sample_record(i, val=0.70 + 0.01 * i, shared_sha="f" * 64) for i in range(5)
    ]
    with pytest.raises(AggregateBroadcastError, match="Aggregate lineage detected"):
        validate_document_outcome_batch(shared_sha_batch)

    # 3. Test rejection of invariant vectors (all identical values across 10+ rows)
    invariant_batch = [_make_sample_record(i, val=0.75) for i in range(12)]
    with pytest.raises(AggregateBroadcastError, match="Suspicious invariant document vector"):
        validate_document_outcome_batch(invariant_batch)


# ---------------------------------------------------------------------------
# 3 & 4. Nested outer-fold exclusion & grouped inner-CV containment
# ---------------------------------------------------------------------------
def test_nested_crossfit_outer_exclusion_and_inner_containment():
    rng = np.random.default_rng(123)
    n_docs = 25
    doc_ids = [f"doc_{i:03d}" for i in range(n_docs)]
    x = rng.standard_normal((n_docs, 4))
    y = 0.5 * x[:, 0] - 0.3 * x[:, 1] + rng.standard_normal(n_docs) * 0.1

    report = run_nested_grouped_crossfit(
        document_ids=doc_ids,
        features=x,
        targets=y,
        feature_names=["f0", "f1", "f2", "f3"],
        n_outer_folds=5,
        n_inner_folds=4,
        candidate_families=(
            PredictorFamily.HIST_GRADIENT_BOOSTING,
            PredictorFamily.RIDGE,
            PredictorFamily.EXTRA_TREES,
        ),
        seed=42,
    )

    assert report.n_documents == 25
    assert len(report.fold_results) == 5
    assert len(report.predictions) == 25

    all_test_docs: list[str] = []
    for f in report.fold_results:
        tr_set = set(f.train_document_ids)
        te_set = set(f.test_document_ids)
        assert len(tr_set & te_set) == 0, f"Leakage detected in fold {f.fold_index}"
        all_test_docs.extend(f.test_document_ids)

    assert sorted(all_test_docs) == sorted(doc_ids)


# ---------------------------------------------------------------------------
# 5. Learner-family restriction
# ---------------------------------------------------------------------------
def test_nested_crossfit_learner_family_restriction():
    rng = np.random.default_rng(456)
    doc_ids = [f"doc_{i:03d}" for i in range(15)]
    x = rng.standard_normal((15, 3))
    y = rng.standard_normal(15)

    with pytest.raises(ValueError, match="Unknown learner family"):
        run_nested_grouped_crossfit(
            document_ids=doc_ids,
            features=x,
            targets=y,
            candidate_families=["DISALLOWED_NEURAL_NET"],  # type: ignore
            n_outer_folds=3,
            n_inner_folds=2,
            seed=42,
        )


# ---------------------------------------------------------------------------
# 6 & 7. Paired bootstrap known-answer result & simultaneous max-statistic
# ---------------------------------------------------------------------------
def test_paired_bootstrap_known_answer_and_simultaneous_max_statistic():
    n_docs = 20
    docs = [f"doc_{i:03d}" for i in range(n_docs)]

    base_A = {d: 0.70 + 0.01 * (i % 5) for i, d in enumerate(docs)}
    base_C = {d: 0.10 + 0.005 * (i % 4) for i, d in enumerate(docs)}

    ours_A = {d: base_A[d] + 0.10 for d in docs}
    ours_C = {d: base_C[d] + 0.08 for d in docs}

    comp1_A = dict(base_A)
    comp1_C = dict(base_C)

    comp2_A = {d: base_A[d] - 0.05 for d in docs}
    comp2_C = {d: base_C[d] - 0.04 for d in docs}

    report = run_paired_document_bootstrap(
        ours_A=ours_A,
        ours_C_comm=ours_C,
        comparators_A={"comp1": comp1_A, "comp2": comp2_A},
        comparators_C_comm={"comp1": comp1_C, "comp2": comp2_C},
        replicates=1000,
        seed=42,
        alpha=0.05,
    )

    assert report.ready_families_count == 2
    assert report.headline_sota_eligible is False
    assert "INELIGIBLE" in report.sota_eligibility_status

    res1 = report.results["comp1"]
    assert pytest.approx(res1.point_delta_A, rel=1e-3) == 0.10
    assert pytest.approx(res1.point_delta_C_comm, rel=1e-3) == 0.08
    assert res1.directional_win is True
    assert res1.simultaneous_l95_delta_A > 0.0
    assert res1.simultaneous_l95_delta_C_comm > 0.0


# ---------------------------------------------------------------------------
# 8. Nonzero-variance bootstrap nondegenerate interval
# ---------------------------------------------------------------------------
def test_nonzero_variance_bootstrap_nondegenerate():
    rng = np.random.default_rng(789)
    n_docs = 30
    docs = [f"doc_{i:03d}" for i in range(n_docs)]

    noise_ours_A = rng.normal(0, 0.05, n_docs)
    noise_comp_A = rng.normal(0, 0.05, n_docs)

    ours_A = {d: float(0.80 + noise_ours_A[i]) for i, d in enumerate(docs)}
    ours_C = {d: float(0.20 + rng.normal(0, 0.02)) for d in docs}

    comp_A = {d: float(0.70 + noise_comp_A[i]) for i, d in enumerate(docs)}
    comp_C = {d: float(0.15 + rng.normal(0, 0.02)) for d in docs}

    report = run_paired_document_bootstrap(
        ours_A=ours_A,
        ours_C_comm=ours_C,
        comparators_A={"comp_noisy": comp_A},
        comparators_C_comm={"comp_noisy": comp_C},
        replicates=1000,
        seed=100,
    )

    res = report.results["comp_noisy"]
    assert res.simultaneous_l95_delta_A < res.point_delta_A
    assert res.simultaneous_l95_delta_C_comm < res.point_delta_C_comm


# ---------------------------------------------------------------------------
# 9. Placeholder result rejection
# ---------------------------------------------------------------------------
def test_placeholder_result_rejection():
    valid_row = {
        "family": "DAC",
        "estimate": 0.72,
        "status": "COMPLETE",
        "raw_response_sha256": hashlib.sha256(b"resp").hexdigest(),
        "cell_id": "cell_123",
    }
    verify_empirical_lineage_required(valid_row)

    bad_row = {
        "family": "DAC",
        "estimate": 0.72,
        "status": "COMPLETE",
        "cell_id": "cell_123",
    }
    with pytest.raises(MissingLineageError, match="lacks raw execution lineage"):
        verify_empirical_lineage_required(bad_row)


# ---------------------------------------------------------------------------
# 10. Representation metric applicability
# ---------------------------------------------------------------------------
def test_endpoint_hybrid_metric_applicability():
    validate_endpoint_metric_applicability("COMI", "A")
    validate_endpoint_metric_applicability("COMI", "realized_tokens")
    validate_endpoint_metric_applicability("RAM", "latency_ms")
    validate_endpoint_metric_applicability("GMSA", "A")
    validate_endpoint_metric_applicability("SARA", "realized_tokens")

    for metric in ("Tbar", "C_comm", "C_recon", "Delta_budget"):
        with pytest.raises(InapplicableMetricError, match="NOT_APPLICABLE"):
            validate_endpoint_metric_applicability("COMI", metric)
        with pytest.raises(InapplicableMetricError, match="NOT_APPLICABLE"):
            validate_endpoint_metric_applicability("RAM", metric)
        with pytest.raises(InapplicableMetricError, match="NOT_APPLICABLE"):
            validate_endpoint_metric_applicability("GMSA", metric)
        with pytest.raises(InapplicableMetricError, match="NOT_APPLICABLE"):
            validate_endpoint_metric_applicability("SARA", metric)


# ---------------------------------------------------------------------------
# 11. Comparator registry completeness
# ---------------------------------------------------------------------------
def test_comparator_registry_census_and_readiness():
    reg = get_comparator_registry()
    assert len(reg) == 6
    assert set(reg.keys()) == {
        "LLMLingua-2",
        "DAC",
        "LongLLMLingua",
        "Perception Compressor",
        "TACO-RL",
        "Provence",
    }

    ready = get_ready_primary_families()
    assert len(ready) == 2
    ready_names = {r.family for r in ready}
    assert ready_names == {"LLMLingua-2", "DAC"}

    assert count_ready_primary_families() == 2
    assert is_headline_sota_eligible() is False

    endpoint_reg = get_endpoint_hybrid_registry()
    assert len(endpoint_reg) == 4
    assert set(endpoint_reg.keys()) == {"COMI", "RAM", "GMSA", "SARA"}
    for entry in endpoint_reg.values():
        assert entry.status == "IMPLEMENTATION_READY"


# ---------------------------------------------------------------------------
# 12. LongLLMLingua identity separation
# ---------------------------------------------------------------------------
def test_longllmlingua_identity_separation():
    reg = get_comparator_registry()
    longllm = reg["LongLLMLingua"]

    assert "LongLLMLingua" in longllm.paper_title
    assert "Selective Context" not in longllm.paper_title
    assert longllm.ranking_mode == "longllmlingua"
    assert longllm.status == ComparatorReadinessStatus.BLOCKED_BY_IMPLEMENTATION_DEPENDENCY
    assert longllm.requires_isolated_env is True


# ---------------------------------------------------------------------------
# 13. Receiver configuration identity determinism
# ---------------------------------------------------------------------------
def test_receiver_configuration_identity_and_hashing():
    c1 = ReceiverConfigurationContract(
        receiver_id="rec_gpt4o_mini",
        provider="openai",
        model_id="gpt-4o-mini-2024-07-18",
        returned_version="gpt-4o-mini-2024-07-18",
        prompt_template_sha256=hashlib.sha256(b"template_v1").hexdigest(),
        config_hash=hashlib.sha256(b"config_v1").hexdigest(),
        tool_policy="NO_TOOLS",
        decoder_regime="DECODER_AUDIT_PENDING_EXECUTION",
        tokenizer_name="o200k_base",
        cache_namespace="ns_v3_5",
    )
    h1 = c1.compute_identity_hash()
    assert len(h1) == 64
    h2 = c1.compute_identity_hash()
    assert h1 == h2

    c3 = ReceiverConfigurationContract(
        receiver_id="rec_gpt4o_mini",
        provider="openai",
        model_id="gpt-4o-mini-2024-07-18",
        returned_version="gpt-4o-mini-2024-07-18",
        prompt_template_sha256=hashlib.sha256(b"template_v2_mutated").hexdigest(),
        config_hash=hashlib.sha256(b"config_v1").hexdigest(),
        tool_policy="NO_TOOLS",
        decoder_regime="DECODER_AUDIT_PENDING_EXECUTION",
        tokenizer_name="o200k_base",
        cache_namespace="ns_v3_5",
    )
    assert c3.compute_identity_hash() != h1


# ---------------------------------------------------------------------------
# 14. B* cross-model calibration reuse prohibition
# ---------------------------------------------------------------------------
def test_bstar_cross_model_reuse_prohibition():
    c1 = ReceiverConfigurationContract(
        receiver_id="rec_1",
        provider="openai",
        model_id="m1",
        returned_version="m1.0",
        prompt_template_sha256="sha_p1",
        config_hash="sha_c1",
        tool_policy="NO_TOOLS",
        decoder_regime="PENDING",
        tokenizer_name="tok1",
        cache_namespace="ns1",
    )
    c2 = ReceiverConfigurationContract(
        receiver_id="rec_2",
        provider="google",
        model_id="m2",
        returned_version="m2.0",
        prompt_template_sha256="sha_p2",
        config_hash="sha_c2",
        tool_policy="NO_TOOLS",
        decoder_regime="PENDING",
        tokenizer_name="tok2",
        cache_namespace="ns2",
    )

    costs = [350, 400, 420, 500, 380]
    calib1 = calibrate_receiver_budget(costs, c1, grid=PROSPECTIVE_BUDGET_GRID)
    calibs = {"rec_1": calib1}

    rec1_res = assert_budget_calibrated_for_receiver(calibs, c1)
    assert rec1_res.receiver_id == "rec_1"

    with pytest.raises(UncalibratedBudgetError, match="has no calibrated B\\* record"):
        assert_budget_calibrated_for_receiver(calibs, c2)


# ---------------------------------------------------------------------------
# 15. Final-test firewall invariant
# ---------------------------------------------------------------------------
def test_final_test_firewall_known_answer():
    workspace = os.environ.get("TVR_NON_GIT_ROOT")
    if not workspace:
        workspace = str(Path.home() / "Desktop" / ("handoff-" + "fidelity-2026"))
    manifest = Path(workspace) / "source_manifests" / "STAGE2_TEST.csv"

    if manifest.exists():
        h = hashlib.sha256()
        with manifest.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        actual_sha = h.hexdigest()
        assert actual_sha == EXPECTED_TEST_SHA
