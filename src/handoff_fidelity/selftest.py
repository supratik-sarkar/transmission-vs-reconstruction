from __future__ import annotations

import random

from .estimands import decompose
from .models import Atom, AtomCausalRecord, AtomRole
from .sampling import all_inclusion_probabilities, sample_focal_atoms


def run_design_selftests() -> dict[str, str]:
    atoms: list[Atom] = []
    counts = {
        AtomRole.ENTITY: 4,
        AtomRole.SCOPE: 3,
        AtomRole.PERIOD: 5,
        AtomRole.NUMERIC: 6,
        AtomRole.PROVENANCE: 2,
    }
    for role, count in counts.items():
        for i in range(count):
            atoms.append(
                Atom(
                    document_id="doc",
                    atom_id=f"{role.value}-{i}",
                    role=role,
                    value=f"v-{i}",
                    canonical_value=f"v-{i}",
                )
            )

    pis = all_inclusion_probabilities(atoms)
    if any(p <= 0 for p in pis.values()):
        raise AssertionError("Non-positive inclusion probability")
    if abs(sum(pis.values()) - 3.0) > 1e-12:
        raise AssertionError("Inclusion probabilities do not sum to k=3")
    sample_focal_atoms(atoms, rng=random.Random(20260907))

    records = [
        AtomCausalRecord(
            document_id="d1",
            atom_id="a",
            role=AtomRole.NUMERIC,
            pi=0.5,
            transmitted=1,
            r_minus=0.0,
            d_plus=1.0,
        ),
        AtomCausalRecord(
            document_id="d1",
            atom_id="b",
            role=AtomRole.SCOPE,
            pi=0.5,
            transmitted=0,
            r_minus=1.0,
            d_plus=1.0,
        ),
    ]
    result = decompose(records)
    rhs = result.r_bar + result.volume + result.alignment
    if abs(result.endpoint_fidelity - rhs) > 1e-12:
        raise AssertionError("Decomposition identity failed")

    return {
        "sampling_positivity": "PASS",
        "sum_pi_equals_k": "PASS",
        "decomposition_identity": "PASS",
    }
