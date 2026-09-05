"""Deterministic self-tests.

Runnable without pytest so that the invariants can be checked anywhere,
including inside a minimal container. ``pytest`` exercises the same functions
through ``tests/``.

Every check here is an INVARIANT OF THE DESIGN, not a smoke test: if one fails,
a scientific claim in the protocol is unsupported.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .causal.estimands import decompose
from .causal.sham_partial import corrected_delta, sign_for
from .causal.targeting import knapsack
from .models import Atom, AtomCausalRecord, AtomRole, VerificationStatus
from .sampling.design import (
    DocumentIneligible,
    all_inclusion_probabilities,
    select_focal,
)


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    name: str
    passed: bool
    detail: str


def _atom(doc: str, role: AtomRole, i: int) -> Atom:
    return Atom(
        document_id=doc,
        atom_id=f"{doc}:{role.value}:{i}",
        role=role,
        canonical_value=f"{role.value}-{i}",
        surface_form=f"{role.value}-{i}",
        char_start=i * 10,
        char_end=i * 10 + 5,
        token_start=i,
        token_end=i + 1,
        local_context="",
        sentence_index=i,
        verification=VerificationStatus.ACCEPTED,
    )


def check_sampling_positivity(trials: int = 2000, seed: int = 11) -> CheckOutcome:
    """sum_z pi_iz == k exactly, and every atom has pi > 0.

    The earlier "k most populated strata" rule gave pi = 0 off-support, leaving
    the Hajek estimator undefined on part of the target population.
    """
    rng = random.Random(seed)
    worst_sum = 0.0
    min_pi = 1.0
    for _ in range(trials):
        roles = rng.sample(list(AtomRole), rng.randint(3, 5))
        atoms = [_atom("d", r, i) for r in roles for i in range(rng.randint(1, 6))]
        pis = all_inclusion_probabilities(atoms, k=3)
        worst_sum = max(worst_sum, abs(sum(pis.values()) - 3.0))
        min_pi = min(min_pi, min(pis.values()))
        if len(pis) != len(atoms) or min(pis.values()) <= 0:
            return CheckOutcome("sampling_positivity", False, "an atom received pi <= 0")
    return CheckOutcome(
        "sampling_positivity",
        worst_sum < 1e-12,
        f"max |sum(pi) - 3| = {worst_sum:.3e}, min pi = {min_pi:.4f}, {trials} trials",
    )


def check_sampling_determinism(seed: int = 5) -> CheckOutcome:
    """Same seed and same inventory give the same focal sample regardless of the
    order atoms arrive in."""
    roles = list(AtomRole)[:4]
    atoms = [_atom("d", r, i) for r in roles for i in range(3)]
    a = [f.atom_id for f in select_focal(atoms, rng=random.Random(seed))]
    shuffled = atoms[:]
    random.Random(99).shuffle(shuffled)
    b = [f.atom_id for f in select_focal(shuffled, rng=random.Random(seed))]
    return CheckOutcome("sampling_determinism", a == b, f"{a} vs {b}")


def check_ineligible_document() -> CheckOutcome:
    atoms = [_atom("d", AtomRole.ENTITY, 0), _atom("d", AtomRole.SCOPE, 1)]
    try:
        select_focal(atoms, rng=random.Random(0))
    except DocumentIneligible:
        return CheckOutcome("ineligible_document", True, "2 strata correctly rejected")
    return CheckOutcome("ineligible_document", False, "a 2-stratum document was accepted")


def check_decomposition_identity(trials: int = 400, seed: int = 3) -> CheckOutcome:
    rng = random.Random(seed)
    worst = 0.0
    for _ in range(trials):
        recs = [
            AtomCausalRecord(
                document_id=f"d{rng.randint(0, 6)}",
                atom_id=f"a{i}",
                role=rng.choice(list(AtomRole)),
                pi=rng.uniform(0.05, 1.0),
                transmitted=rng.randint(0, 1),
                r_minus=float(rng.randint(0, 1)),
                d_plus=float(rng.randint(0, 1)),
            )
            for i in range(rng.randint(6, 40))
        ]
        worst = max(worst, abs(decompose(recs).identity_residual))
    return CheckOutcome(
        "decomposition_identity",
        worst < 1e-10,
        f"max |A - (Rbar0 + Tbar*Dbar + Cov)| = {worst:.3e} over {trials} trials",
    )


def check_selection_bias_identity(trials: int = 400, seed: int = 4) -> CheckOutcome:
    """The selection bias must agree along all THREE computational routes.

        (a) R^obs - Rbar_0                              (definition)
        (b) -Cov(T, R^-) / (1 - Tbar)                   (covariance form)
        (c) Tbar * (E[R^-|T=0] - E[R^-|T=1])            (conditional-mean form)

    Checking only (a) against (b) would leave a weighting defect in the
    covariance path undetectable, because both would move together. Route (c)
    reaches the same quantity through two conditional Hajek means instead.
    """
    rng = random.Random(seed)
    worst = 0.0
    checked = 0
    for _ in range(trials):
        recs = [
            AtomCausalRecord(
                document_id=f"d{rng.randint(0, 5)}",
                atom_id=f"a{i}",
                role=rng.choice(list(AtomRole)),
                pi=rng.uniform(0.05, 1.0),
                transmitted=rng.randint(0, 1),
                r_minus=float(rng.randint(0, 1)),
                d_plus=float(rng.randint(0, 1)),
            )
            for i in range(rng.randint(8, 30))
        ]
        d = decompose(recs)
        if d.selection_bias_max_discrepancy is None:
            continue
        checked += 1
        worst = max(worst, d.selection_bias_max_discrepancy)
    return CheckOutcome(
        "selection_bias_identity",
        worst < 1e-9 and checked > 0,
        f"max pairwise discrepancy across all three routes {worst:.3e} "
        f"over {checked} evaluable trials",
    )


def check_sham_sign() -> CheckOutcome:
    """s = 2T - 1; deletion and insertion take OPPOSITE offsets."""
    t1 = AtomCausalRecord("d", "a", AtomRole.NUMERIC, 0.5, 1, 0.2, 0.9)
    t0 = AtomCausalRecord("d", "b", AtomRole.NUMERIC, 0.5, 0, 0.3, 0.8)
    eps = 0.05
    ok = (
        sign_for(1) == 1
        and sign_for(0) == -1
        and abs(corrected_delta(t1, eps) - (t1.delta_avail + eps)) < 1e-12
        and abs(corrected_delta(t0, eps) - (t0.delta_avail - eps)) < 1e-12
    )
    return CheckOutcome("sham_sign_convention", ok, "s=+1 for deletion, s=-1 for insertion")


def check_knapsack_determinism(trials: int = 200, seed: int = 8) -> CheckOutcome:
    rng = random.Random(seed)
    for _ in range(trials):
        items = [
            (f"a{i}", rng.randint(1, 9), rng.uniform(-1, 1)) for i in range(rng.randint(3, 12))
        ]
        budget = rng.randint(5, 30)
        first = knapsack(items, budget)
        shuffled = items[:]
        rng.shuffle(shuffled)
        second = knapsack(shuffled, budget)
        if first.chosen != second.chosen:
            return CheckOutcome(
                "knapsack_determinism",
                False,
                f"input order changed the solution: {first.chosen} vs {second.chosen}",
            )
        if first.total_cost > budget:
            return CheckOutcome("knapsack_determinism", False, "budget exceeded")
    return CheckOutcome("knapsack_determinism", True, f"{trials} randomised instances agreed")


def check_hajek_vs_unweighted() -> CheckOutcome:
    """A weighted pooled estimate must differ from an unweighted one when the
    quantity varies across strata. If they agreed always, the weighting would be
    decorative."""
    recs = [
        AtomCausalRecord("d", "a1", AtomRole.NUMERIC, 0.1, 1, 0.0, 1.0),
        AtomCausalRecord("d", "a2", AtomRole.ENTITY, 0.9, 0, 1.0, 1.0),
    ]
    weighted = decompose(recs).r_bar_zero
    unweighted = float(np.mean([r.r_minus for r in recs]))
    return CheckOutcome(
        "hajek_differs_from_unweighted",
        abs(weighted - unweighted) > 1e-6,
        f"weighted {weighted:.4f} vs unweighted {unweighted:.4f}",
    )


CHECKS: tuple[Callable[[], CheckOutcome], ...] = (
    check_sampling_positivity,
    check_sampling_determinism,
    check_ineligible_document,
    check_decomposition_identity,
    check_selection_bias_identity,
    check_sham_sign,
    check_knapsack_determinism,
    check_hajek_vs_unweighted,
)


def run_all() -> list[CheckOutcome]:
    return [check() for check in CHECKS]


def summarise(outcomes: list[CheckOutcome]) -> str:
    lines = []
    for o in outcomes:
        lines.append(f"[{'PASS' if o.passed else 'FAIL'}] {o.name}: {o.detail}")
    failed = sum(1 for o in outcomes if not o.passed)
    lines.append(f"{len(outcomes) - failed}/{len(outcomes)} checks passed")
    return "\n".join(lines)
