"""Calibration-time selection rules for the four unresolved parameters.

Each rule is FROZEN; only its realisation is pending. Every rule here reads
DETERMINISTIC SOURCE AND RENDER PROPERTIES ONLY. None may read receiver
outcomes, CausalRelay scores, comparator performance or final-test data -- and
the signatures make that structurally hard, because none of them accepts an
outcome.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

BUDGET_GRID: tuple[int, ...] = (200, 250, 300, 350, 400, 500)
TARGET_RHO: float = 2.0
EVICTION_GRID: tuple[int, ...] = (0, 1, 2, 4, 8)
EVICTION_RETENTION_FLOOR: float = 0.80
EXPC_GRID: tuple[int, ...] = (20, 30, 50)
EXPC_CALL_BUDGET_FRACTION: float = 0.15
EXPC_RETENTION_FLOOR: float = 0.80


class OutcomeLeakError(AssertionError):
    """Raised if a selection rule is handed anything outcome-derived."""


@dataclass(frozen=True, slots=True)
class BudgetSelection:
    b_star: int
    median_rho: float
    per_candidate: dict[int, float]
    n_documents: int
    rule: str = "argmin_B |median_i(F_i / B) - 2|, ties toward larger B"

    @property
    def binds(self) -> bool:
        return self.median_rho > 1.0


def select_primary_budget(
    full_render_costs: Sequence[int],
    *,
    grid: Sequence[int] = BUDGET_GRID,
    target_rho: float = TARGET_RHO,
) -> BudgetSelection:
    r"""Choose :math:`B^\star = \arg\min_B |\mathrm{median}_i(F_i/B) - 2|`.

    ``full_render_costs`` are the deterministic full-inventory render costs
    :math:`F_i` of the calibration documents -- a property of the source and the
    frozen renderer alone. Ties resolve toward the LARGER budget, which is the
    conservative direction: it errs toward a less punishing benchmark rather
    than toward manufacturing difficulty.
    """
    costs = [int(c) for c in full_render_costs]
    if not costs:
        raise ValueError("no calibration documents supplied")
    if any(c <= 0 for c in costs):
        raise ValueError("full-inventory render cost must be positive")

    per_candidate = {int(b): statistics.median(c / b for c in costs) for b in sorted(grid)}
    # max() over sorted-ascending candidates with a negated distance key gives
    # the LARGER budget on a tie, without a second pass.
    b_star = max(per_candidate, key=lambda b: (-abs(per_candidate[b] - target_rho), b))
    return BudgetSelection(
        b_star=b_star,
        median_rho=per_candidate[b_star],
        per_candidate=per_candidate,
        n_documents=len(costs),
    )


@dataclass(frozen=True, slots=True)
class EvictionSelection:
    tolerance: int | None
    retention: dict[int, float]
    floor: float = EVICTION_RETENTION_FLOOR

    @property
    def resolved(self) -> bool:
        return self.tolerance is not None


def select_eviction_tolerance(
    retention_by_tolerance: dict[int, float],
    *,
    grid: Sequence[int] = EVICTION_GRID,
    floor: float = EVICTION_RETENTION_FLOOR,
) -> EvictionSelection:
    """Smallest tolerance retaining at least ``floor`` of otherwise-eligible
    matched insert/evict pairs.

    Smallest-that-qualifies rather than largest-available: a looser tolerance
    buys retention by weakening budget neutrality, which is the property the
    swap exists to provide.
    """
    retention = {
        int(t): float(retention_by_tolerance[t])
        for t in sorted(grid)
        if t in retention_by_tolerance
    }
    if not retention:
        raise ValueError("no retention measurements supplied")
    for tol in sorted(retention):
        if retention[tol] >= floor:
            return EvictionSelection(tolerance=tol, retention=retention, floor=floor)
    return EvictionSelection(tolerance=None, retention=retention, floor=floor)


@dataclass(frozen=True, slots=True)
class ExperimentCSelection:
    subset_size: int | None
    projected_calls: dict[int, int]
    call_budget: int
    retention: float
    rejected: dict[int, str] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.subset_size is not None


def select_experiment_c_subset(
    *,
    median_candidates_per_document: int,
    development_receiver_call_budget: int,
    matched_pair_retention: float,
    grid: Sequence[int] = EXPC_GRID,
    call_budget_fraction: float = EXPC_CALL_BUDGET_FRACTION,
    retention_floor: float = EXPC_RETENTION_FLOOR,
    calls_per_candidate: int = 2,
) -> ExperimentCSelection:
    """Largest subset satisfying BOTH the call-budget cap and the retention floor.

    Experiment C is the largest cost line in the project because :math:`G^\\star`
    needs :math:`\\Delta^{\\mathrm{bu}}` for every candidate in the feasible set,
    so the cap is what keeps it affordable.
    """
    ceiling = int(development_receiver_call_budget * call_budget_fraction)
    projected = {
        int(n): int(n) * int(median_candidates_per_document) * calls_per_candidate
        for n in sorted(grid)
    }
    rejected: dict[int, str] = {}
    chosen: int | None = None
    for n in sorted(grid, reverse=True):
        if matched_pair_retention < retention_floor:
            rejected[n] = (
                f"matched-pair retention {matched_pair_retention:.3f} < floor {retention_floor:.2f}"
            )
            continue
        if projected[n] > ceiling:
            rejected[n] = f"projected {projected[n]} calls > ceiling {ceiling}"
            continue
        chosen = n
        break
    return ExperimentCSelection(
        subset_size=chosen,
        projected_calls=projected,
        call_budget=ceiling,
        retention=matched_pair_retention,
        rejected=rejected,
    )
