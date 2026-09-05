"""CausalRelay: leakage guards, grouped CV, renderer sharing, allocation."""

from __future__ import annotations

import numpy as np

from handoff_fidelity.causalrelay.allocate import (
    TestLabelAccessError,
    allocate,
    assert_no_test_labels,
)
from handoff_fidelity.causalrelay.features import (
    FEATURE_NAMES,
    FeatureLeakError,
    assert_pretreatment,
    extract,
    schema_hash,
)
from handoff_fidelity.causalrelay.model import (
    ABLATION_FAMILY,
    LabelLeakError,
    RidgeRegressor,
    fit_policy,
    grouped_folds,
)
from handoff_fidelity.causalrelay.renderer import render_atom, render_message, rendered_token_cost
from handoff_fidelity.corpus.frame import build_source_frame
from handoff_fidelity.models import AtomRole

from ._support import FRAME_TEXT, FakeTokenizer, atom, inventory, raises


def _frame():
    return build_source_frame(
        document_id="doc1",
        raw_text=FRAME_TEXT,
        window_tokens=1000,
        tokenizer=FakeTokenizer(),
        section="full",
    )


def test_features_are_pretreatment_only():
    """Post-treatment features would make the deployed policy depend on
    quantities it cannot observe at test time."""
    assert_pretreatment(FEATURE_NAMES)
    for bad in ("mean_r_minus", "delta_label", "receiver_agreement", "transmitted_rate"):
        with raises(FeatureLeakError):
            assert_pretreatment([bad])


def test_feature_extraction_is_deterministic_and_shaped():
    frame = _frame()
    atoms = inventory(n_roles=4, per_role=2)
    a = extract(frame, atoms)
    b = extract(frame, list(reversed(atoms)))
    assert a.rows == b.rows, "feature order must not depend on input order"
    assert len(a.names) == len(a.rows[0])
    assert schema_hash() == schema_hash()


def test_fitting_on_a_test_split_is_a_hard_error():
    x = np.random.default_rng(0).normal(size=(20, 3))
    y = np.arange(20, dtype=float)
    groups = [f"d{i % 5}" for i in range(20)]
    with raises(LabelLeakError):
        fit_policy(
            x,
            y,
            groups,
            feature_names=["a", "b", "c"],
            feature_schema_hash="h",
            family=ABLATION_FAMILY,
            split_name="stage2_test",
        )


def test_grouped_folds_never_split_a_document():
    groups = [f"d{i // 4}" for i in range(40)]
    for train_idx, test_idx in grouped_folds(groups, n_splits=5):
        train_docs = {groups[i] for i in train_idx}
        test_docs = {groups[i] for i in test_idx}
        assert not (train_docs & test_docs), "a document appeared on both sides of the split"


def test_grouped_folds_cover_every_document():
    groups = [f"d{i // 3}" for i in range(30)]
    covered: set[str] = set()
    for _, test_idx in grouped_folds(groups, n_splits=5):
        covered |= {groups[i] for i in test_idx}
    assert covered == set(groups)


def test_ridge_recovers_a_linear_signal():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(200, 3))
    y = x @ np.array([1.5, -2.0, 0.5]) + 3.0
    model = RidgeRegressor(alpha=1e-8).fit(x, y)
    assert float(np.max(np.abs(model.predict(x) - y))) < 1e-6


def test_policy_fit_is_deterministic_and_carries_its_fingerprint():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(60, 3))
    y = x[:, 0] * 0.4
    groups = [f"d{i % 10}" for i in range(60)]
    kwargs = {
        "feature_names": ["a", "b", "c"],
        "feature_schema_hash": "h",
        "family": ABLATION_FAMILY,
        "split_name": "stage2_dev",
    }
    first = fit_policy(x, y, groups, **kwargs)
    second = fit_policy(x, y, groups, **kwargs)
    assert first.fingerprint() == second.fingerprint()
    assert first.n_train_documents == 10


def test_test_label_access_is_refused():
    assert_no_test_labels("stage2_dev", "delta_budget")
    assert_no_test_labels("stage2_test", "none")
    with raises(TestLabelAccessError):
        assert_no_test_labels("stage2_test", "delta_budget")


def test_renderer_is_shared_and_deterministic():
    """The uniform-atoms control uses this exact function, which is what makes
    the comparison about allocation rather than presentation."""
    a = atom(AtomRole.SCOPE, "north america")
    assert render_atom(a) == "- scope: north america"
    atoms = inventory(n_roles=3, per_role=2)
    assert render_message(atoms) == render_message(list(reversed(atoms)))


def test_renderer_orders_by_source_position_not_utility():
    atoms = [
        atom(AtomRole.NUMERIC, "second", start=50),
        atom(AtomRole.SCOPE, "first", start=10),
    ]
    lines = render_message(atoms).splitlines()
    assert "first" in lines[0] and "second" in lines[1]


def test_allocation_respects_the_hard_budget():
    tok = FakeTokenizer()
    atoms = inventory(n_roles=5, per_role=4)
    scores = [0.5] * len(atoms)
    result = allocate(atoms, scores, budget=10, tokenizer=tok)
    assert result.total_cost <= 10
    assert tok.count(result.message) <= 10


def test_allocation_prefers_higher_predicted_surplus():
    tok = FakeTokenizer()
    atoms = [atom(AtomRole.SCOPE, f"s{i}", start=i * 10) for i in range(6)]
    scores = [0.0, 0.0, 0.0, 0.0, 0.0, 9.0]
    result = allocate(atoms, scores, budget=3, tokenizer=tok)
    assert atoms[5].atom_id in result.chosen_atom_ids


def test_allocation_excludes_negative_predicted_surplus():
    tok = FakeTokenizer()
    atoms = [atom(AtomRole.SCOPE, "keep", start=0), atom(AtomRole.PERIOD, "drop", start=10)]
    result = allocate(atoms, [1.0, -1.0], budget=100, tokenizer=tok)
    assert atoms[0].atom_id in result.chosen_atom_ids
    assert atoms[1].atom_id not in result.chosen_atom_ids


def test_allocation_is_order_independent():
    tok = FakeTokenizer()
    atoms = inventory(n_roles=4, per_role=3)
    scores = [float(i % 5) for i in range(len(atoms))]
    a = allocate(atoms, scores, budget=14, tokenizer=tok)
    pairs = list(zip(atoms, scores, strict=False))[::-1]
    b = allocate([p[0] for p in pairs], [p[1] for p in pairs], budget=14, tokenizer=tok)
    assert a.chosen_atom_ids == b.chosen_atom_ids


def test_rendered_cost_includes_the_line_separator():
    tok = FakeTokenizer()
    a = atom(AtomRole.SCOPE, "x")
    assert rendered_token_cost(a, tok) == tok.count(render_atom(a) + "\n")
