"""Deterministic, rule-based Tier-1 atom extraction.

No language model is used anywhere in this module. That is a design
requirement, not a convenience: the atom inventory defines the target
population, and a model-mediated inventory would make the population a function
of the model under study.

Every extracted atom records its character span in the SOURCE FRAME, so
``corpus.frame.assert_inventory_within_frame`` can verify mechanically that the
inventory and the relay-visible text agree.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace

from ..corpus.normalize import split_sentences
from ..models import Atom, AtomRole, VerificationStatus
from .taxonomy import ENTITY_SUFFIXES, SCOPE_VOCABULARY

LOCAL_CONTEXT_CHARS = 120

# --- role patterns ---------------------------------------------------------

_PCT = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?%")
_CURRENCY = re.compile(
    r"(?<![\w])(\$|USD\s?|EUR\s?|£|€)\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?"
    r"(billion|million|thousand|bn|mm|m|k)?",
    re.IGNORECASE,
)
_PERIOD_FY = re.compile(r"(?<![\w])(?:FY|fiscal\s+(?:year\s+)?)(\d{4})(?![\d])", re.IGNORECASE)
_PERIOD_Q = re.compile(r"(?<![\w])Q([1-4])\s*(?:of\s*)?(?:FY)?\s*(\d{4})(?![\d])", re.IGNORECASE)
_PERIOD_QSUF = re.compile(
    r"(?<![\w])(?:the\s+)?(first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(\d{4})",
    re.IGNORECASE,
)
_PROVENANCE = re.compile(
    r"(?<![\w])(Note\s+\d+[A-Za-z]?|Item\s+\d+[A-Za-z]?|Exhibit\s+\d+(?:\.\d+)?|"
    r"Part\s+[IVX]+|Schedule\s+[A-Z0-9]+)(?![\w])"
)
_ENTITY = re.compile(
    r"(?<![\w])((?:[A-Z][\w&.\-']*\s+){0,4}[A-Z][\w&.\-']*\s+(?:"
    + "|".join(re.escape(s) for s in ENTITY_SUFFIXES)
    + r"))(?![\w])"
)
_QUARTER_WORD = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def _canon_number(raw: str) -> str:
    return f"{float(raw.replace(',', '')):.4f}".rstrip("0").rstrip(".")


def _scope_pattern() -> re.Pattern[str]:
    ordered = sorted(SCOPE_VOCABULARY, key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(s) for s in ordered) + r")(?![\w])")


_SCOPE = _scope_pattern()


def _sentence_index(spans: list[tuple[int, int]], pos: int) -> int:
    for idx, (a, b) in enumerate(spans):
        if a <= pos < b:
            return idx
    return max(0, len(spans) - 1)


def _raw_candidates(text: str) -> list[tuple[AtomRole, int, int, str, dict]]:
    out: list[tuple[AtomRole, int, int, str, dict]] = []

    for m in _PCT.finditer(text):
        out.append(
            (
                AtomRole.NUMERIC,
                m.start(),
                m.end(),
                _canon_number(m.group(1)) + "%",
                {"subtype": "pct"},
            )
        )

    for m in _CURRENCY.finditer(text):
        unit = (m.group(3) or "").lower()
        canon = f"{m.group(1).strip().upper()}{_canon_number(m.group(2))}"
        if unit:
            canon += f"|{unit}"
        out.append((AtomRole.NUMERIC, m.start(), m.end(), canon, {"subtype": "currency"}))

    for m in _PERIOD_FY.finditer(text):
        out.append((AtomRole.PERIOD, m.start(), m.end(), f"FY{m.group(1)}", {"subtype": "annual"}))

    for m in _PERIOD_Q.finditer(text):
        out.append(
            (
                AtomRole.PERIOD,
                m.start(),
                m.end(),
                f"FY{m.group(2)}Q{m.group(1)}",
                {"subtype": "quarter"},
            )
        )

    for m in _PERIOD_QSUF.finditer(text):
        q = _QUARTER_WORD[m.group(1).lower()]
        out.append(
            (AtomRole.PERIOD, m.start(), m.end(), f"FY{m.group(2)}Q{q}", {"subtype": "quarter"})
        )

    for m in _PROVENANCE.finditer(text):
        canon = re.sub(r"\s+", " ", m.group(1)).strip().title()
        out.append((AtomRole.PROVENANCE, m.start(), m.end(), canon, {}))

    for m in _ENTITY.finditer(text):
        canon = re.sub(r"\s+", " ", m.group(1)).strip()
        out.append((AtomRole.ENTITY, m.start(), m.end(), canon, {}))

    for m in _SCOPE.finditer(text):
        out.append((AtomRole.SCOPE, m.start(), m.end(), m.group(1), {}))

    return out


def _resolve_overlaps(
    cands: list[tuple[AtomRole, int, int, str, dict]],
) -> list[tuple[AtomRole, int, int, str, dict]]:
    """Longest span wins; ties broken by frozen role order then by start.

    Overlap resolution must be total and deterministic, otherwise the inventory
    depends on dict iteration order.
    """
    from .taxonomy import ROLE_ORDER

    order = {r: i for i, r in enumerate(ROLE_ORDER)}
    ranked = sorted(cands, key=lambda c: (-(c[2] - c[1]), order[c[0]], c[1], c[3]))
    kept: list[tuple[AtomRole, int, int, str, dict]] = []
    occupied: list[tuple[int, int]] = []
    for c in ranked:
        if any(not (c[2] <= a or c[1] >= b) for a, b in occupied):
            continue
        kept.append(c)
        occupied.append((c[1], c[2]))
    return sorted(kept, key=lambda c: c[1])


def atomize(document_id: str, text: str) -> list[Atom]:
    """Extract the Tier-1 inventory from ``text``.

    ``text`` MUST be the relay-visible source frame, not the raw document.

    Duplicate surface occurrences of the same ``(role, canonical_value)`` are
    merged into one atom whose ``occurrence_count`` records the multiplicity;
    the retained span is the first occurrence. Merging matters because deletion
    must remove EVERY canonical-equivalent occurrence, otherwise an atom marked
    unavailable is still present in the message.
    """
    sentences = split_sentences(text)
    resolved = _resolve_overlaps(_raw_candidates(text))

    grouped: dict[tuple[str, str], list[tuple[AtomRole, int, int, str, dict]]] = defaultdict(list)
    for cand in resolved:
        grouped[(cand[0].value, cand[3])].append(cand)

    atoms: list[Atom] = []
    for (role_value, canon), members in sorted(grouped.items()):
        first = min(members, key=lambda c: c[1])
        role, start, end, _, meta = first
        atoms.append(
            Atom(
                document_id=document_id,
                atom_id=f"{document_id}:{role_value}:{_slug(canon)}",
                role=role,
                canonical_value=canon,
                surface_form=text[start:end],
                char_start=start,
                char_end=end,
                token_start=-1,
                token_end=-1,
                local_context=text[
                    max(0, start - LOCAL_CONTEXT_CHARS) : min(len(text), end + LOCAL_CONTEXT_CHARS)
                ],
                sentence_index=_sentence_index(sentences, start),
                verification=VerificationStatus.UNVERIFIED,
                occurrence_count=len(members),
                metadata={
                    **meta,
                    "all_spans": [(c[1], c[2]) for c in sorted(members, key=lambda c: c[1])],
                },
            )
        )
    atoms.sort(key=lambda a: (a.char_start, a.role.value, a.canonical_value))
    return atoms


_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-")[:48]


def attach_token_spans(atoms: list[Atom], text: str, tokenizer) -> list[Atom]:
    """Fill token offsets by encoding the prefix. Exact but O(n) per atom;
    used once per document at inventory-build time."""
    out: list[Atom] = []
    for atom in atoms:
        out.append(
            replace(
                atom,
                token_start=tokenizer.count(text[: atom.char_start]),
                token_end=tokenizer.count(text[: atom.char_end]),
            )
        )
    return out
