"""Fail-closed manuscript and presentation operational language sanitizer.

Ensures no manuscript-facing output (TeX, tables, macros, SVG text, captions)
leaks internal project, operational, accounting, or billing terminology.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

FORBIDDEN_TERMS: tuple[str, ...] = (
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
    "prof_review_",
    "preview_",
    "stage2_dev",
    "stage2_test",
)

FORBIDDEN_STAGE_REGEX = re.compile(r"\bS(?:0[0-9]|1[01])\b")


class SanitizationError(ValueError):
    """Raised when operational language is detected in manuscript-facing content."""


@dataclass(frozen=True, slots=True)
class SanitizationViolation:
    file_path: str
    line_number: int
    matched_term: str
    line_snippet: str


@dataclass(slots=True)
class SanitizationResult:
    ok: bool
    violations: list[SanitizationViolation] = field(default_factory=list)
    scanned_items: int = 0
    scanned_bytes: int = 0

    def report(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [
            f"{status}: manuscript operational language sanitization ({self.scanned_items} items scanned)"
        ]
        for v in self.violations:
            lines.append(
                f"  [{v.file_path}:{v.line_number}] matched {v.matched_term!r} -> {v.line_snippet.strip()}"
            )
        return "\n".join(lines)


def sanitize_text(text: str, filename: str = "<text>") -> SanitizationResult:
    """Scan text line-by-line against forbidden operational terms and stage IDs."""
    violations: list[SanitizationViolation] = []
    lines = text.splitlines()

    for line_idx, line in enumerate(lines, 1):
        lowered = line.casefold()

        # Check literal forbidden phrases
        for term in FORBIDDEN_TERMS:
            if term in lowered:
                violations.append(
                    SanitizationViolation(
                        file_path=filename,
                        line_number=line_idx,
                        matched_term=term,
                        line_snippet=line[:120],
                    )
                )

        # Check forbidden stage regex
        stage_match = FORBIDDEN_STAGE_REGEX.search(line)
        if stage_match:
            violations.append(
                SanitizationViolation(
                    file_path=filename,
                    line_number=line_idx,
                    matched_term=stage_match.group(0),
                    line_snippet=line[:120],
                )
            )

    return SanitizationResult(
        ok=len(violations) == 0,
        violations=violations,
        scanned_items=1,
        scanned_bytes=len(text.encode("utf-8")),
    )


def extract_svg_text(svg_content: str) -> str:
    """Extract visible text content from SVG XML elements."""
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError:
        return svg_content  # Fall back to raw text if XML parsing fails

    text_parts: list[str] = []
    # Namespaces can vary; search all tags ending with 'text' or 'tspan' or 'desc' or 'title'
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
        if tag in {"text", "tspan", "title", "desc"}:
            if elem.text and elem.text.strip():
                text_parts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                text_parts.append(elem.tail.strip())
    return "\n".join(text_parts)


def sanitize_file(path: Path | str) -> SanitizationResult:
    """Sanitize a single file (TeX, table fragment, macro, SVG, txt, md)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    raw_bytes = p.read_bytes()
    text = raw_bytes.decode("utf-8", errors="replace")

    if p.suffix.lower() == ".svg":
        # Extract XML text nodes as well as scanning the raw content
        visible_text = extract_svg_text(text)
        res_visible = sanitize_text(visible_text, filename=f"{p.name}:[visible_text]")
        res_raw = sanitize_text(text, filename=str(p))
        all_violations = res_visible.violations + res_raw.violations
        # Deduplicate violations by (line_number, matched_term)
        seen: set[tuple[int, str]] = set()
        deduped: list[SanitizationViolation] = []
        for v in all_violations:
            k = (v.line_number, v.matched_term)
            if k not in seen:
                seen.add(k)
                deduped.append(v)
        return SanitizationResult(
            ok=len(deduped) == 0,
            violations=deduped,
            scanned_items=1,
            scanned_bytes=len(raw_bytes),
        )

    res = sanitize_text(text, filename=str(p))
    res.scanned_bytes = len(raw_bytes)
    return res


def sanitize_directory(
    root: Path | str,
    extensions: Sequence[str] = (".tex", ".svg", ".md", ".json", ".txt"),
    fail_fast: bool = False,
) -> SanitizationResult:
    """Sanitize all matching files in a directory."""
    dir_path = Path(root)
    all_violations: list[SanitizationViolation] = []
    total_bytes = 0
    item_count = 0

    ext_set = {e.lower() for e in extensions}

    for p in sorted(dir_path.rglob("*")):
        if p.is_file() and p.suffix.lower() in ext_set:
            res = sanitize_file(p)
            item_count += 1
            total_bytes += res.scanned_bytes
            if not res.ok:
                all_violations.extend(res.violations)
                if fail_fast:
                    break

    return SanitizationResult(
        ok=len(all_violations) == 0,
        violations=all_violations,
        scanned_items=item_count,
        scanned_bytes=total_bytes,
    )
