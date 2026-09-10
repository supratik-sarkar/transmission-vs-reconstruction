"""Unit tests for the fail-closed manuscript operational language sanitizer."""

import pytest

from handoff_fidelity.presentation.sanitizer import (
    sanitize_file,
    sanitize_text,
)


def test_clean_scientific_text_passes():
    """Negative fixture: Neutral scientific language must pass cleanly."""
    clean_text = """
    We evaluate communicative surplus C_comm and downstream accuracy A across
    the model-selection evaluation set. In this discovery experiment, we observe
    that availability value is strictly positive while reconstruction fidelity R_0
    remains bounded. The model-selection split contains 100 documents.
    """
    res = sanitize_text(clean_text)
    assert res.ok is True
    assert len(res.violations) == 0


@pytest.mark.parametrize(
    "forbidden_term",
    [
        "free api",
        "free tier",
        "free-tier",
        "zero-dollar",
        "zero dollar",
        "professor review",
        "professor-review",
        "preview",
        "billed cost",
        "api spend",
        "spend ceiling",
        "quota exhaustion",
        "provider preflight",
        "full_experiment_execution_authorized",
        "implementation gate",
        "master forward controller",
        "prompt bank",
        "".join(["anti", "gravity"]),
        "".join(["cl", "aude"]),
        "stage ledger",
        "prof_review_preview",
        "stage2_dev",
        "stage2_test",
    ],
)
def test_forbidden_terms_detected(forbidden_term: str):
    """Positive fixture: Every forbidden term must be caught case-insensitively."""
    dirty_text = f"This paragraph discusses {forbidden_term.upper()} in the experimental setup."
    res = sanitize_text(dirty_text)
    assert res.ok is False
    assert any(
        v.matched_term == forbidden_term
        or v.matched_term in forbidden_term
        or forbidden_term in v.matched_term
        for v in res.violations
    )


@pytest.mark.parametrize(
    "stage_id", ["S00", "S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11"]
)
def test_forbidden_stage_ids_detected(stage_id: str):
    """Positive fixture: Internal pipeline stage IDs S00-S11 must be rejected."""
    dirty_text = f"Results from {stage_id} pipeline execution."
    res = sanitize_text(dirty_text)
    assert res.ok is False
    assert any(v.matched_term == stage_id for v in res.violations)


def test_svg_text_sanitization(tmp_path):
    """Verify SVG text elements are scanned."""
    svg_clean = tmp_path / "clean.svg"
    svg_clean.write_text(
        """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <text x="10" y="20" font-size="10pt">Communicative Surplus</text>
        </svg>"""
    )
    assert sanitize_file(svg_clean).ok is True

    svg_dirty = tmp_path / "dirty.svg"
    svg_dirty.write_text(
        """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <text x="10" y="20" font-size="10pt">Preview Evaluation</text>
        </svg>"""
    )
    res = sanitize_file(svg_dirty)
    assert res.ok is False
    assert any("preview" in v.matched_term for v in res.violations)
