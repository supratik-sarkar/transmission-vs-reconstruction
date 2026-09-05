"""Budget allocation for CausalRelay.

    u_hat_z = max(0, s_hat_z)          predicted utility
    maximise sum_z u_hat_z  subject to  sum_z cost_z <= B

Clipping at zero is deliberate at ALLOCATION time: an atom with predicted
negative surplus should simply not be selected, and admitting negative values
into the objective would let the solver "gain" by excluding them, which is the
same decision expressed less clearly. Note this differs from the Experiment-C
ORACLE, which retains negative surpluses in G so that an oracle may
legitimately exclude a harmful atom.

No test outcome, intervention or oracle label may influence allocation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..causal.targeting import knapsack
from ..models import Atom
from .renderer import render_message, rendered_token_cost


class TestLabelAccessError(AssertionError):
    __test__ = False


@dataclass(frozen=True, slots=True)
class Allocation:
    chosen_atom_ids: tuple[str, ...]
    message: str
    total_cost: int
    predicted_utility: float
    budget: int
    ties_broken: int


def predicted_utility(scores: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, np.asarray(scores, dtype=float))


def allocate(
    atoms: Sequence[Atom],
    scores: Sequence[float],
    *,
    budget: int,
    tokenizer,
    header: str | None = None,
) -> Allocation:
    if len(atoms) != len(scores):
        raise ValueError("atoms and scores must align")
    ordered = sorted(atoms, key=lambda a: a.atom_id)
    score_by_id = {a.atom_id: float(s) for a, s in zip(atoms, scores, strict=False)}
    utilities = predicted_utility(np.array([score_by_id[a.atom_id] for a in ordered]))
    costs = {a.atom_id: rendered_token_cost(a, tokenizer) for a in ordered}

    items = [
        (a.atom_id, costs[a.atom_id], float(u)) for a, u in zip(ordered, utilities, strict=False)
    ]
    sol = knapsack(items, budget)
    chosen = set(sol.chosen)
    selected = [a for a in ordered if a.atom_id in chosen]
    message = render_message(selected, header=header)

    realised = tokenizer.count(message)
    if realised > budget:
        # The knapsack budgets per-atom rendered cost; the joined message can
        # differ by separator accounting, so the HARD ceiling is re-checked on
        # the realised string. Trim by ascending predicted utility, which is a
        # total order once ties fall back to atom_id.
        remaining = sorted(selected, key=lambda a: (score_by_id[a.atom_id], a.atom_id))
        while remaining and tokenizer.count(render_message(remaining, header=header)) > budget:
            remaining.pop(0)
        selected = sorted(remaining, key=lambda a: a.atom_id)
        message = render_message(selected, header=header)
        realised = tokenizer.count(message)
        chosen = {a.atom_id for a in selected}

    return Allocation(
        tuple(sorted(a.atom_id for a in selected)),
        message,
        realised,
        float(sum(u for a, u in zip(ordered, utilities, strict=False) if a.atom_id in chosen)),
        budget,
        sol.ties_broken,
    )


def assert_no_test_labels(split_name: str, label_source: str) -> None:
    """Guard invoked wherever a label could reach the deployed policy."""
    if "test" in split_name and "dev" not in split_name and label_source != "none":
        raise TestLabelAccessError(
            f"CausalRelay attempted to read labels from split {split_name!r} "
            f"(source {label_source!r}); test-time policy must see no test outcome"
        )
