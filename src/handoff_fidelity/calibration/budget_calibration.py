"""Model-specific and tokenizer-specific B* calibration interface (V3.5).

Enforces:
1. Exact receiver/provider/model/tokenizer identity contract.
2. Independent calibration per receiver/tokenizer combination.
3. Prospective candidate budget sensitivity grid {200, 250, 300, 350, 400, 500}.
4. Structural prohibition against cross-model budget reuse without calibration.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

PROSPECTIVE_BUDGET_GRID: tuple[int, ...] = (200, 250, 300, 350, 400, 500)
PRIMARY_DESIGN_BUDGET: int = 200
TARGET_COMPRESSION_RATIO: float = 2.0


class UncalibratedBudgetError(ValueError):
    """Raised when an uncalibrated budget is assigned across different receivers."""


@dataclass(frozen=True, slots=True)
class ReceiverConfigurationContract:
    receiver_id: str
    provider: str
    model_id: str
    returned_version: str | None
    prompt_template_sha256: str
    config_hash: str
    tool_policy: str
    decoder_regime: str
    tokenizer_name: str
    cache_namespace: str

    def compute_identity_hash(self) -> str:
        rep = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(rep.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelCalibrationRecord:
    receiver_id: str
    receiver_identity_hash: str
    tokenizer_name: str
    b_star: int
    median_rho: float
    per_candidate_rho: dict[int, float]
    n_calibration_documents: int
    selection_rule: str = "argmin_B |median_i(F_i / B) - 2|, ties toward larger B"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calibrate_receiver_budget(
    full_render_costs: Sequence[int],
    receiver_contract: ReceiverConfigurationContract,
    *,
    grid: Sequence[int] = PROSPECTIVE_BUDGET_GRID,
    target_rho: float = TARGET_COMPRESSION_RATIO,
) -> ModelCalibrationRecord:
    """Compute independent B* for an exact receiver and tokenizer configuration.

    B* = argmin_B |median_i(F_i / B) - 2|, with ties resolved to the larger budget.
    """
    costs = [int(c) for c in full_render_costs]
    if not costs:
        raise ValueError("Cannot calibrate budget with zero documents")
    if any(c <= 0 for c in costs):
        raise ValueError("Full-inventory render cost must be strictly positive")

    per_cand: dict[int, float] = {}
    for b in sorted(grid):
        ratios = [c / b for c in costs]
        per_cand[int(b)] = float(statistics.median(ratios))

    # Conservatively tie-break toward larger B
    b_star = max(per_cand, key=lambda b: (-abs(per_cand[b] - target_rho), b))

    ident_hash = receiver_contract.compute_identity_hash()

    return ModelCalibrationRecord(
        receiver_id=receiver_contract.receiver_id,
        receiver_identity_hash=ident_hash,
        tokenizer_name=receiver_contract.tokenizer_name,
        b_star=b_star,
        median_rho=per_cand[b_star],
        per_candidate_rho=per_cand,
        n_calibration_documents=len(costs),
    )


def assert_budget_calibrated_for_receiver(
    calibrations: dict[str, ModelCalibrationRecord],
    receiver_contract: ReceiverConfigurationContract,
) -> ModelCalibrationRecord:
    """Verify that a valid calibration exists specifically for this receiver configuration."""
    rec_id = receiver_contract.receiver_id
    calib = calibrations.get(rec_id)
    if calib is None:
        raise UncalibratedBudgetError(f"Receiver '{rec_id}' has no calibrated B* record.")

    expected_hash = receiver_contract.compute_identity_hash()
    if calib.receiver_identity_hash != expected_hash:
        raise UncalibratedBudgetError(
            f"Receiver configuration drift detected for '{rec_id}'. "
            f"Expected identity hash {expected_hash}, found {calib.receiver_identity_hash}."
        )

    return calib
