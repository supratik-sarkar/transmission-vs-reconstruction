"""Automated guard test: prevention of aggregate summary distribution to document rows.

Fails closed if aggregate-level summary statistics are copied/broadcast across
document outcome rows without independent document execution lineage.
"""

from __future__ import annotations

import pytest

from handoff_fidelity.causal.paired_bootstrap import (
    BootstrapDataIntegrityError,
    run_paired_document_bootstrap,
)
from handoff_fidelity.export.document_outcomes import (
    AggregateBroadcastError,
    DocumentOutcomeRecord,
    validate_document_outcome_batch,
)


def _make_dummy_row(doc_id: str, value: float, eval_id: str, raw_sha: str) -> DocumentOutcomeRecord:
    return DocumentOutcomeRecord(
        document_id_hash=doc_id,
        split="model_selection",
        outer_fold=0,
        policy_id="test_policy",
        receiver_id="test_receiver",
        receiver_config_hash="0123456789abcdef",
        logical_evaluation_id=eval_id,
        raw_response_sha256=raw_sha,
        metric_name="A",
        metric_value=value,
        evaluable_status="COMPLETE",
        realized_tokens=200,
        evidence_stratum="model_selection_adaptive",
    )


def test_rejection_of_shared_logical_eval_lineage():
    """Attempting to distribute rows that share one logical evaluation ID must raise AggregateBroadcastError."""
    rows = [
        _make_dummy_row(f"doc_hash_{i:016d}", 0.42, eval_id="shared_eval_id_001", raw_sha="a" * 64)
        for i in range(5)
    ]
    with pytest.raises(AggregateBroadcastError, match="Aggregate lineage detected"):
        validate_document_outcome_batch(rows)


def test_rejection_of_shared_raw_response_hash():
    """Attempting to assign rows that share one raw response hash across documents must be rejected."""
    rows = [
        _make_dummy_row(f"doc_hash_{i:016d}", 0.42, eval_id=f"eval_id_{i}", raw_sha="b" * 64)
        for i in range(5)
    ]
    with pytest.raises(AggregateBroadcastError, match="Aggregate lineage detected"):
        validate_document_outcome_batch(rows)


def test_rejection_of_invariant_cloned_vectors():
    """Attempting to populate 10+ document rows with identical scalar values must be rejected."""
    rows = [
        _make_dummy_row(f"doc_hash_{i:016d}", 0.385, eval_id=f"eval_{i}", raw_sha=f"{i:064x}")
        for i in range(12)
    ]
    with pytest.raises(AggregateBroadcastError, match="Suspicious invariant document vector"):
        validate_document_outcome_batch(rows)


def test_acceptance_of_genuine_distinct_outcomes():
    """Authentic document rows with distinct evaluations, hashes, and realistic values must pass."""
    rows = [
        _make_dummy_row(
            f"doc_hash_{i:016d}", 0.35 + 0.01 * (i % 5), eval_id=f"eval_{i}", raw_sha=f"{i:064x}"
        )
        for i in range(15)
    ]
    validated = validate_document_outcome_batch(rows)
    assert len(validated) == 15


def test_bootstrap_rejects_mismatched_or_duplicate_lineage():
    """Paired bootstrap must reject inputs with duplicated document keys or missing vectors."""
    ours_A = {"doc_1": 0.45, "doc_2": 0.42}
    ours_C = {"doc_1": 0.43, "doc_2": 0.40}
    comp_A = {"c1": {"doc_1": 0.38}}  # missing doc_2
    comp_C = {"c1": {"doc_1": 0.37}}

    with pytest.raises(BootstrapDataIntegrityError, match="Insufficient common documents"):
        run_paired_document_bootstrap(
            ours_A=ours_A,
            ours_C_comm=ours_C,
            comparators_A=comp_A,
            comparators_C_comm=comp_C,
            replicates=50,
        )
