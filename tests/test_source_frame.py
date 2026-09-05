"""Source-frame construction and inventory equivalence."""

from __future__ import annotations

from dataclasses import replace

from handoff_fidelity.corpus.frame import (
    FrameEquivalenceError,
    assert_inventory_within_frame,
    build_source_frame,
    sha256_text,
)
from handoff_fidelity.corpus.normalize import normalize_text, split_sentences
from handoff_fidelity.corpus.sections import SectionNotFound, extract_mdna

from ._support import FRAME_TEXT, FakeTokenizer, raises


def _frame():
    return build_source_frame(
        document_id="doc1",
        raw_text=FRAME_TEXT,
        window_tokens=1000,
        tokenizer=FakeTokenizer(),
        section="full",
    )


def test_frame_hash_is_over_exact_windowed_text():
    frame = _frame()
    assert frame.sha256 == sha256_text(frame.text)


def test_frame_truncation_is_recorded():
    frame = build_source_frame(
        document_id="doc1",
        raw_text=FRAME_TEXT,
        window_tokens=5,
        tokenizer=FakeTokenizer(),
        section="full",
    )
    assert frame.truncated is True
    assert frame.token_count <= 5


def test_normalisation_is_idempotent():
    once = normalize_text(FRAME_TEXT)
    assert normalize_text(once) == once


def test_sentence_spans_cover_text_without_overlap():
    spans = split_sentences(FRAME_TEXT)
    assert spans
    for (a, b), (c, _) in zip(spans, spans[1:], strict=False):
        assert a < b <= c


def test_inventory_must_lie_inside_the_frame():
    """An atom outside the relay-visible frame would be scored as a transmission
    failure for content the compressor never saw."""
    from handoff_fidelity.atomizer.rules import atomize

    frame = _frame()
    atoms = atomize(frame.document_id, frame.text)
    assert atoms
    assert_inventory_within_frame(frame, atoms)

    bad = replace(atoms[0], char_start=len(frame.text) + 5, char_end=len(frame.text) + 9)
    with raises(FrameEquivalenceError):
        assert_inventory_within_frame(frame, [bad])


def test_surface_form_must_match_the_frame_at_its_span():
    from handoff_fidelity.atomizer.rules import atomize

    frame = _frame()
    atoms = atomize(frame.document_id, frame.text)
    tampered = replace(atoms[0], surface_form="something else entirely")
    with raises(FrameEquivalenceError):
        assert_inventory_within_frame(frame, [tampered])


def test_missing_section_fails_closed():
    with raises(SectionNotFound):
        extract_mdna("a document with no management discussion heading at all")


def test_atomizer_finds_each_tier1_role():
    from handoff_fidelity.atomizer.rules import atomize
    from handoff_fidelity.models import AtomRole

    atoms = atomize("doc1", normalize_text(FRAME_TEXT))
    found = {a.role for a in atoms}
    for role in (
        AtomRole.ENTITY,
        AtomRole.SCOPE,
        AtomRole.PERIOD,
        AtomRole.NUMERIC,
        AtomRole.PROVENANCE,
    ):
        assert role in found, f"{role.value} not extracted"


def test_atomizer_is_deterministic():
    from handoff_fidelity.atomizer.rules import atomize

    text = normalize_text(FRAME_TEXT)
    a = [x.atom_id for x in atomize("doc1", text)]
    b = [x.atom_id for x in atomize("doc1", text)]
    assert a == b
