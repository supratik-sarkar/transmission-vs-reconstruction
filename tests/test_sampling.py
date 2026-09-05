"""Focal sampling design: positivity, the pi formula, and eligibility."""

from __future__ import annotations

import random

from handoff_fidelity.models import AtomRole
from handoff_fidelity.sampling.design import (
    DocumentIneligible,
    all_inclusion_probabilities,
    inclusion_probability,
    is_eligible_document,
    select_focal,
    strata,
)

from ._support import atom, inventory, raises


def test_pi_formula_matches_the_specification():
    assert inclusion_probability(m_strata=5, stratum_size=4, k=3) == (3 / 5) * (1 / 4)


def test_inclusion_probabilities_sum_to_k_exactly():
    """sum_z pi_iz = sum_s n_is * (k/m)(1/n_is) = k."""
    for n_roles in (3, 4, 5):
        for per_role in (1, 2, 5):
            atoms = inventory(n_roles=n_roles, per_role=per_role)
            total = sum(all_inclusion_probabilities(atoms, k=3).values())
            assert abs(total - 3.0) < 1e-12, (n_roles, per_role, total)


def test_positivity_holds_over_randomised_inventories():
    """Every atom in the eligible inventory must have pi > 0.

    The earlier 'k most populated strata' rule gave pi = 0 off-support, which
    leaves the Hajek estimator undefined on part of the target population.
    """
    rng = random.Random(17)
    worst = 0.0
    smallest = 1.0
    for _ in range(1000):
        roles = rng.sample(list(AtomRole), rng.randint(3, 5))
        atoms = [
            atom(r, f"{r.value}-{i}", start=(ri * 50 + i))
            for ri, r in enumerate(roles)
            for i in range(rng.randint(1, 7))
        ]
        pis = all_inclusion_probabilities(atoms, k=3)
        assert len(pis) == len(atoms)
        assert min(pis.values()) > 0.0
        smallest = min(smallest, min(pis.values()))
        worst = max(worst, abs(sum(pis.values()) - 3.0))
    assert worst < 1e-12
    assert smallest > 0.0


def test_every_stratum_can_be_selected():
    """No stratum may be structurally unreachable. If a role could never be
    sampled, the target population would silently exclude it."""
    atoms = inventory(n_roles=5, per_role=1)
    seen: set[str] = set()
    for seed in range(300):
        seen.update(f.role.value for f in select_focal(atoms, rng=random.Random(seed)))
    assert seen == {r.value for r in list(AtomRole)[:5]}


def test_exactly_k_distinct_strata_are_drawn():
    atoms = inventory(n_roles=5, per_role=3)
    picks = select_focal(atoms, rng=random.Random(4))
    assert len(picks) == 3
    assert len({p.role for p in picks}) == 3


def test_selection_is_independent_of_input_order():
    atoms = inventory(n_roles=4, per_role=3)
    a = [f.atom_id for f in select_focal(atoms, rng=random.Random(9))]
    shuffled = atoms[:]
    random.Random(123).shuffle(shuffled)
    b = [f.atom_id for f in select_focal(shuffled, rng=random.Random(9))]
    assert a == b


def test_documents_with_too_few_strata_are_ineligible():
    atoms = inventory(n_roles=2, per_role=4)
    assert is_eligible_document(atoms) is False
    with raises(DocumentIneligible):
        select_focal(atoms, rng=random.Random(0))
    with raises(DocumentIneligible):
        all_inclusion_probabilities(atoms)


def test_strata_are_sorted_deterministically():
    atoms = inventory(n_roles=3, per_role=4)
    grouped = strata(atoms)
    for members in grouped.values():
        assert [m.atom_id for m in members] == sorted(m.atom_id for m in members)


def test_recorded_pi_matches_the_formula():
    atoms = inventory(n_roles=4, per_role=3)
    m = len(strata(atoms))
    for pick in select_focal(atoms, rng=random.Random(2)):
        assert abs(pick.pi - (3 / m) * (1 / pick.stratum_size)) < 1e-12
        assert pick.populated_strata == m
