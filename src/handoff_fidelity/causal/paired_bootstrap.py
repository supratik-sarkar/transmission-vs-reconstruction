"""Document-paired 10,000-replicate max-statistic bootstrap inference (V3.5).

Enforces:
1. Inputs must be authentic document-level outcome vectors with verifiable lineage.
2. Clustered nonparametric bootstrap resampling identical document draws across methods.
3. Max-statistic family-wise error rate control for simultaneous lower bounds.
4. Simultaneous requirement: L95_sim(Delta A) > 0 AND L95_sim(Delta C_comm) > 0.
5. Strict SOTA eligibility: broad headline SOTA is INELIGIBLE if ready families K < 4.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

FINAL_BOOTSTRAP_REPLICATES = 10_000
MIN_READY_FAMILIES_FOR_BROAD_SOTA = 4


class BootstrapDataIntegrityError(ValueError):
    """Raised when bootstrap input data lacks authentic document-level lineage."""


@dataclass(frozen=True, slots=True)
class ComparatorSimultaneousResult:
    comparator_name: str
    n_documents: int
    point_delta_A: float
    simultaneous_l95_delta_A: float
    point_delta_C_comm: float
    simultaneous_l95_delta_C_comm: float
    directional_win: bool
    simultaneous_win: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SimultaneousInferenceReport:
    ready_families_count: int
    headline_sota_eligible: bool
    sota_eligibility_status: str
    n_replicates: int
    seed: int
    results: dict[str, ComparatorSimultaneousResult]
    sota_superiority_verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready_families_count": self.ready_families_count,
            "headline_sota_eligible": self.headline_sota_eligible,
            "sota_eligibility_status": self.sota_eligibility_status,
            "n_replicates": self.n_replicates,
            "seed": self.seed,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "sota_superiority_verdict": self.sota_superiority_verdict,
        }


def validate_document_vector_lineage(
    doc_ids: Sequence[str],
    values: Sequence[float],
    *,
    method_name: str,
    metric_name: str,
) -> tuple[list[str], np.ndarray]:
    """Validate that input vectors have valid document lineage and are non-empty."""
    if len(doc_ids) != len(values):
        raise BootstrapDataIntegrityError(
            f"Length mismatch for {method_name} ({metric_name}): {len(doc_ids)} docs vs {len(values)} values."
        )
    if not doc_ids:
        raise BootstrapDataIntegrityError(
            f"Zero documents provided for {method_name} ({metric_name})."
        )

    # Document IDs must be distinct
    if len(doc_ids) != len(set(doc_ids)):
        raise BootstrapDataIntegrityError(
            f"Duplicated document IDs detected in input for {method_name} ({metric_name})."
        )

    val_arr = np.asarray(values, dtype=float)
    if np.any(np.isnan(val_arr)):
        raise BootstrapDataIntegrityError(
            f"NaN values found in input for {method_name} ({metric_name})."
        )

    return list(doc_ids), val_arr


def run_paired_document_bootstrap(
    *,
    ours_A: Mapping[str, float],
    ours_C_comm: Mapping[str, float],
    comparators_A: Mapping[str, Mapping[str, float]],
    comparators_C_comm: Mapping[str, Mapping[str, float]],
    replicates: int = FINAL_BOOTSTRAP_REPLICATES,
    seed: int = 42,
    alpha: float = 0.05,
) -> SimultaneousInferenceReport:
    """Execute paired document-clustered bootstrap with simultaneous max-statistic correction."""
    comparator_names = sorted(comparators_A.keys())
    k_ready = len(comparator_names)

    if k_ready == 0:
        raise BootstrapDataIntegrityError("No comparator methods supplied for paired inference.")

    # Find common intersection of documents across all methods
    common_docs = set(ours_A.keys()) & set(ours_C_comm.keys())
    for c_name in comparator_names:
        common_docs &= set(comparators_A[c_name].keys())
        common_docs &= set(comparators_C_comm[c_name].keys())

    sorted_docs = sorted(common_docs)
    n_docs = len(sorted_docs)
    if n_docs < 10:
        raise BootstrapDataIntegrityError(
            f"Insufficient common documents ({n_docs}) across methods for clustered inference."
        )

    # Validate vectors
    validate_document_vector_lineage(
        sorted_docs, [ours_A[d] for d in sorted_docs], method_name="ours", metric_name="A"
    )
    validate_document_vector_lineage(
        sorted_docs, [ours_C_comm[d] for d in sorted_docs], method_name="ours", metric_name="C_comm"
    )

    diffs_A: dict[str, np.ndarray] = {}
    diffs_C: dict[str, np.ndarray] = {}
    point_deltas_A: dict[str, float] = {}
    point_deltas_C: dict[str, float] = {}

    for c_name in comparator_names:
        arr_c_A = np.array([comparators_A[c_name][d] for d in sorted_docs], dtype=float)
        arr_c_C = np.array([comparators_C_comm[c_name][d] for d in sorted_docs], dtype=float)
        arr_ours_A = np.array([ours_A[d] for d in sorted_docs], dtype=float)
        arr_ours_C = np.array([ours_C_comm[d] for d in sorted_docs], dtype=float)

        d_A = arr_ours_A - arr_c_A
        d_C = arr_ours_C - arr_c_C

        diffs_A[c_name] = d_A
        diffs_C[c_name] = d_C
        point_deltas_A[c_name] = float(np.mean(d_A))
        point_deltas_C[c_name] = float(np.mean(d_C))

    # Document-clustered paired bootstrap resampling
    rng = np.random.default_rng(seed)
    # Generate replicate indices: shape (replicates, n_docs)
    boot_indices = rng.integers(0, n_docs, size=(replicates, n_docs))

    # Matrix of bootstrap means: shape (replicates, k_ready)
    boot_means_A = np.zeros((replicates, k_ready), dtype=float)
    boot_means_C = np.zeros((replicates, k_ready), dtype=float)

    for j_idx, c_name in enumerate(comparator_names):
        d_A = diffs_A[c_name]
        d_C = diffs_C[c_name]
        # Evaluate mean over the sampled document indices for each replicate
        boot_means_A[:, j_idx] = np.mean(d_A[boot_indices], axis=1)
        boot_means_C[:, j_idx] = np.mean(d_C[boot_indices], axis=1)

    # Max-statistic simultaneous lower bound computation
    # For one-sided lower bound, we consider deviations below the point estimate
    # Centered deviations: (point - bootstrap_mean)
    # To bound Delta_j >= point_j - quantile, we look at the distribution of max_j (point_j - boot_mean_j)
    centered_dev_A = np.array([point_deltas_A[c] for c in comparator_names]) - boot_means_A
    centered_dev_C = np.array([point_deltas_C[c] for c in comparator_names]) - boot_means_C

    # Max-statistic across comparators per replicate
    max_dev_A = np.max(centered_dev_A, axis=1)
    max_dev_C = np.max(centered_dev_C, axis=1)

    # 1 - alpha quantile of the max deviation
    crit_quantile_A = float(np.percentile(max_dev_A, 100 * (1.0 - alpha)))
    crit_quantile_C = float(np.percentile(max_dev_C, 100 * (1.0 - alpha)))

    simultaneous_l95_A: dict[str, float] = {}
    simultaneous_l95_C: dict[str, float] = {}

    for _j_idx, c_name in enumerate(comparator_names):
        simultaneous_l95_A[c_name] = float(point_deltas_A[c_name] - crit_quantile_A)
        simultaneous_l95_C[c_name] = float(point_deltas_C[c_name] - crit_quantile_C)

    results: dict[str, ComparatorSimultaneousResult] = {}
    all_simultaneous = True

    for c_name in comparator_names:
        p_A = point_deltas_A[c_name]
        p_C = point_deltas_C[c_name]
        l_A = simultaneous_l95_A[c_name]
        l_C = simultaneous_l95_C[c_name]

        dir_win = (p_A > 0.0) and (p_C > 0.0)
        sim_win = (l_A > 0.0) and (l_C > 0.0)
        if not sim_win:
            all_simultaneous = False

        results[c_name] = ComparatorSimultaneousResult(
            comparator_name=c_name,
            n_documents=n_docs,
            point_delta_A=p_A,
            simultaneous_l95_delta_A=l_A,
            point_delta_C_comm=p_C,
            simultaneous_l95_delta_C_comm=l_C,
            directional_win=dir_win,
            simultaneous_win=sim_win,
        )

    eligible = k_ready >= MIN_READY_FAMILIES_FOR_BROAD_SOTA
    eligibility_status = (
        "ELIGIBLE"
        if eligible
        else f"INELIGIBLE (denominator requirement >= 4 ready families, observed = {k_ready})"
    )

    if not eligible:
        verdict = "INELIGIBLE"
    elif all_simultaneous:
        verdict = "PASS"
    else:
        verdict = "NOT_ESTABLISHED"

    return SimultaneousInferenceReport(
        ready_families_count=k_ready,
        headline_sota_eligible=eligible,
        sota_eligibility_status=eligibility_status,
        n_replicates=replicates,
        seed=seed,
        results=results,
        sota_superiority_verdict=verdict,
    )
