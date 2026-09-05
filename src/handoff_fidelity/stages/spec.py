"""Stage definitions and their guards.

Stages are declared here and EXECUTED nowhere in this repository. Every stage
carries the guard conditions that must hold before it may run; the guards are
checked mechanically because "we remembered not to look at the test set" is not
a protocol.

Sizes marked PROPOSED are not yet frozen and must be approved before the
preregistration is hashed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class Stage(StrEnum):
    CALIBRATION = "CALIBRATION"
    STAGE1 = "STAGE1"
    STAGE2_DEV = "STAGE2_DEV"
    STAGE2_TEST = "STAGE2_TEST"
    EXPERIMENT_C = "EXPERIMENT_C"
    MULTIHOP = "MULTIHOP"


@dataclass(frozen=True, slots=True)
class StageSpec:
    stage: Stage
    n_documents: int | None
    proposed: bool
    requires_protocol_freeze: bool
    requires_test_freeze: bool
    requires_gate_passed: bool
    may_fit_models: bool
    may_inspect_outputs: bool
    description: str


STAGES: dict[Stage, StageSpec] = {
    Stage.CALIBRATION: StageSpec(
        Stage.CALIBRATION,
        None,
        False,
        False,
        False,
        False,
        False,
        True,
        "Instrument validation only: atomizer kappa, matcher precision/recall, editor "
        "validity, determinism audit. Runs on the calibration pool, which is disjoint "
        "from every experimental split by issuer.",
    ),
    Stage.STAGE1: StageSpec(
        Stage.STAGE1,
        100,
        False,
        True,
        False,
        False,
        False,
        True,
        "Mechanism discovery. Experiment A + Experiment B + placebo. No CausalRelay "
        "training and no SOTA superiority claim.",
    ),
    Stage.STAGE2_DEV: StageSpec(
        Stage.STAGE2_DEV,
        100,
        True,
        True,
        False,
        True,
        True,
        True,
        "PROPOSED. Development split: external budget-adapter calibration and "
        "CausalRelay fitting. Fully instrumented for Delta^bu on the predeclared "
        "candidate set.",
    ),
    Stage.STAGE2_TEST: StageSpec(
        Stage.STAGE2_TEST,
        200,
        True,
        True,
        True,
        True,
        False,
        False,
        "PROPOSED. Sealed final test. Used exactly once, after the test freeze record "
        "validates. No fitting, no tuning, no inspection during baseline debugging.",
    ),
    Stage.EXPERIMENT_C: StageSpec(
        Stage.EXPERIMENT_C,
        None,
        True,
        True,
        False,
        True,
        False,
        True,
        "PROPOSED subset size. Post-gate, fully instrumented candidate sets for "
        "budget-neutral targeting.",
    ),
    Stage.MULTIHOP: StageSpec(
        Stage.MULTIHOP,
        None,
        True,
        True,
        False,
        True,
        False,
        True,
        "PROPOSED. Depth sweep h in {1,2,3,5}. Post-gate.",
    ),
}


class StageGuardError(RuntimeError):
    pass


def check_split_disjoint(
    stage1_ids: Sequence[str], stage2_ids: Sequence[str], issuer_of: dict[str, str] | None = None
) -> None:
    """No Stage-1 document may appear in Stage 2, and the splits should be
    issuer-disjoint where feasible."""
    overlap = sorted(set(stage1_ids) & set(stage2_ids))
    if overlap:
        raise StageGuardError(f"{len(overlap)} documents appear in both Stage 1 and Stage 2")
    if issuer_of:
        i1 = {issuer_of[d] for d in stage1_ids if d in issuer_of}
        i2 = {issuer_of[d] for d in stage2_ids if d in issuer_of}
        shared = sorted(i1 & i2)
        if shared:
            raise StageGuardError(
                f"{len(shared)} issuers appear in both Stage 1 and Stage 2; the split "
                "must be issuer-disjoint where feasible"
            )


def check_dev_test_disjoint(dev_ids: Sequence[str], test_ids: Sequence[str]) -> None:
    overlap = sorted(set(dev_ids) & set(test_ids))
    if overlap:
        raise StageGuardError(
            f"{len(overlap)} documents appear in both the development and the sealed "
            "test split; the benchmark would be fitted on its own test set"
        )
