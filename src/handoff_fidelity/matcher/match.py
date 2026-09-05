"""Presence detection for a canonical atom value inside a message.

The critical correctness property is that matching is TOKEN-BOUNDARY aware.
A naive substring test reports the entity ``AB`` as present inside ``ABC Corp``
and the period ``FY202`` inside ``FY2023``; both inflate the measured
transmission rate T, which is the denominator of half the paper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .canonical import canonical_numeric, canonical_period, canonicalize, normalize

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)

_NUMERIC_SPAN = re.compile(
    r"(?:\$|usd|eur|gbp|£|€)?\s*-?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|pct|billion|million|thousand|bn|mm|m|k)?",
    re.IGNORECASE,
)
# Trailing (?!\d) matters: without it "FY2023" matches inside "FY20231",
# which inflates the measured transmission rate.
_PERIOD_SPAN = re.compile(
    r"(?<!\w)(?:fy\s*\d{4}(?:\s*q[1-4])?|q[1-4]\s*(?:of\s*)?(?:fy)?\s*\d{4}|"
    r"fiscal\s+(?:year\s+)?\d{4}|(?:first|second|third|fourth)\s+quarter\s+of\s+"
    r"(?:fiscal\s+)?\d{4})(?!\w)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MatchSpan:
    start: int
    end: int
    text: str


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


def _contains_token_sequence(haystack: str, needle: str) -> bool:
    h = _tokens(haystack)
    n = _tokens(needle)
    if not n or len(n) > len(h):
        return False
    return any(h[i : i + len(n)] == n for i in range(len(h) - len(n) + 1))


def find_spans(message: str, *, canonical_value: str, role: str) -> list[MatchSpan]:
    """All character spans in ``message`` whose canonical form equals
    ``canonical_value``. Used by the editor: deletion must remove EVERY
    canonical-equivalent occurrence, not just the first."""
    spans: list[MatchSpan] = []
    if role == "numeric":
        for m in _NUMERIC_SPAN.finditer(message):
            text = m.group().strip()
            if text and canonical_numeric(text) == canonical_value:
                spans.append(MatchSpan(m.start(), m.start() + len(m.group().rstrip()), text))
        return _dedupe(spans)
    if role == "period":
        for m in _PERIOD_SPAN.finditer(message):
            if canonical_period(m.group()) == canonical_value:
                spans.append(MatchSpan(m.start(), m.end(), m.group()))
        return _dedupe(spans)

    # entity / scope / provenance: literal token-boundary search over surface
    # variants generated from the canonical value.
    pattern = re.compile(
        r"(?<!\w)" + r"\s+".join(re.escape(tok) for tok in canonical_value.split()) + r"(?!\w)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(message):
        if canonicalize(m.group(), role) == canonicalize(canonical_value, role):
            spans.append(MatchSpan(m.start(), m.end(), m.group()))
    return _dedupe(spans)


def _dedupe(spans: list[MatchSpan]) -> list[MatchSpan]:
    seen: set[tuple[int, int]] = set()
    out: list[MatchSpan] = []
    for s in sorted(spans, key=lambda x: (x.start, -x.end)):
        if any(not (s.end <= a or s.start >= b) for a, b in seen):
            continue
        seen.add((s.start, s.end))
        out.append(s)
    return out


def is_transmitted(message: str, *, canonical_value: str, role: str) -> bool:
    """T_z: did this atom appear in the handoff message?"""
    if find_spans(message, canonical_value=canonical_value, role=role):
        return True
    if role in {"entity", "scope", "provenance"}:
        return _contains_token_sequence(message, canonical_value)
    return False


def recovered(output: str, *, canonical_value: str, role: str) -> bool:
    """Y_iz: did the receiver's elicited value match the source value?

    The receiver answers into a fixed slot schema, so ``output`` is normally a
    short field value rather than free prose; the same canonical comparison is
    applied either way.
    """
    stripped = output.strip()
    if stripped and canonicalize(stripped, role) == canonical_value:
        return True
    return is_transmitted(output, canonical_value=canonical_value, role=role)
