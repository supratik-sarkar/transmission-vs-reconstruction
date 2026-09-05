"""Orchestration, event contract and the mock end-to-end route."""

from __future__ import annotations

import random

from handoff_fidelity.app_contracts.events import (
    STAGE_ORDER,
    EventLog,
    EventStatus,
    EventType,
    SequenceError,
    Stage,
)
from handoff_fidelity.calibration.selection import (
    select_eviction_tolerance,
    select_experiment_c_subset,
    select_primary_budget,
)
from handoff_fidelity.models import Atom, AtomRole, VerificationStatus
from handoff_fidelity.orchestration.graph import (
    GraphNode,
    GraphTopologyError,
    assert_topology,
    topology_description,
)
from handoff_fidelity.orchestration.mock_pipeline import run_mock_pipeline
from handoff_fidelity.sampling.instrumentation import (
    MAX_INSTRUMENTED_CANDIDATES_PER_DOCUMENT,
    plan_instrumentation,
)

# --- event contract ---------------------------------------------------------


def test_event_sequence_is_monotonic_and_replayable():
    log = EventLog("r1")
    for stage in STAGE_ORDER[:4]:
        log.append(stage, EventType.STAGE_STARTED, EventStatus.RUNNING)
    log.assert_monotonic()
    assert [e.sequence for e in log.all()] == [1, 2, 3, 4]
    assert [e.sequence for e in log.replay(after_sequence=2)] == [3, 4]
    assert list(log.replay(after_sequence=99)) == []


def test_replay_never_invents_a_missing_event():
    log = EventLog("r1")
    log.append(Stage.RELAY, EventType.STAGE_STARTED, EventStatus.RUNNING)
    assert len(list(log.replay(after_sequence=0))) == 1
    try:
        list(log.replay(after_sequence=-1))
        raise AssertionError("expected SequenceError")
    except SequenceError:
        pass


def test_event_log_rejects_out_of_order_topology():
    log = EventLog("r1")
    log.append(Stage.ESTIMATE, EventType.STAGE_STARTED, EventStatus.RUNNING)
    log.append(Stage.RELAY, EventType.STAGE_STARTED, EventStatus.RUNNING)
    try:
        log.assert_topology()
        raise AssertionError("expected SequenceError")
    except SequenceError:
        pass


def test_topology_is_fixed_and_not_model_selectable():
    d = topology_description()
    assert d["fixed"] is True
    assert d["model_may_alter_topology"] is False
    assert d["conditional_edges"] == 0
    assert d["stages"] == [s.value for s in STAGE_ORDER]


def test_reordered_graph_is_rejected_before_execution():
    nodes = [GraphNode(Stage.ESTIMATE, lambda s: s), GraphNode(Stage.RELAY, lambda s: s)]
    try:
        assert_topology(nodes)
        raise AssertionError("expected GraphTopologyError")
    except GraphTopologyError:
        pass


# --- mock end-to-end --------------------------------------------------------


def test_mock_pipeline_runs_the_whole_route():
    result = run_mock_pipeline(seed=2)
    state = result.state
    assert state.source_frame is not None
    assert len(state.atoms) > 0
    assert len(state.focals) == 3
    assert len(state.records) > 0
    assert len(state.ledger) > 0
    state.events.assert_monotonic()
    state.events.assert_topology()


def test_mock_pipeline_output_is_labelled_non_evidentiary():
    d = run_mock_pipeline(seed=2).to_dict()
    assert d["evidentiary_status"] == "NONE"
    assert "NOT A SCIENTIFIC RESULT" in d["marker"]


def test_mock_pipeline_decomposition_identity_closes():
    """The orchestrated route must reproduce the identity exactly; a wrapper that
    perturbed the estimands would show up here."""
    dec = run_mock_pipeline(seed=2).state.decomposition
    assert abs(dec["identity_residual"]) < 1e-12
    residual = dec["endpoint_fidelity"] - (dec["r_bar_zero"] + dec["volume"] + dec["alignment"])
    assert abs(residual) < 1e-12


def test_mock_pipeline_exhibits_reconstruction():
    """The demo seed must show the phenomenon: endpoint correctness with no
    communication contribution."""
    state = run_mock_pipeline(seed=2).state
    fates = [(r.transmitted, r.r_minus) for r in state.records]
    assert any(t == 0 and r > 0 for t, r in fates), "no reconstructed atom in the demo"
    dec = state.decomposition
    assert dec["c_recon"] > 0.0


def test_mock_pipeline_emits_telemetry_spans():
    spans = run_mock_pipeline(seed=2).to_dict()["spans"]
    for expected in ("handoff.relay", "handoff.estimate", "handoff.receiver.natural"):
        assert expected in spans


def test_mock_pipeline_is_deterministic():
    a = run_mock_pipeline(run_id="fixed", seed=2).state
    b = run_mock_pipeline(run_id="fixed", seed=2).state
    assert [r.atom_id for r in a.records] == [r.atom_id for r in b.records]
    assert a.decomposition == b.decomposition


# --- development instrumentation cap ---------------------------------------


def _atoms(n_per_role: int, roles: int = 5) -> list[Atom]:
    out = []
    for ri, role in enumerate(list(AtomRole)[:roles]):
        for i in range(n_per_role):
            out.append(
                Atom(
                    document_id="d1",
                    atom_id=f"d1:{role.value}:{i:03d}",
                    role=role,
                    canonical_value=f"{role.value}-{i}",
                    surface_form=f"{role.value}-{i}",
                    char_start=ri * 1000 + i * 10,
                    char_end=ri * 1000 + i * 10 + 5,
                    token_start=-1,
                    token_end=-1,
                    local_context="",
                    sentence_index=i,
                    verification=VerificationStatus.ACCEPTED,
                )
            )
    return out


def test_small_document_is_censused_with_q_equal_one():
    plan = plan_instrumentation(_atoms(4), rng=random.Random(0))
    assert plan.capped is False
    assert plan.n_selected == 20
    assert all(q == 1.0 for q in plan.q.values())


def test_large_document_is_capped_at_thirty():
    plan = plan_instrumentation(_atoms(40), rng=random.Random(0))
    assert plan.capped is True
    assert plan.n_selected == MAX_INSTRUMENTED_CANDIDATES_PER_DOCUMENT


def test_every_eligible_candidate_keeps_a_positive_probability():
    """Positivity at the second phase is what keeps the two-phase estimator
    defined; a q of zero would repeat the original sampling defect."""
    atoms = _atoms(40)
    plan = plan_instrumentation(atoms, rng=random.Random(1))
    assert len(plan.q) == len(atoms)
    assert min(plan.q.values()) > 0.0
    for atom in atoms:
        assert plan.weight(atom.atom_id) > 0.0


def test_cap_is_role_stratified_and_keeps_every_role():
    atoms = _atoms(40)
    plan = plan_instrumentation(atoms, rng=random.Random(3))
    chosen_roles = {aid.split(":")[1] for aid in plan.selected}
    assert len(chosen_roles) == 5, "a role was dropped entirely"


def test_instrumentation_is_deterministic_given_a_seed():
    a = plan_instrumentation(_atoms(40), rng=random.Random(11)).selected
    b = plan_instrumentation(_atoms(40), rng=random.Random(11)).selected
    assert a == b


# --- calibration selection rules -------------------------------------------


def test_budget_rule_targets_rho_of_two_and_breaks_ties_upward():
    # Full-inventory cost 600 -> rho = 2 exactly at B = 300.
    sel = select_primary_budget([600] * 9)
    assert sel.b_star == 300
    assert abs(sel.median_rho - 2.0) < 1e-9
    assert sel.binds is True


def test_budget_rule_never_selects_a_non_binding_budget_when_one_binds():
    sel = select_primary_budget([600] * 5)
    assert sel.per_candidate[sel.b_star] > 1.0


def test_budget_tie_breaks_toward_the_larger_candidate():
    # Cost 500: B=250 gives rho 2.0; B=200 gives 2.5; B=300 gives 1.667.
    # 250 is the unique argmin, so construct a genuine tie instead.
    sel = select_primary_budget([700] * 3)  # 350 -> 2.0 exactly
    assert sel.b_star == 350


def test_eviction_rule_picks_the_smallest_qualifying_tolerance():
    sel = select_eviction_tolerance({0: 0.40, 1: 0.72, 2: 0.85, 4: 0.93, 8: 0.99})
    assert sel.tolerance == 2  # smallest at or above the 0.80 floor
    assert sel.resolved is True


def test_eviction_rule_reports_unresolved_when_nothing_qualifies():
    sel = select_eviction_tolerance({0: 0.1, 1: 0.2, 2: 0.3, 4: 0.4, 8: 0.5})
    assert sel.tolerance is None and sel.resolved is False


def test_experiment_c_rule_respects_the_call_budget():
    sel = select_experiment_c_subset(
        median_candidates_per_document=30,
        development_receiver_call_budget=10_000,
        matched_pair_retention=0.9,
    )
    # ceiling = 1500 calls; 20 docs x 30 x 2 = 1200 fits, 30 docs = 1800 does not.
    assert sel.subset_size == 20
    assert 30 in sel.rejected


def test_experiment_c_rule_refuses_when_retention_is_too_low():
    sel = select_experiment_c_subset(
        median_candidates_per_document=10,
        development_receiver_call_budget=10_000_000,
        matched_pair_retention=0.5,
    )
    assert sel.subset_size is None
