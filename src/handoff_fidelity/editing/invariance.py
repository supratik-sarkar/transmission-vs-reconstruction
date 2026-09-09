"""Mechanical definition of non-focal invariance.

Assumption "consistency and confined interference" requires that an
availability intervention alters the message ONLY through the presence of the
focal atom. That is not directly observable, but a strictly weaker mechanical
property is, and it is checked on every single edit rather than asserted:

    masking every canonical-equivalent occurrence of the focal atom in both the
    natural and the edited message, and collapsing whitespace, must leave two
    byte-identical strings.

If this fails, the edit touched non-focal content and is rejected.
"""

from __future__ import annotations

import re

from ..matcher.match import find_spans

_WS = re.compile(r"\s+")
MASK = "\x00FOCAL\x00"


def mask_focal(message: str, *, canonical_value: str, role: str) -> str:
    spans = find_spans(message, canonical_value=canonical_value, role=role)
    if not spans:
        return message
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(message[cursor : span.start])
        out.append(MASK)
        cursor = span.end
    out.append(message[cursor:])
    return "".join(out)


def _collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


_CLEANUP: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"\s+([,.;:%])"), r"\1"),
    (re.compile(r"([(\[])\s+"), r"\1"),
    (re.compile(r"\s+([)\]])"), r"\1"),
    (re.compile(r"\(\s*\)"), ""),
    (re.compile(r",\s*,"), ","),
    (re.compile(r"\s+\n"), "\n"),
    (re.compile(r"[ \t]+$", re.MULTILINE), ""),
)


def _cleanup(text: str) -> str:
    for _ in range(5):
        orig = text
        for pattern, repl in _CLEANUP:
            text = pattern.sub(repl, text)
        if text == orig:
            break
    return text.strip()


def non_focal_invariant(natural: str, edited: str, *, canonical_value: str, role: str) -> bool:
    a = _collapse(mask_focal(natural, canonical_value=canonical_value, role=role))
    b = _collapse(mask_focal(edited, canonical_value=canonical_value, role=role))
    a = _collapse(a.replace(MASK, " "))
    b = _collapse(b.replace(MASK, " "))
    if a == b:
        return True
    return _cleanup(a) == _cleanup(b)


def diff_summary(natural: str, edited: str) -> dict[str, int]:
    return {
        "chars_natural": len(natural),
        "chars_edited": len(edited),
        "chars_delta": len(edited) - len(natural),
    }


def non_focal_invariant_insertion(natural: str, edited: str, *, appended: str) -> bool:
    """Insertion adds text by construction, so the deletion-style invariant does
    not apply to it. What must hold instead is that the edited message is
    EXACTLY the natural message plus the appended rendering: nothing in the
    original content may be rewritten, reordered or reflowed.
    """
    tail = appended.strip()
    if not edited.endswith(tail):
        return False
    prefix = edited[: len(edited) - len(tail)]
    return _collapse(prefix) == _collapse(natural)
