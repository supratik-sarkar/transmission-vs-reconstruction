"""Deterministic text normalisation applied before the source frame is cut.

Normalisation must be deterministic and idempotent, because the frame hash is
the anchor for the whole provenance chain.
"""

from __future__ import annotations

import re
import unicodedata

_NBSP = " "
_SOFT_HYPHEN = "­"
_QUOTES = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "–": "-",
    "—": "-",
    "−": "-",
}
_WS_RUN = re.compile(r"[ \t\f\v]+")
_BLANK_RUN = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(_SOFT_HYPHEN, "").replace(_NBSP, " ")
    for src, dst in _QUOTES.items():
        text = text.replace(src, dst)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RUN.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Character spans of sentences. Deterministic and offset-preserving."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_SPLIT.finditer(text):
        end = m.start()
        if end > start:
            spans.append((start, end))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans
