"""Figure quality and presentation standard validator.

Enforces:
1. Vector formats (.pdf and .svg exist and are non-empty).
2. Legibility floor (font-size >= 6.0pt / 8px).
3. Sanitizer compliance (zero forbidden operational terms in SVG visible text).
4. XML well-formedness.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .sanitizer import sanitize_file


@dataclass(slots=True)
class FigureValidationResult:
    ok: bool
    figure_id: str
    pdf_path: str
    svg_path: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"{status}: figure quality audit for {self.figure_id}"]
        lines.append(f"  PDF: {self.pdf_path}")
        lines.append(f"  SVG: {self.svg_path}")
        for f in self.failures:
            lines.append(f"  FAIL: {f}")
        for w in self.warnings:
            lines.append(f"  WARN: {w}")
        return "\n".join(lines)


def _extract_font_sizes(svg_text: str) -> list[float]:
    """Extract font sizes in points from attributes and inline CSS."""
    sizes: list[float] = []

    # Attribute font-size="..."
    for match in re.finditer(r'font-size\s*=\s*["\']([^"\']+)["\']', svg_text, re.IGNORECASE):
        val_str = match.group(1).strip()
        num_m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(pt|px)?$", val_str)
        if num_m:
            val = float(num_m.group(1))
            unit = num_m.group(2)
            if unit == "px":
                val = val * 0.75  # 1px ~= 0.75pt
            sizes.append(val)

    # Inline style="...font-size: 10pt;..."
    for match in re.finditer(
        r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)(pt|px)?", svg_text, re.IGNORECASE
    ):
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "px":
            val = val * 0.75
        sizes.append(val)

    return sizes


def validate_figure(
    pdf_path: Path | str,
    svg_path: Path | str,
    min_font_size_pt: float = 6.0,
) -> FigureValidationResult:
    """Validate a single figure pair (.pdf and .svg)."""
    p_pdf = Path(pdf_path)
    p_svg = Path(svg_path)
    fig_id = p_pdf.stem
    res = FigureValidationResult(
        ok=True, figure_id=fig_id, pdf_path=str(p_pdf), svg_path=str(p_svg)
    )

    # 1. Vector existence and non-empty
    if not p_pdf.is_file() or p_pdf.stat().st_size == 0:
        res.failures.append(f"PDF vector artifact missing or empty: {p_pdf}")
    if not p_svg.is_file() or p_svg.stat().st_size == 0:
        res.failures.append(f"SVG vector artifact missing or empty: {p_svg}")

    if not res.failures and p_svg.is_file():
        svg_content = p_svg.read_text(encoding="utf-8", errors="replace")

        # 2. XML well-formedness
        try:
            root = ET.fromstring(svg_content)
            viewbox = root.attrib.get("viewBox")
            width = root.attrib.get("width")
            height = root.attrib.get("height")
            if not viewbox and not (width and height):
                res.warnings.append("SVG lacks both viewBox and explicit width/height dimensions")
        except ET.ParseError as e:
            res.failures.append(f"SVG is not well-formed XML: {e}")

        # 3. Legibility floor
        font_sizes = _extract_font_sizes(svg_content)
        small_sizes = [s for s in font_sizes if s < min_font_size_pt]
        if small_sizes:
            res.failures.append(
                f"SVG contains font sizes below legibility floor ({min_font_size_pt}pt): "
                f"min observed {min(small_sizes):.1f}pt"
            )

        # 4. Sanitizer check
        san_res = sanitize_file(p_svg)
        if not san_res.ok:
            for v in san_res.violations:
                res.failures.append(
                    f"Operational language violation in SVG text: matched {v.matched_term!r} on line {v.line_number}"
                )

    res.ok = len(res.failures) == 0
    return res


def validate_figures_directory(
    figures_dir: Path | str,
    min_font_size_pt: float = 6.0,
) -> dict[str, FigureValidationResult]:
    """Validate all figure pairs in a directory."""
    d = Path(figures_dir)
    results: dict[str, FigureValidationResult] = {}

    # Find all pdf files
    for pdf in sorted(d.glob("*.pdf")):
        svg = pdf.with_suffix(".svg")
        res = validate_figure(pdf, svg, min_font_size_pt=min_font_size_pt)
        results[pdf.stem] = res

    return results
