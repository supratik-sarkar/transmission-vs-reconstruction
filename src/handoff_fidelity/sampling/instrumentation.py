r"""Bounded development instrumentation.

The development split needs :math:`\Delta^{\mathrm{bu}}` labels, and instrumenting
every candidate is the single largest cost in the project: at the measured
density that is roughly :math:`100 \times 116 \times 2 \approx 23{,}200` receiver
calls, about half the projected total.

This module caps it. For each development document:

* at most ``MAX_INSTRUMENTED_CANDIDATES_PER_DOCUMENT`` candidates are instrumented;
* if there are more, exactly that many are drawn ROLE-STRATIFIED WITHOUT
  REPLACEMENT;
* the second-stage inclusion probability :math:`q_{iz} > 0` is persisted for
  every eligible candidate, not only the drawn ones, so the two-phase
  Horvitz-Thompson / Hajek estimators remain usable.

Selection may never depend on receiver outcomes or on observed
:math:`\Delta`. The signature takes atoms and a seed and nothing else, so an
outcome cannot reach it.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Atom

MAX_INSTRUMENTED_CANDIDATES_PER_DOCUMENT = 30


@dataclass(frozen=True, slots=True)
class InstrumentationPlan:
    document_id: str
    selected: tuple[str, ...]
    q: dict[str, float]
    n_eligible: int
    capped: bool

    @property
    def n_selected(self) -> int:
        return len(self.selected)

    def weight(self, atom_id: str) -> float:
        """Second-stage design weight :math:`1/q_{iz}`."""
        q = self.q[atom_id]
        if q <= 0.0:
            raise ValueError(f"q_iz must be positive; got {q} for {atom_id}")
        return 1.0 / q


class InstrumentationError(ValueError):
    pass


def plan_instrumentation(
    atoms: Sequence[Atom],
    *,
    rng: random.Random,
    cap: int = MAX_INSTRUMENTED_CANDIDATES_PER_DOCUMENT,
) -> InstrumentationPlan:
    """Role-stratified cap with persisted second-stage probabilities.

    Allocation across roles is proportional to stratum size with largest-remainder
    rounding, so the drawn set mirrors the role composition of the eligible
    inventory rather than over-representing sparse roles.
    """
    if cap <= 0:
        raise InstrumentationError("cap must be positive")
    if not atoms:
        raise InstrumentationError("no eligible candidates")

    document_ids = {a.document_id for a in atoms}
    if len(document_ids) != 1:
        raise InstrumentationError(f"expected one document, got {sorted(document_ids)}")
    document_id = document_ids.pop()

    by_role: dict[str, list[Atom]] = defaultdict(list)
    for atom in atoms:
        by_role[atom.role.value].append(atom)
    for members in by_role.values():
        members.sort(key=lambda a: a.atom_id)

    n_eligible = len(atoms)
    if n_eligible <= cap:
        # Census: every candidate is instrumented, so q = 1 exactly.
        return InstrumentationPlan(
            document_id=document_id,
            selected=tuple(sorted(a.atom_id for a in atoms)),
            q={a.atom_id: 1.0 for a in atoms},
            n_eligible=n_eligible,
            capped=False,
        )

    roles = sorted(by_role)
    exact = {r: cap * len(by_role[r]) / n_eligible for r in roles}
    alloc = {r: int(exact[r]) for r in roles}
    # Every populated role keeps at least one draw, so no role is silently lost.
    for r in roles:
        if alloc[r] == 0:
            alloc[r] = 1
    while sum(alloc.values()) > cap:
        candidates = [role for role in roles if alloc[role] > 1]
        if not candidates:
            break
        chosen = max(candidates, key=lambda role: (alloc[role] - exact[role], role))
        alloc[chosen] -= 1
    while sum(alloc.values()) < cap:
        candidates = [role for role in roles if alloc[role] < len(by_role[role])]
        if not candidates:
            break
        chosen = max(candidates, key=lambda role: (exact[role] - alloc[role], role))
        alloc[chosen] += 1

    selected: list[str] = []
    q: dict[str, float] = {}
    for r in roles:
        members = by_role[r]
        take = min(alloc[r], len(members))
        drawn = rng.sample(members, take) if take else []
        selected.extend(a.atom_id for a in drawn)
        # Uniform WOR within the stratum: q = take / |stratum|, positive for
        # EVERY eligible member, drawn or not.
        prob = take / len(members)
        if prob <= 0.0:
            raise InstrumentationError(
                f"role {r!r} received zero second-stage probability; positivity is required"
            )
        for a in members:
            q[a.atom_id] = prob

    return InstrumentationPlan(
        document_id=document_id,
        selected=tuple(sorted(selected)),
        q=q,
        n_eligible=n_eligible,
        capped=True,
    )
