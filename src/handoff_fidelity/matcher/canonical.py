"""Canonicalisation for every Tier-1 role.

Deterministic and total: given a role and a surface string, the canonical form
is a pure function. No model is consulted, so the primary outcome never depends
on a judge.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_PUNCT_STRIP = re.compile(r"[^\w\s.\-%$€£/]", re.UNICODE)
_WS = re.compile(r"\s+")

_MAGNITUDE = {
    "bn": Decimal(10) ** 9,
    "billion": Decimal(10) ** 9,
    "mm": Decimal(10) ** 6,
    "m": Decimal(10) ** 6,
    "million": Decimal(10) ** 6,
    "k": Decimal(10) ** 3,
    "thousand": Decimal(10) ** 3,
}

_QUARTER_WORD = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace(" ", " ").replace("­", "")
    for src, dst in (
        ("’", "'"),
        ("‘", "'"),
        ("“", '"'),
        ("”", '"'),
        ("–", "-"),
        ("—", "-"),
        ("−", "-"),
    ):
        value = value.replace(src, dst)
    value = _PUNCT_STRIP.sub(" ", value)
    return _WS.sub(" ", value).strip().casefold()


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def canonical_numeric(value: str) -> str:
    """Percentages, currency and bare numbers to a single normal form.

    ``6.2%``, ``6.20 %`` and ``6.2 percent`` all canonicalise to ``6.2%``;
    ``$1.5 billion`` and ``USD 1,500,000,000`` both to ``USD1500000000``.
    Decimal equivalence is exact (``Decimal``), never float comparison.
    """
    raw = unicodedata.normalize("NFKC", value).strip()
    raw = raw.replace(" ", " ")
    low = raw.casefold().replace("percent", "%").replace("pct", "%")

    m = re.search(r"(-?\d[\d,]*(?:\.\d+)?)\s*%", low)
    if m:
        d = _decimal(m.group(1))
        if d is not None:
            return f"{_trim(d)}%"

    m = re.search(
        r"(\$|usd|eur|gbp|£|€)\s*(-?\d[\d,]*(?:\.\d+)?)\s*"
        r"(billion|million|thousand|bn|mm|m|k)?",
        low,
    )
    if m:
        d = _decimal(m.group(2))
        if d is not None:
            mult = _MAGNITUDE.get((m.group(3) or "").strip(), Decimal(1))
            sym = {"$": "USD", "usd": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP"}[
                m.group(1)
            ]
            return f"{sym}{_trim(d * mult)}"

    m = re.search(r"(-?\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand|bn|mm|m|k)?", low)
    if m:
        d = _decimal(m.group(1))
        if d is not None:
            mult = _MAGNITUDE.get((m.group(2) or "").strip(), Decimal(1))
            return _trim(d * mult)
    return normalize(value)


def _trim(d: Decimal) -> str:
    return format(d.normalize(), "f")


def canonical_period(value: str) -> str:
    """``FY2023``, ``fiscal 2023``, ``Q1 2023``, ``the first quarter of 2023``
    to ``FY2023`` / ``FY2023Q1``."""
    v = unicodedata.normalize("NFKC", value).strip().casefold()
    v = v.replace("fiscal year", "fy").replace("fiscal", "fy")

    m = re.search(r"q([1-4])\s*(?:of\s*)?(?:fy)?\s*(\d{4})", v)
    if m:
        return f"FY{m.group(2)}Q{m.group(1)}"
    m = re.search(r"(first|second|third|fourth)\s+quarter\s+of\s+(?:fy\s*)?(\d{4})", v)
    if m:
        return f"FY{m.group(2)}Q{_QUARTER_WORD[m.group(1)]}"
    m = re.search(r"(?:fy)\s*(\d{4})", v)
    if m:
        return f"FY{m.group(1)}"
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", v)
    if m:
        return f"FY{m.group(1)}"
    return normalize(value)


def canonical_provenance(value: str) -> str:
    v = normalize(value)
    v = _WS.sub(" ", v)
    return v.title()


def canonicalize(value: str, role: str) -> str:
    if role == "numeric":
        return canonical_numeric(value)
    if role == "period":
        return canonical_period(value)
    if role == "provenance":
        return canonical_provenance(value)
    return normalize(value)
