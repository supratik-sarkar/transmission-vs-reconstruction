import random

import pytest

from handoff_fidelity.models import Atom, AtomRole
from handoff_fidelity.sampling import all_inclusion_probabilities, sample_focal_atoms


def _atoms() -> list[Atom]:
    out = []
    for role, n in {
        AtomRole.ENTITY: 2,
        AtomRole.SCOPE: 3,
        AtomRole.PERIOD: 4,
        AtomRole.NUMERIC: 5,
        AtomRole.PROVENANCE: 6,
    }.items():
        for i in range(n):
            out.append(
                Atom(
                    document_id="d",
                    atom_id=f"{role.value}-{i}",
                    role=role,
                    value=str(i),
                    canonical_value=str(i),
                )
            )
    return out


def test_positive_pi_and_sum_k() -> None:
    pis = all_inclusion_probabilities(_atoms(), k=3)
    assert min(pis.values()) > 0
    assert sum(pis.values()) == pytest.approx(3.0)


def test_sample_has_three_distinct_roles() -> None:
    sample = sample_focal_atoms(_atoms(), rng=random.Random(7), k=3)
    assert len(sample) == 3
    assert len({x.role for x in sample}) == 3
