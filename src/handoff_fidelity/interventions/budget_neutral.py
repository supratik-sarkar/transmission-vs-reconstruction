"""Experiment C interventions: matched-length insert/evict swaps.

Inserting an atom at a FIXED budget requires evicting something else, so the
effect measured is Delta^bu, not Delta^av. Availability overrun (Experiment A)
and budget-neutral displacement (Experiment C) answer different questions and
are never mixed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Atom

LENGTH_TOLERANCE_TOKENS = 2


class NoMatchedPartner(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SwapPlan:
    inserted_atom_id: str
    evicted_atom_id: str
    inserted_tokens: int
    evicted_tokens: int

    @property
    def length_delta(self) -> int:
        return self.inserted_tokens - self.evicted_tokens


def choose_eviction_partner(
    *,
    focal: Atom,
    focal_tokens: int,
    present: Sequence[tuple[Atom, int]],
    tolerance: int = LENGTH_TOLERANCE_TOKENS,
) -> SwapPlan:
    """Pick the evicted atom deterministically.

    Selection rule (frozen): smallest absolute token-length difference, ties
    broken by lexicographic atom_id. A partner from the same role as the focal
    atom is avoided where possible, because evicting a same-role atom
    confounds the swap with a role-composition change.
    """
    candidates = [
        (abs(tokens - focal_tokens), atom.role is focal.role, atom.atom_id, atom, tokens)
        for atom, tokens in present
        if atom.atom_id != focal.atom_id
    ]
    feasible = [c for c in candidates if c[0] <= tolerance]
    if not feasible:
        raise NoMatchedPartner(
            f"no atom within {tolerance} tokens of {focal.atom_id}; the atom is "
            "ineligible for the budget-neutral swap and the rate is reported"
        )
    feasible.sort(key=lambda c: (c[0], c[1], c[2]))
    _, _, _, partner, partner_tokens = feasible[0]
    return SwapPlan(focal.atom_id, partner.atom_id, focal_tokens, partner_tokens)


def candidate_set(
    atoms: Sequence[Atom],
    *,
    token_costs: dict[str, int],
    tolerance: int = LENGTH_TOLERANCE_TOKENS,
) -> tuple[tuple[Atom, ...], tuple[tuple[Atom, str], ...]]:
    """Enumerate the Experiment-C candidate set C_i.

    An atom qualifies when it (a) passed the atomizer and eligibility filter,
    (b) admits a matched-length counterpart for eviction, and (c) can be
    rendered. Condition (c) is checked by the caller after rendering.

    Delta^bu is then measured for EVERY member, not a sample of it: computing
    G* requires the whole feasible set.
    """
    present = [(a, token_costs.get(a.atom_id, 0)) for a in atoms]
    kept: list[Atom] = []
    dropped: list[tuple[Atom, str]] = []
    for atom in atoms:
        try:
            choose_eviction_partner(
                focal=atom,
                focal_tokens=token_costs.get(atom.atom_id, 0),
                present=present,
                tolerance=tolerance,
            )
        except NoMatchedPartner:
            dropped.append((atom, "no_matched_length_partner"))
        else:
            kept.append(atom)
    return tuple(kept), tuple(dropped)
