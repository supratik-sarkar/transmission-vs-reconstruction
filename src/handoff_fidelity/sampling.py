from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence

from .models import Atom, FocalSelection


class SamplingError(ValueError):
    pass


def inclusion_probability(*, m_strata: int, stratum_size: int, k: int = 3) -> float:
    if m_strata < k:
        raise SamplingError(f"Need at least {k} populated strata; got {m_strata}.")
    if stratum_size <= 0:
        raise SamplingError("stratum_size must be positive")
    return (k / m_strata) * (1 / stratum_size)


def sample_focal_atoms(
    atoms: Sequence[Atom], *, rng: random.Random, k: int = 3
) -> list[FocalSelection]:
    by_role: dict[str, list[Atom]] = defaultdict(list)
    for atom in atoms:
        by_role[atom.role.value].append(atom)

    roles = sorted(by_role)
    m = len(roles)
    if m < k:
        raise SamplingError(f"Need >= {k} populated strata, found {m}.")

    selected_roles = rng.sample(roles, k=k)
    result: list[FocalSelection] = []
    for role in selected_roles:
        candidates = by_role[role]
        atom = rng.choice(candidates)
        result.append(
            FocalSelection(
                document_id=atom.document_id,
                atom_id=atom.atom_id,
                role=atom.role,
                pi=inclusion_probability(m_strata=m, stratum_size=len(candidates), k=k),
                stratum_size=len(candidates),
                populated_strata=m,
            )
        )
    return result


def all_inclusion_probabilities(atoms: Sequence[Atom], *, k: int = 3) -> dict[str, float]:
    by_role: dict[str, list[Atom]] = defaultdict(list)
    for atom in atoms:
        by_role[atom.role.value].append(atom)
    m = len(by_role)
    if m < k:
        raise SamplingError(f"Need >= {k} populated strata, found {m}.")
    out: dict[str, float] = {}
    for values in by_role.values():
        pi = inclusion_probability(m_strata=m, stratum_size=len(values), k=k)
        for atom in values:
            out[atom.atom_id] = pi
    return out
