"""Availability editor: deletion, insertion, invariance and sham edits."""

from __future__ import annotations

from handoff_fidelity.editing.editor import (
    InvalidEdit,
    build_counterfactual,
    delete_atom,
    insert_atom,
)
from handoff_fidelity.editing.invariance import mask_focal, non_focal_invariant
from handoff_fidelity.editing.sham import sham_deletion, sham_insertion
from handoff_fidelity.matcher.match import find_spans, is_transmitted

from ._support import FakeTokenizer, raises

MSG = "- scope: North America\n- period: FY2019\n- numeric: 6.2%"


def test_deletion_removes_the_atom():
    out = delete_atom(MSG, document_id="d", atom_id="a", canonical_value="6.2%", role="numeric")
    assert is_transmitted(out.text, canonical_value="6.2%", role="numeric") is False
    assert out.log.mechanism == "del"
    assert out.log.accepted is True


def test_deletion_removes_every_canonical_equivalent_occurrence():
    """Removing only the first occurrence would leave an atom marked
    unavailable still present in the message."""
    msg = MSG + "\n- note: restated as 6.20 % in the appendix"
    assert len(find_spans(msg, canonical_value="6.2%", role="numeric")) == 2
    out = delete_atom(msg, document_id="d", atom_id="a", canonical_value="6.2%", role="numeric")
    assert find_spans(out.text, canonical_value="6.2%", role="numeric") == []
    assert out.log.occurrences == 2


def test_deletion_preserves_non_focal_content():
    out = delete_atom(MSG, document_id="d", atom_id="a", canonical_value="6.2%", role="numeric")
    assert "North America" in out.text
    assert "FY2019" in out.text
    assert non_focal_invariant(MSG, out.text, canonical_value="6.2%", role="numeric")


def test_deletion_of_an_absent_atom_is_refused():
    with raises(InvalidEdit):
        delete_atom(MSG, document_id="d", atom_id="a", canonical_value="9.9%", role="numeric")


def test_deletion_of_an_entangled_clause_is_refused():
    msg = "- numeric: margin rose from 6.2% to 8.1%"
    with raises(InvalidEdit):
        delete_atom(msg, document_id="d", atom_id="a", canonical_value="6.2%", role="numeric")


def test_insertion_adds_the_atom_and_the_matcher_sees_it():
    """Renderer and matcher must agree. If they do not, an inserted atom would
    be scored as absent."""
    base = "- scope: North America\n- period: FY2019"
    out = insert_atom(
        base,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        rendered="- numeric: 6.2%",
    )
    assert is_transmitted(out.text, canonical_value="6.2%", role="numeric") is True
    assert out.log.mechanism == "ins"


def test_insertion_that_the_matcher_cannot_detect_is_refused():
    base = "- scope: North America"
    with raises(InvalidEdit):
        insert_atom(
            base,
            document_id="d",
            atom_id="a",
            canonical_value="6.2%",
            role="numeric",
            rendered="- numeric: about six point two",
        )


def test_insertion_of_a_present_atom_is_refused():
    with raises(InvalidEdit):
        insert_atom(
            MSG,
            document_id="d",
            atom_id="a",
            canonical_value="6.2%",
            role="numeric",
            rendered="- numeric: 6.2%",
        )


def test_insertion_overruns_the_budget_rather_than_displacing():
    """Under overrun no atom is evicted, so a negative surplus isolates
    interference and cannot be a displacement artefact."""
    base = "- scope: North America\n- period: FY2019"
    tok = FakeTokenizer()
    out = insert_atom(
        base,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        rendered="- numeric: 6.2%",
        tokenizer=tok,
        budget=tok.count(base),
    )
    assert out.log.overrun_tokens > 0
    assert "North America" in out.text and "FY2019" in out.text


def test_build_counterfactual_constructs_only_the_missing_arm():
    deleted = build_counterfactual(
        MSG,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        transmitted=1,
        rendered="- numeric: 6.2%",
    )
    assert deleted.log.mechanism == "del"
    base = "- scope: North America"
    inserted = build_counterfactual(
        base,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        transmitted=0,
        rendered="- numeric: 6.2%",
    )
    assert inserted.log.mechanism == "ins"


def test_mask_focal_replaces_all_occurrences():
    masked = mask_focal(MSG + " and 6.20 %", canonical_value="6.2%", role="numeric")
    assert "6.2%" not in masked
    assert "6.20 %" not in masked


def test_invariance_detects_a_change_to_non_focal_content():
    tampered = MSG.replace("North America", "Europe")
    assert non_focal_invariant(MSG, tampered, canonical_value="6.2%", role="numeric") is False


def test_sham_deletion_preserves_the_value():
    """The sham disturbs the message exactly as a deletion does, but removes no
    information -- so it isolates the mechanical artefact alone."""
    out = sham_deletion(
        MSG,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        equivalent_surface="6.20 %",
    )
    assert is_transmitted(out.text, canonical_value="6.2%", role="numeric") is True
    assert out.log.reason == "sham"


def test_sham_deletion_refuses_a_value_destroying_replacement():
    with raises(InvalidEdit):
        sham_deletion(
            MSG,
            document_id="d",
            atom_id="a",
            canonical_value="6.2%",
            role="numeric",
            equivalent_surface="approximately six percent",
        )


def test_sham_insertion_does_not_change_focal_availability():
    base = "- scope: North America\n- period: FY2019"
    out = sham_insertion(
        base,
        document_id="d",
        atom_id="a",
        canonical_value="6.2%",
        role="numeric",
        redundant_rendered="- scope: North America",
    )
    assert is_transmitted(out.text, canonical_value="6.2%", role="numeric") is False
    assert len(out.text) > len(base)


def test_sham_insertion_refuses_to_introduce_the_focal_atom():
    base = "- scope: North America"
    with raises(InvalidEdit):
        sham_insertion(
            base,
            document_id="d",
            atom_id="a",
            canonical_value="6.2%",
            role="numeric",
            redundant_rendered="- numeric: 6.2%",
        )


def test_deletion_with_parenthetical_punctuation_cleanup():
    msg = "direct/OEM $4,718,993 (43%); other $155,895 (1%)."
    out = delete_atom(msg, document_id="d", atom_id="a", canonical_value="43%", role="numeric")
    assert "43%" not in out.text
    assert out.text == "direct/OEM $4,718,993; other $155,895 (1%)."
    assert is_transmitted(out.text, canonical_value="43%", role="numeric") is False


def test_insertion_of_quarterly_period_and_currency_atoms():
    base = "Revenue reported for company."
    out_q = insert_atom(
        base,
        document_id="d",
        atom_id="p1",
        canonical_value="FY2025Q1",
        role="period",
        rendered="- period: FY2025Q1",
    )
    assert is_transmitted(out_q.text, canonical_value="FY2025Q1", role="period") is True

    out_c1 = insert_atom(
        base,
        document_id="d",
        atom_id="n1",
        canonical_value="$14",
        role="numeric",
        rendered="- numeric: $14",
    )
    assert is_transmitted(out_c1.text, canonical_value="$14", role="numeric") is True

    out_c2 = insert_atom(
        base,
        document_id="d",
        atom_id="n2",
        canonical_value="$127.2|million",
        role="numeric",
        rendered="- numeric: $127.2|million",
    )
    assert is_transmitted(out_c2.text, canonical_value="$127.2|million", role="numeric") is True


def test_deletion_with_quoted_atom_cleanup():
    msg = "Fiscal year ended November 3, 2024 (“fiscal year 2024”)."
    out = delete_atom(msg, document_id="d", atom_id="a", canonical_value="FY2024", role="period")
    assert is_transmitted(out.text, canonical_value="FY2024", role="period") is False
    assert "“ ”" not in out.text
