r"""Experiment C: budget-neutral targeting.

Delta^av and Delta^bu are DIFFERENT estimands:

    Delta^av_z = Y_z(1; M_-z)          - Y_z(0; M_-z)
    Delta^bu_z = Y_z(1; M_{-z \ e})    - Y_z(0; M_-z)

They differ by the evicted atom's own effect, which is zero only if removing e
does not affect recovery of z -- a condition that fails precisely under the
in-message redundancy the design documents elsewhere. A fixed-budget oracle fed
Delta^av therefore optimises the wrong objective, so Experiment C uses
Delta^bu exclusively and is gated.

G* is called the FIRST-ORDER SURPLUS BENCHMARK, not the true causal optimum:
G sums individually measured surpluses, and equality with the joint allocation
utility requires approximate additivity. The pairwise interaction diagnostic
decides whether that reading stands.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..models import BudgetNeutralRecord


@dataclass(frozen=True, slots=True)
class TargetingResult:
    g_obs: float
    g_rand: float
    g_star: float
    eta_u: float | None
    undefined_reason: str
    tie_count: int
    n_candidates: int
    cov_t_delta_budget: float


@dataclass(frozen=True, slots=True)
class KnapsackSolution:
    chosen: tuple[str, ...]
    total_cost: int
    total_utility: float
    ties_broken: int


def knapsack(items: Sequence[tuple[str, int, float]], budget: int) -> KnapsackSolution:
    """Deterministic 0/1 knapsack over integer token costs.

    Items are ``(atom_id, cost, utility)``. Negative-utility items are retained
    rather than clipped, so the oracle may legitimately exclude an atom whose
    transmission is harmful; they simply never improve the objective.

    Tie-breaking is frozen: smallest cost first, then lexicographic atom_id.
    Without a total order the solution depends on input order, which would make
    the oracle irreproducible.
    """
    if budget < 0:
        raise ValueError("budget must be non-negative")
    ordered = sorted(items, key=lambda it: (it[1], it[0]))
    n = len(ordered)
    neg_inf = float("-inf")
    dp = [[0.0] * (budget + 1) for _ in range(n + 1)]
    take = [[False] * (budget + 1) for _ in range(n + 1)]
    ties = 0
    for i in range(1, n + 1):
        _, cost, util = ordered[i - 1]
        for b in range(budget + 1):
            skip = dp[i - 1][b]
            grab = dp[i - 1][b - cost] + util if (0 <= cost <= b) else neg_inf
            if grab > skip:
                dp[i][b] = grab
                take[i][b] = True
            else:
                if grab == skip and grab != neg_inf and cost <= b:
                    ties += 1
                dp[i][b] = skip
    chosen: list[str] = []
    b = budget
    for i in range(n, 0, -1):
        if take[i][b]:
            chosen.append(ordered[i - 1][0])
            b -= ordered[i - 1][1]
    chosen.sort()
    total_cost = sum(c for aid, c, _ in ordered if aid in set(chosen))
    return KnapsackSolution(tuple(chosen), total_cost, float(dp[n][budget]), ties)


def _utility(records: Sequence[BudgetNeutralRecord], chosen: set[str]) -> float:
    return float(sum(r.value * r.delta_budget for r in records if r.atom_id in chosen))


def evaluate_targeting(
    records: Sequence[BudgetNeutralRecord],
    *,
    budget: int,
    seed: int = 0,
    random_draws: int = 512,
) -> TargetingResult:
    """G_obs, G_rand, G* and eta_U on a FULLY INSTRUMENTED candidate set.

    Sample splitting does not work here: computing G* requires Delta^bu for
    every candidate in the feasible set, which a held-out half does not supply.
    Two or three focal atoms per document are far too few to define a
    document-level knapsack.
    """
    import random as _random

    if not records:
        raise ValueError("empty candidate set")
    observed = {r.atom_id for r in records if r.transmitted == 1}
    g_obs = _utility(records, observed)

    items = [(r.atom_id, int(r.rendered_tokens), r.value * r.delta_budget) for r in records]
    sol = knapsack(items, budget)
    g_star = sol.total_utility

    rng = _random.Random(seed)
    draws: list[float] = []
    ids = sorted(r.atom_id for r in records)
    costs = {r.atom_id: int(r.rendered_tokens) for r in records}
    for _ in range(random_draws):
        shuffled = ids[:]
        rng.shuffle(shuffled)
        spent = 0
        picked: set[str] = set()
        for aid in shuffled:
            if spent + costs[aid] <= budget:
                picked.add(aid)
                spent += costs[aid]
        draws.append(_utility(records, picked))
    g_rand = float(np.mean(draws)) if draws else 0.0

    t = np.array([float(r.transmitted) for r in records])
    d = np.array([r.delta_budget for r in records])
    cov = float(np.mean(t * d) - np.mean(t) * np.mean(d))

    if g_star <= g_rand:
        return TargetingResult(
            g_obs,
            g_rand,
            g_star,
            None,
            "G* <= G_rand: eta_U is undefined and is reported as such, not imputed",
            sol.ties_broken,
            len(records),
            cov,
        )
    return TargetingResult(
        g_obs,
        g_rand,
        g_star,
        (g_obs - g_rand) / (g_star - g_rand),
        "",
        sol.ties_broken,
        len(records),
        cov,
    )


@dataclass(frozen=True, slots=True)
class InteractionDiagnostic:
    n_pairs: int
    mean_abs_interaction: float
    mean_abs_delta: float
    ratio: float
    additivity_supported: bool


def interaction_diagnostic(
    with_partner: Sequence[float],
    without_partner: Sequence[float],
    deltas: Sequence[float],
    *,
    threshold: float = 0.25,
) -> InteractionDiagnostic:
    """Delta^bu_z(with z') - Delta^bu_z(without z') on sampled pairs.

    If interactions are large relative to Delta^bu, the oracle interpretation is
    dropped entirely and only assignment-effect alignment Cov(T, Delta^bu) is
    reported.
    """
    a = np.asarray(with_partner, dtype=float)
    b = np.asarray(without_partner, dtype=float)
    d = np.asarray(deltas, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired interaction vectors must align")
    if a.size == 0:
        raise ValueError("no sampled pairs")
    inter = float(np.mean(np.abs(a - b)))
    base = float(np.mean(np.abs(d))) if d.size else 0.0
    ratio = inter / base if base > 0 else float("inf")
    return InteractionDiagnostic(int(a.size), inter, base, ratio, ratio <= threshold)
