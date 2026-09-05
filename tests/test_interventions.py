"""Matched skeleton, prior probe schema, budget-neutral swaps, chance levels."""

from __future__ import annotations

from handoff_fidelity.interventions.budget_neutral import (
    NoMatchedPartner,
    candidate_set,
    choose_eviction_partner,
)
from handoff_fidelity.interventions.prior_probe import (
    PRIOR_BINS,
    estimate,
    order_invariance_check,
    stratified_dose_response,
)
from handoff_fidelity.interventions.skeleton import (
    OMITTED,
    TupleIneligible,
    assert_matched,
    build_candidate_tuples,
    natural_mapping,
    render_skeleton,
    slot_structure,
)
from handoff_fidelity.models import AtomRole
from handoff_fidelity.receiver.prompt import build_prior_probe_prompt, build_receiver_prompt
from handoff_fidelity.receiver.slots import SLOT_SCHEMAS, k_effective

from ._support import atom, raises


def _tuple():
    atoms = [
        atom(AtomRole.ENTITY, "alder ridge holdings", start=0, sentence=0),
        atom(AtomRole.SCOPE, "north america", start=40, sentence=0),
        atom(AtomRole.PERIOD, "FY2019", start=70, sentence=0),
        atom(AtomRole.NUMERIC, "6.2%", start=90, sentence=0),
    ]
    return build_candidate_tuples(atoms)[0]


def test_tuples_need_three_roles_not_five():
    """Requiring all five would exclude most real sentences and silently
    redefine the population."""
    two = [atom(AtomRole.ENTITY, "e", start=0), atom(AtomRole.SCOPE, "s", start=10)]
    assert build_candidate_tuples(two) == []
    three = two + [atom(AtomRole.PERIOD, "FY2019", start=20)]
    assert len(build_candidate_tuples(three)) == 1


def test_focal_slot_is_omitted_in_both_arms():
    tup = _tuple()
    nat = render_skeleton(tup, AtomRole.NUMERIC, natural_mapping(tup))
    blocked = dict(natural_mapping(tup))
    blocked[AtomRole.ENTITY] = "brant vale systems"
    blk = render_skeleton(tup, AtomRole.NUMERIC, blocked)
    assert nat.count(OMITTED) == 1 and blk.count(OMITTED) == 1
    assert "6.2%" not in nat and "6.2%" not in blk


def test_arms_share_slot_structure():
    tup = _tuple()
    nat = render_skeleton(tup, AtomRole.PERIOD, natural_mapping(tup))
    blocked = dict(natural_mapping(tup))
    blocked[AtomRole.ENTITY] = "brant vale systems"
    blocked[AtomRole.SCOPE] = "europe"
    blk = render_skeleton(tup, AtomRole.PERIOD, blocked)
    assert slot_structure(nat) == slot_structure(blk)
    assert_matched(nat, blk)


def test_structural_drift_between_arms_is_detected():
    tup = _tuple()
    nat = render_skeleton(tup, AtomRole.PERIOD, natural_mapping(tup))
    drifted = "\n".join(nat.splitlines()[:-1])
    with raises(AssertionError):
        assert_matched(nat, drifted)


def test_only_the_value_mapping_differs():
    tup = _tuple()
    nat = render_skeleton(tup, AtomRole.NUMERIC, natural_mapping(tup))
    blocked = dict(natural_mapping(tup))
    blocked[AtomRole.SCOPE] = "europe"
    blk = render_skeleton(tup, AtomRole.NUMERIC, blocked)
    assert [line.split(":")[0] for line in nat.splitlines()] == [
        line.split(":")[0] for line in blk.splitlines()
    ]
    assert nat != blk


def test_ineligible_focal_role_is_refused():
    tup = _tuple()
    with raises(TupleIneligible):
        render_skeleton(tup, AtomRole.PROVENANCE, natural_mapping(tup))


def test_k_eff_excludes_the_natural_value():
    """The natural value is excluded from its own redraw, so reporting
    1/|support| would understate chance."""
    assert k_effective(AtomRole.PERIOD, 6) == 5
    assert k_effective(AtomRole.PERIOD, 6, natural_excluded=False) == 6
    with raises(ValueError):
        k_effective(AtomRole.PERIOD, 1)


def test_probe_prompts_are_well_defined_not_bare_role_names():
    """A prompt such as 'Numeric = ?' measures prompt ambiguity, not
    reconstruction."""
    for _role, schema in SLOT_SCHEMAS.items():
        if "{subject}" in schema.question_template or "{attribute}" in schema.question_template:
            with raises(ValueError):
                schema.render()
    prompt = build_prior_probe_prompt(
        role=AtomRole.NUMERIC, subject="the issuer", attribute="segment margin change"
    )
    assert "the issuer" in prompt and "segment margin change" in prompt


def test_one_receiver_prompt_serves_every_arm():
    """A prompt difference across arms would confound the availability
    contrast."""
    kwargs = {"role": AtomRole.NUMERIC, "subject": "the issuer", "attribute": "margin change"}
    natural = build_receiver_prompt(message="- numeric: 6.2%", **kwargs)
    counterfactual = build_receiver_prompt(message="- scope: north america", **kwargs)
    no_evidence = build_receiver_prompt(message="", **kwargs)
    marker = "Question:"
    assert (
        natural.split(marker)[1] == counterfactual.split(marker)[1] == no_evidence.split(marker)[1]
    )


def test_no_evidence_prompt_carries_the_empty_note_marker():
    prompt = build_receiver_prompt(
        message="", role=AtomRole.SCOPE, subject="the issuer", attribute="the segment"
    )
    assert "no note was provided" in prompt


def test_prior_probe_estimate_and_binning():
    est = estimate("a1", [1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    assert abs(est.p_hat - 0.2) < 1e-12
    assert est.bin_label == "low"
    assert est.binomial_se > 0
    assert estimate("a2", [1] * 10).bin_label == "high"


def test_probe_outcomes_must_be_binary():
    with raises(ValueError):
        estimate("a1", [0, 1, 2])
    with raises(ValueError):
        estimate("a1", [])


def test_dose_response_is_a_stratification_not_a_slope():
    probes = [estimate(f"a{i}", [1] * i + [0] * (10 - i)) for i in range(0, 11)]
    trend = stratified_dose_response(probes, [i / 10 for i in range(11)])
    assert trend.bins == tuple(b[2] for b in PRIOR_BINS)
    assert "binomial error" in trend.caveat


def test_order_invariance_check_reports_agreement():
    assert order_invariance_check([1, 0, 1], [1, 0, 1]) == 1.0
    assert abs(order_invariance_check([1, 0, 1], [1, 1, 1]) - 2 / 3) < 1e-12


def test_eviction_partner_is_length_matched_and_deterministic():
    focal = atom(AtomRole.NUMERIC, "6.2%", start=0)
    present = [
        (atom(AtomRole.SCOPE, "europe", start=10), 5),
        (atom(AtomRole.PERIOD, "FY2019", start=20), 4),
        (atom(AtomRole.ENTITY, "brant", start=30), 30),
    ]
    plan = choose_eviction_partner(focal=focal, focal_tokens=4, present=present)
    assert plan.evicted_atom_id.endswith("FY2019")
    assert plan.length_delta == 0
    again = choose_eviction_partner(focal=focal, focal_tokens=4, present=list(reversed(present)))
    assert again.evicted_atom_id == plan.evicted_atom_id


def test_no_matched_partner_is_an_explicit_exclusion():
    focal = atom(AtomRole.NUMERIC, "6.2%", start=0)
    present = [(atom(AtomRole.ENTITY, "brant", start=30), 40)]
    with raises(NoMatchedPartner):
        choose_eviction_partner(focal=focal, focal_tokens=4, present=present)


def test_candidate_set_reports_its_exclusions():
    atoms = [
        atom(AtomRole.NUMERIC, "6.2%", start=0),
        atom(AtomRole.SCOPE, "europe", start=10),
        atom(AtomRole.ENTITY, "brant", start=20),
    ]
    costs = {atoms[0].atom_id: 4, atoms[1].atom_id: 4, atoms[2].atom_id: 40}
    kept, dropped = candidate_set(atoms, token_costs=costs)
    assert {a.atom_id for a in kept} == {atoms[0].atom_id, atoms[1].atom_id}
    assert dropped[0][1] == "no_matched_length_partner"
