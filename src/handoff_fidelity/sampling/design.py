"""Fixed-size role-stratified focal sampling.

Design (frozen):

    for a document with m_i populated eligible strata (m_i >= k):
        choose k = 3 strata uniformly WITHOUT replacement from ALL populated strata
        choose one atom uniformly within each selected stratum

    pi_iz = (k / m_i) * (1 / n_is)

Positivity is the point. An earlier design that took "the k most populated
strata" gave pi = 0 off-support, which does not merely violate the positivity
assumption -- it leaves the Hajek estimator undefined on part of the target
population. Under the design above,

    sum_z pi_iz = sum_s n_is * (k / m_i) * (1 / n_is) = m_i * (k / m_i) = k

exactly, which the test suite verifies over randomised inventories.

Sampling happens BEFORE the relay runs and the focal identities are never shown
to any compressor.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence

from ..models import Atom, FocalSelection

K_FOCAL = 3


class SamplingError(ValueError):
    pass


class DocumentIneligible(SamplingError):
    """Fewer than k populated eligible strata: this document cannot support the
    design and is excluded before the relay runs."""


def strata(atoms: Sequence[Atom]) -> dict[str, list[Atom]]:
    by_role: dict[str, list[Atom]] = defaultdict(list)
    for atom in atoms:
        by_role[atom.role.value].append(atom)
    # Deterministic order inside each stratum, independent of input order.
    return {role: sorted(members, key=lambda a: a.atom_id) for role, members in by_role.items()}


def inclusion_probability(*, m_strata: int, stratum_size: int, k: int = K_FOCAL) -> float:
    if m_strata < k:
        raise DocumentIneligible(f"need at least {k} populated strata, got {m_strata}")
    if stratum_size <= 0:
        raise SamplingError("stratum_size must be positive")
    return (k / m_strata) * (1.0 / stratum_size)


def all_inclusion_probabilities(atoms: Sequence[Atom], *, k: int = K_FOCAL) -> dict[str, float]:
    """pi for EVERY atom in the document's eligible inventory, not only the
    sampled ones. Required for the Horvitz-Thompson/Hajek denominators."""
    by_role = strata(atoms)
    m = len(by_role)
    out: dict[str, float] = {}
    for members in by_role.values():
        pi = inclusion_probability(m_strata=m, stratum_size=len(members), k=k)
        for atom in members:
            out[atom.atom_id] = pi
    return out


def is_eligible_document(atoms: Sequence[Atom], *, k: int = K_FOCAL) -> bool:
    return len(strata(atoms)) >= k


def select_focal(
    atoms: Sequence[Atom], *, rng: random.Random, k: int = K_FOCAL
) -> list[FocalSelection]:
    by_role = strata(atoms)
    m = len(by_role)
    if m < k:
        raise DocumentIneligible(
            f"document has {m} populated eligible strata; the design requires at least {k}"
        )
    role_names = sorted(by_role)
    chosen_roles = sorted(rng.sample(role_names, k))
    out: list[FocalSelection] = []
    for role in chosen_roles:
        members = by_role[role]
        atom = members[rng.randrange(len(members))]
        out.append(
            FocalSelection(
                document_id=atom.document_id,
                atom_id=atom.atom_id,
                role=atom.role,
                pi=inclusion_probability(m_strata=m, stratum_size=len(members), k=k),
                stratum_size=len(members),
                populated_strata=m,
                k=k,
            )
        )
    return out
