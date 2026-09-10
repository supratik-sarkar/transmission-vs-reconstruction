"""Unit tests for figure quality validator."""

from handoff_fidelity.presentation.figure_validator import validate_figure


def test_valid_figure_pair_passes(tmp_path):
    pdf = tmp_path / "fig1.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf content")
    svg = tmp_path / "fig1.svg"
    svg.write_text(
        """<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
            <text x="10" y="20" font-size="9pt">Main Effect</text>
        </svg>"""
    )
    res = validate_figure(pdf, svg)
    assert res.ok is True
    assert len(res.failures) == 0


def test_missing_svg_fails(tmp_path):
    pdf = tmp_path / "fig1.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    svg = tmp_path / "fig1.svg"
    res = validate_figure(pdf, svg)
    assert res.ok is False
    assert any("missing" in f for f in res.failures)


def test_tiny_font_size_fails(tmp_path):
    pdf = tmp_path / "fig1.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    svg = tmp_path / "fig1.svg"
    svg.write_text(
        """<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
            <text x="10" y="20" font-size="4pt">Illegible Label</text>
        </svg>"""
    )
    res = validate_figure(pdf, svg, min_font_size_pt=6.0)
    assert res.ok is False
    assert any("legibility floor" in f for f in res.failures)


def test_sanitizer_violation_in_figure_fails(tmp_path):
    pdf = tmp_path / "fig1.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    svg = tmp_path / "fig1.svg"
    svg.write_text(
        """<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
            <text x="10" y="20" font-size="9pt">Professor Review Benchmark</text>
        </svg>"""
    )
    res = validate_figure(pdf, svg)
    assert res.ok is False
    assert any("Operational language" in f for f in res.failures)
