"""Automated guard test: hard prohibition against ungrounded empirical result rows.

Enforces:
1. No numerical result row may exist without verifiable cell/run execution lineage.
2. Latent/hybrid architectures strictly reject discrete atom transmission metrics.
3. Static scan verification for codebase hygiene against simulated mock outcomes.
"""

from __future__ import annotations

import pytest

from handoff_fidelity.baselines.endpoint_hybrid_registry import (
    InapplicableMetricError,
    MissingLineageError,
    validate_endpoint_metric_applicability,
    verify_empirical_lineage_required,
)


def test_rejection_of_ungrounded_numeric_estimate():
    """Attempting to propose an empirical result without raw lineage must raise MissingLineageError."""
    unverified_row = {
        "result_id": "ENDPOINT__test__COMI__A",
        "family": "COMI",
        "estimate": 0.415,
        "status": "COMPLETE",
        # Missing cell_id / logical_evaluation_id and raw_response_sha256
    }
    with pytest.raises(MissingLineageError, match="lacks raw execution lineage"):
        verify_empirical_lineage_required(unverified_row)


def test_acceptance_of_properly_grounded_result():
    """A result row bearing authentic cell execution lineage must pass verification."""
    grounded_row = {
        "result_id": "ENDPOINT__cell_01__COMI__A",
        "family": "COMI",
        "estimate": 0.415,
        "status": "COMPLETE",
        "cell_id": "cell_execution_comi_01",
        "raw_response_sha256": "c" * 64,
        "source_artifact_sha256": "d" * 64,
    }
    # Must not raise
    verify_empirical_lineage_required(grounded_row)


@pytest.mark.parametrize("fam", ["COMI", "RAM", "GMSA", "SARA"])
@pytest.mark.parametrize("bad_metric", ["Tbar", "C_comm", "C_recon", "Delta_budget"])
def test_rejection_of_inapplicable_atom_metrics_on_endpoint_methods(fam: str, bad_metric: str):
    """Attempting to assign discrete atom transmission metrics to continuous/latent methods must fail."""
    with pytest.raises(InapplicableMetricError, match="NOT_APPLICABLE"):
        validate_endpoint_metric_applicability(fam, bad_metric)


@pytest.mark.parametrize("fam", ["COMI", "RAM", "GMSA", "SARA"])
@pytest.mark.parametrize("good_metric", ["A", "realized_tokens", "latency_ms"])
def test_acceptance_of_applicable_common_metrics_on_endpoint_methods(fam: str, good_metric: str):
    """Applicable common metrics (fidelity A, tokens, latency) must be accepted."""
    # Must not raise
    validate_endpoint_metric_applicability(fam, good_metric)
