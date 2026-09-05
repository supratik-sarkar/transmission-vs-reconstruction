"""Construction of the relay-visible source frame.

This module implements the single most important structural invariant in the
protocol:

    the atom inventory is built from EXACTLY the text the relay can see.

If the atomizer ran on the full filing while the relay saw a 2000-token window,
then atoms outside the window would be scored as transmission failures for
content the compressor was never shown. The frame is therefore cut FIRST,
hashed, and every downstream stage consumes the frame -- never the raw source.

Pipeline (§13):
    raw -> extract section -> normalise -> tokenize (frozen tokenizer)
        -> cut window -> hash -> atomize THAT text
"""

from __future__ import annotations

import hashlib

from ..models import SourceFrame
from ..tokenization import Tokenizer, get_tokenizer
from .normalize import normalize_text
from .sections import SectionNotFound, extract_mdna


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_source_frame(
    *,
    document_id: str,
    raw_text: str,
    window_tokens: int,
    tokenizer: Tokenizer | None = None,
    tokenizer_name: str = "cl100k_base",
    allow_tokenizer_fallback: bool = False,
    section: str = "mdna",
    require_section: bool = True,
) -> SourceFrame:
    tok = tokenizer or get_tokenizer(tokenizer_name, allow_fallback=allow_tokenizer_fallback)

    if section == "mdna":
        try:
            start, end = extract_mdna(raw_text)
            body = raw_text[start:end]
        except SectionNotFound:
            if require_section:
                raise
            body = raw_text
    elif section == "full":
        body = raw_text
    else:  # pragma: no cover - guarded by config schema
        raise ValueError(f"unknown section {section!r}")

    normalised = normalize_text(body)
    windowed, truncated = tok.truncate(normalised, window_tokens)
    # Re-normalise: truncation can leave trailing whitespace, and the hash must
    # be over exactly the bytes the relay receives.
    windowed = windowed.rstrip()

    return SourceFrame(
        document_id=document_id,
        text=windowed,
        token_count=tok.count(windowed),
        tokenizer=tok.name,
        window_tokens=window_tokens,
        truncated=truncated,
        sha256=sha256_text(windowed),
        section=section,
    )


class FrameEquivalenceError(AssertionError):
    pass


def assert_inventory_within_frame(frame: SourceFrame, atoms) -> None:
    """Every atom span must lie inside the relay-visible frame and its surface
    form must be recoverable from the frame at that span.

    This is checked mechanically rather than trusted, because a single offset
    bug here silently redefines the target population.
    """
    n = len(frame.text)
    for atom in atoms:
        if atom.document_id != frame.document_id:
            raise FrameEquivalenceError(
                f"atom {atom.atom_id} belongs to {atom.document_id}, frame is {frame.document_id}"
            )
        if not (0 <= atom.char_start < atom.char_end <= n):
            raise FrameEquivalenceError(
                f"atom {atom.atom_id} span ({atom.char_start},{atom.char_end}) outside frame of length {n}"
            )
        if frame.text[atom.char_start : atom.char_end] != atom.surface_form:
            raise FrameEquivalenceError(
                f"atom {atom.atom_id} surface form does not match frame text at its span"
            )
