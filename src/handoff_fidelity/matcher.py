from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


def canonical_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"[^\w\s.\-%]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def canonical_numeric(value: str) -> str:
    raw = canonical_text(value).replace("%", "").replace(",", "")
    try:
        return f"{Decimal(raw):.2f}"
    except InvalidOperation:
        return canonical_text(value)


def canonical_period(value: str) -> str:
    v = canonical_text(value).upper().replace(" ", "")
    m = re.fullmatch(r"FY(\d{4})Q([1-4])", v)
    if m:
        return f"FY{m.group(1)}Q{m.group(2)}"
    m = re.fullmatch(r"FY(\d{4})", v)
    if m:
        return f"FY{m.group(1)}"
    return v


def canonicalize(value: str, role: str) -> str:
    if role == "numeric":
        return canonical_numeric(value)
    if role == "period":
        return canonical_period(value)
    return canonical_text(value)


def is_transmitted(message: str, *, canonical_value: str, role: str) -> bool:
    if role == "numeric":
        candidates = re.findall(r"-?\d[\d,]*(?:\.\d+)?%?", message)
        return canonical_value in {canonical_numeric(c) for c in candidates}
    return canonical_value in canonicalize(message, role)
