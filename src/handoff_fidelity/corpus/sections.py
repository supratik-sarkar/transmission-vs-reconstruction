"""Section extraction.

Rule-based and deterministic: no model is used to decide what counts as the
management-discussion section, because that decision would then sit inside the
definition of the target population.
"""

from __future__ import annotations

import re

MDNA_START = re.compile(
    r"item\s*7\s*[.\-:–]?\s*management['’]?s?\s+discussion\s+and\s+analysis",
    re.IGNORECASE,
)
MDNA_END = re.compile(
    r"item\s*(7a|8)\s*[.\-:–]?\s*(quantitative|financial\s+statements)",
    re.IGNORECASE,
)


class SectionNotFound(ValueError):
    pass


def extract_mdna(text: str) -> tuple[int, int]:
    """Return the character span of the MD&A section.

    If the document contains a table of contents the first match is a pointer
    rather than the section itself, so the LAST start match preceding a valid
    end match is used.
    """
    starts = [m.end() for m in MDNA_START.finditer(text)]
    if not starts:
        raise SectionNotFound("no MD&A heading matched")
    ends = [m.start() for m in MDNA_END.finditer(text)]
    best: tuple[int, int] | None = None
    for s in starts:
        candidate_ends = [e for e in ends if e > s]
        end = candidate_ends[0] if candidate_ends else len(text)
        if best is None or (end - s) > (best[1] - best[0]):
            best = (s, end)
    assert best is not None
    if best[1] - best[0] < 500:
        raise SectionNotFound("MD&A span too short to be the real section")
    return best
