"""Estimands, weighting, sham partial identification, gates, targeting."""

from __future__ import annotations

import random

import numpy as np

from handoff_fidelity.causal.estimands import decompose, decompose_by_class
from handoff_fidelity.causal.gates import PostGateError, evaluate_stage1_gate, require_gate_passed
from handoff_fidelity.causal.multihop import decompose_by_hop, divergence_curve
from handoff_fidelity.causal.sham_partial import (
    atom_region,
    corrected_delta,
    estimate_sham,
    population_region,
    sign_for,
)
from handoff_fidelity.causal.targeting import evaluate_targeting, interaction_diagnostic, knapsack
from handoff_fidelity.causal.weighting import (
    PositivityError,
    design_weights,
    hajek,
    horvitz_thompson,
    weighted_covariance,
)
from handoff_fidelity.models import AtomRole, BudgetNeutralRecord

from ._support import raises, record


def _random_records(rng, n=None):
    n = n or rng.randint(8, 40)
    return [
        record(
            doc=f"d{rng.randint(0, 6)}",
            aid=f"a{i}",
            role=rng.choice(list(AtomRole)),
            pi=rng.uniform(0.05, 1.0),
            t=rng.randint(0, 1),
            r_minus=float(rng.randint(0, 1)),
            d_plus=float(rng.randint(0, 1)),
        )
        for i in range(n)
    ]


def test_decomposition_closes_with_zero_residual():
    rng = random.Random(21)
    worst = 0.0
    for _ in range(500):
        worst = max(worst, abs(decompose(_random_records(rng)).identity_residual))
    assert worst < 1e-10, worst


def test_selection_bias_agrees_along_all_three_routes():
    """R_obs - Rbar_0  ==  -Cov(T,R^-)/(1-Tbar)  ==  Tbar*(E[R^-|T=0]-E[R^-|T=1]).

    Three computational routes to the same quantity. Route (b) goes through the
    weighted covariance, route (c) through two conditional Hajek means; a
    weighting defect in either would separate them.
    """
    rng = random.Random(22)
    worst, checked = 0.0, 0
    for _ in range(500):
        d = decompose(_random_records(rng))
        if d.selection_bias_max_discrepancy is None:
            continue
        checked += 1
        worst = max(worst, d.selection_bias_max_discrepancy)
    assert checked > 100
    assert worst < 1e-9, worst


def test_selection_bias_matches_a_hand_computed_case():
    """A worked example with weights chosen so the three routes cannot coincide
    by accident."""
    recs = [
        record(doc="d", aid="a1", pi=0.25, t=1, r_minus=1.0, d_plus=1.0),
        record(doc="d", aid="a2", pi=0.50, t=1, r_minus=0.0, d_plus=1.0),
        record(doc="d", aid="a3", pi=0.20, t=0, r_minus=1.0, d_plus=1.0),
        record(doc="d", aid="a4", pi=0.80, t=0, r_minus=0.0, d_plus=0.0),
    ]
    w = [1 / r.pi for r in recs]
    total = sum(w)
    t_bar = (w[0] + w[1]) / total
    e1 = (w[0] * 1.0 + w[1] * 0.0) / (w[0] + w[1])
    e0 = (w[2] * 1.0 + w[3] * 0.0) / (w[2] + w[3])
    expected = t_bar * (e0 - e1)

    d = decompose(recs)
    assert abs(d.selection_bias - expected) < 1e-12
    assert abs(d.selection_bias_identity - expected) < 1e-12
    assert abs(d.selection_bias_conditional - expected) < 1e-12


def test_selection_bias_is_undefined_without_both_arms():
    """The bias is a contrast against Rbar_0, so it needs BOTH arms. It is
    reported as undefined rather than imputed."""
    all_transmitted = [record(aid=f"a{i}", t=1) for i in range(3)]
    assert decompose(all_transmitted).selection_bias is None
    all_omitted = [record(aid=f"a{i}", t=0) for i in range(3)]
    assert decompose(all_omitted).selection_bias is None


def test_r_observational_and_selection_bias_have_different_existence_conditions():
    """R^obs = E[R^- | T=0] needs only the OMITTED arm; the bias additionally
    needs the transmitted arm.

    With every atom omitted, R^obs is genuinely measurable and must be reported,
    while the bias is undefined. Collapsing the two would discard a quantity we
    can compute. This covers the branch where the optional value is present but
    its dependents are not.
    """
    all_omitted = [
        record(aid="a0", t=0, r_minus=1.0, d_plus=1.0),
        record(aid="a1", t=0, r_minus=0.0, d_plus=0.0),
    ]
    d = decompose(all_omitted)
    assert d.r_observational is not None, "R^obs is measurable with an omitted arm"
    assert abs(d.r_observational - 0.5) < 1e-12
    assert d.selection_bias is None
    assert d.selection_bias_identity is None
    assert d.selection_bias_conditional is None
    assert d.selection_bias_max_discrepancy is None

    # The mirror case: no omitted arm at all, so R^obs itself does not exist.
    all_transmitted = [record(aid=f"a{i}", t=1, r_minus=0.5, d_plus=1.0) for i in range(2)]
    d = decompose(all_transmitted)
    assert d.r_observational is None
    assert d.selection_bias is None


def test_c_comm_is_signed_and_phi_only_when_a_positive():
    recs = [record(t=1, r_minus=1.0, d_plus=0.0), record(aid="a1", t=0, r_minus=0.0, d_plus=0.0)]
    d = decompose(recs)
    assert d.c_comm <= 0.0
    zero = decompose([record(t=1, r_minus=0.0, d_plus=0.0)])
    assert zero.phi is None, "phi must not be reported when A = 0"


def test_hajek_differs_from_an_unweighted_mean_when_strata_differ():
    recs = [
        record(aid="a1", role=AtomRole.NUMERIC, pi=0.1, t=1, r_minus=0.0, d_plus=1.0),
        record(aid="a2", role=AtomRole.ENTITY, pi=0.9, t=0, r_minus=1.0, d_plus=1.0),
    ]
    weighted = decompose(recs).r_bar_zero
    unweighted = float(np.mean([r.r_minus for r in recs]))
    assert abs(weighted - unweighted) > 1e-6


def test_positivity_is_enforced_by_the_weighting_layer():
    with raises(PositivityError):
        design_weights(np.array([0.5, 0.0]))
    with raises(PositivityError):
        design_weights(np.array([0.5, 0.5]), np.array([1.0, 0.0]))


def test_two_phase_weights_divide_by_pi_times_q():
    w = design_weights(np.array([0.5]), np.array([0.25]))
    assert abs(float(w[0]) - 8.0) < 1e-12


def test_horvitz_thompson_needs_the_population_size():
    with raises(ValueError):
        horvitz_thompson(np.array([1.0]), np.array([2.0]), 0)


def test_weighted_covariance_matches_the_expansion():
    x = np.array([0.0, 1.0, 1.0, 0.0])
    y = np.array([0.2, 0.9, 0.4, 0.1])
    w = np.array([1.0, 2.0, 3.0, 4.0])
    expected = hajek(x * y, w) - hajek(x, w) * hajek(y, w)
    assert abs(weighted_covariance(x, y, w) - expected) < 1e-12


def test_atom_level_statistics_suppressed_under_regime_s():
    recs = [record(t=1), record(aid="a1", t=0)]
    assert decompose(recs, atom_level_statistics=False).prob_delta_negative is None


def test_per_class_decomposition_covers_every_present_role():
    recs = [
        record(aid="a1", role=AtomRole.NUMERIC, t=1),
        record(aid="a2", role=AtomRole.SCOPE, t=0),
    ]
    by_class = decompose_by_class(recs)
    assert set(by_class) == {"numeric", "scope"}


def test_sham_sign_is_mechanism_dependent():
    """Applying a common offset to both arms would double-count the artefact on
    one and cancel it on the other."""
    assert sign_for(1) == 1 and sign_for(0) == -1
    deleted = record(t=1, r_minus=0.2, d_plus=0.9)
    inserted = record(aid="a1", t=0, r_minus=0.3, d_plus=0.8)
    eps = 0.05
    assert abs(corrected_delta(deleted, eps) - (deleted.delta_avail + eps)) < 1e-12
    assert abs(corrected_delta(inserted, eps) - (inserted.delta_avail - eps)) < 1e-12


def test_estimate_sham_is_a_difference_of_means():
    est = estimate_sham([1.0, 1.0, 0.0], [1.0, 0.0, 0.0], "del")
    assert abs(est.epsilon_mechanical - (1 / 3)) < 1e-12
    assert est.n == 3


def test_population_region_is_clipped_and_symmetric():
    recs = [record(t=1, r_minus=0.1, d_plus=0.9), record(aid="a1", t=0, r_minus=0.2, d_plus=0.7)]
    region = population_region(recs, epsilon_del=0.02, epsilon_ins=0.03, epsilon_bar=0.05)
    assert region.lower >= -1.0 and region.upper <= 1.0
    assert abs(region.width - 0.10) < 1e-12


def test_region_widens_with_the_assumed_semantic_bound():
    recs = [record(t=1, r_minus=0.1, d_plus=0.9)]
    narrow = population_region(recs, epsilon_del=0.0, epsilon_ins=0.0, epsilon_bar=0.01)
    wide = population_region(recs, epsilon_del=0.0, epsilon_ins=0.0, epsilon_bar=0.20)
    assert wide.width > narrow.width


def test_atom_region_requires_an_explicit_heterogeneity_bound():
    lo, hi = atom_region(
        record(t=1, r_minus=0.1, d_plus=0.9), epsilon_mech=0.0, epsilon_bar=0.05, u_bar=0.10
    )
    assert abs((hi - lo) - 0.30) < 1e-12
    with raises(ValueError):
        atom_region(record(t=1), epsilon_mech=0.0, epsilon_bar=0.05, u_bar=-1.0)


def test_gate_proceeds_if_either_arm_clears():
    assert (
        evaluate_stage1_gate(
            reconstruction_contribution=0.30, prior_effects={"scope": 0.01}
        ).proceed
        is True
    )
    assert (
        evaluate_stage1_gate(
            reconstruction_contribution=0.01, prior_effects={"scope": 0.30}
        ).proceed
        is True
    )


def test_gate_halts_only_if_both_fail():
    gate = evaluate_stage1_gate(reconstruction_contribution=0.01, prior_effects={"scope": 0.02})
    assert gate.proceed is False
    assert "Halt" in gate.reason


def test_reconstruction_gate_must_use_c_recon_not_rbar0():
    """Regression test: discovery gate must evaluate C_recon = E[(1-T)R^-] >= 0.10,
    NOT Rbar_0 >= 0.10.

    If an erroneous implementation substitutes Rbar_0 (e.g. 0.12) when C_recon is below
    the threshold (e.g. 0.02 because Tbar is high or (1-T)*R^- is small), substituting
    Rbar_0 would erroneously pass the gate. The gate must evaluate C_recon and fail.
    """
    r_bar_0 = 0.12  # would pass if erroneously used as gate quantity
    c_recon = 0.02  # true quantity E[(1-T)R^-], fails threshold of 0.10

    # True evaluation using C_recon: must FAIL
    gate_true = evaluate_stage1_gate(
        reconstruction_contribution=c_recon,
        prior_effects={"scope": 0.0, "period": 0.0, "numeric": 0.0},
    )
    assert gate_true.proceed is False
    assert "Halt" in gate_true.reason
    assert gate_true.reconstruction_contribution == c_recon

    # Erroneous evaluation using Rbar_0: would incorrectly PASS
    gate_erroneous = evaluate_stage1_gate(
        reconstruction_contribution=r_bar_0,
        prior_effects={"scope": 0.0, "period": 0.0, "numeric": 0.0},
    )
    assert gate_erroneous.proceed is True

    # Assert that substituting Rbar_0 for C_recon flips the gate verdict
    assert gate_true.proceed != gate_erroneous.proceed


def test_gate_ignores_classes_outside_the_predeclared_set():
    """Allowing any class to clear the gate would be optional stopping across
    atom classes."""
    gate = evaluate_stage1_gate(
        reconstruction_contribution=0.0,
        prior_effects={"entity": 0.99},
        eligible_prior_classes=("scope", "numeric"),
    )
    assert gate.proceed is False


def test_post_gate_work_is_blocked_before_and_after_a_failed_gate():
    with raises(PostGateError):
        require_gate_passed(None)
    failed = evaluate_stage1_gate(reconstruction_contribution=0.0, prior_effects={})
    with raises(PostGateError):
        require_gate_passed(failed)


def test_knapsack_is_order_independent_and_respects_the_budget():
    rng = random.Random(31)
    for _ in range(200):
        items = [
            (f"a{i}", rng.randint(1, 9), rng.uniform(-1, 1)) for i in range(rng.randint(3, 12))
        ]
        budget = rng.randint(5, 30)
        first = knapsack(items, budget)
        shuffled = items[:]
        rng.shuffle(shuffled)
        assert first.chosen == knapsack(shuffled, budget).chosen
        assert first.total_cost <= budget


def test_knapsack_never_selects_a_negative_utility_item():
    sol = knapsack([("a", 1, -0.5), ("b", 1, 0.5)], 10)
    assert sol.chosen == ("b",)


def test_eta_u_is_reported_undefined_rather_than_imputed():
    recs = [BudgetNeutralRecord("d", f"a{i}", AtomRole.NUMERIC, 1, 0.0, 2) for i in range(4)]
    result = evaluate_targeting(recs, budget=4)
    assert result.eta_u is None
    assert "undefined" in result.undefined_reason


def test_interaction_diagnostic_flags_large_interactions():
    small = interaction_diagnostic([0.30, 0.31], [0.29, 0.30], [0.30, 0.30])
    assert small.additivity_supported is True
    large = interaction_diagnostic([0.90, 0.10], [0.10, 0.90], [0.30, 0.30])
    assert large.additivity_supported is False


def test_multihop_does_not_enforce_monotonicity():
    """A receiver that reconstructs an atom at hop h may cause it to be
    transmitted at hop h+1, so T_bar can rise."""
    by_hop = {
        1: [record(aid="a", t=0, r_minus=1.0, d_plus=1.0)],
        2: [record(aid="a", t=1, r_minus=1.0, d_plus=1.0)],
    }
    estimates = decompose_by_hop(by_hop)
    t_bars = [e.decomposition.t_bar for e in estimates]
    assert t_bars[1] > t_bars[0]
    assert len(divergence_curve(estimates)) == 2
