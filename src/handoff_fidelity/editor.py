from __future__ import annotations

import re
from dataclasses import dataclass

from .matcher import canonical_numeric


@dataclass(frozen=True)
class EditResult:
    text: str
    changed: bool
    occurrences: int


def delete_surface_occurrences(message: str, *, surface_value: str, role: str) -> EditResult:
    """Conservative relay-message deletion helper.

    Real experimental use must pass the coherence/non-focal invariance audit. This
    helper deliberately does not attempt semantic paraphrase deletion.
    """
    if role == "numeric":
        pattern = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")
        hits = [
            m
            for m in pattern.finditer(message)
            if canonical_numeric(m.group()) == canonical_numeric(surface_value)
        ]
        if not hits:
            return EditResult(message, False, 0)
        chars = list(message)
        for match in reversed(hits):
            chars[match.start() : match.end()] = ""
        return EditResult("".join(chars), True, len(hits))

    pattern = re.compile(re.escape(surface_value), flags=re.IGNORECASE)
    edited, count = pattern.subn("", message)
    return EditResult(edited, count > 0, count)


def insert_focal_atom(message: str, *, rendered_atom: str) -> EditResult:
    sep = "\n" if message and not message.endswith("\n") else ""
    return EditResult(f"{message}{sep}{rendered_atom}", True, 1)
