"""The availability editor.

Constructs ONLY the missing arm:

    T = 1  ->  delete the focal atom          (mechanism "del")
    T = 0  ->  insert the focal atom          (mechanism "ins")

The natural message is never edited. Editing both sides would make the
decomposition describe an edited pipeline rather than the deployed one, so the
editing artefact is handled by the sham placebo and partial identification
instead of by assumed cancellation.

Insertion OVERRUNS the budget rather than displacing another atom. That is
deliberate: under overrun a negative availability surplus isolates
interference, and cannot be a displacement artefact. Budget-neutral
displacement is a separate estimand (Experiment C).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..matcher.match import find_spans
from .invariance import non_focal_invariant, non_focal_invariant_insertion

Mechanism = Literal["del", "ins"]

# Deterministic clean-up after a deletion. Applied in a fixed order.
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

# A deletion is refused when the focal span sits inside one of these
# constructions, because removing it leaves a sentence whose meaning is altered
# by more than the absence of the atom.
_ENTANGLED_LEFT = re.compile(r"(?:compared\s+with|versus|vs\.?|from|between)\s*$", re.IGNORECASE)
_ENTANGLED_RIGHT = re.compile(r"^\s*(?:and|or|to|through)\s+\d", re.IGNORECASE)


class InvalidEdit(ValueError):
    """Raised when a mechanically valid edit cannot be produced. The atom is
    flagged ineligible for intervention and the rate is reported; it is NOT
    silently dropped."""


@dataclass(frozen=True, slots=True)
class EditLog:
    document_id: str
    atom_id: str
    role: str
    mechanism: Mechanism
    occurrences: int
    accepted: bool
    reason: str = ""
    tokens_before: int = -1
    tokens_after: int = -1
    overrun_tokens: int = 0
    detail: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EditResult:
    text: str
    log: EditLog


def _cleanup(text: str) -> str:
    for pattern, repl in _CLEANUP:
        text = pattern.sub(repl, text)
    return text.strip()


def _entangled(message: str, start: int, end: int) -> bool:
    left = message[max(0, start - 24) : start]
    right = message[end : end + 24]
    return bool(_ENTANGLED_LEFT.search(left) or _ENTANGLED_RIGHT.match(right))


def delete_atom(
    message: str,
    *,
    document_id: str,
    atom_id: str,
    canonical_value: str,
    role: str,
    tokenizer=None,
) -> EditResult:
    spans = find_spans(message, canonical_value=canonical_value, role=role)
    if not spans:
        raise InvalidEdit(
            f"deletion requested for {atom_id} but no canonical-equivalent occurrence "
            "is present in the message; T was measured inconsistently"
        )
    for span in spans:
        if _entangled(message, span.start, span.end):
            raise InvalidEdit(f"entangled clause around {atom_id}") from None

    chars = list(message)
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        del chars[span.start : span.end]
    edited = _cleanup("".join(chars))

    if not non_focal_invariant(message, edited, canonical_value=canonical_value, role=role):
        raise InvalidEdit(f"deletion of {atom_id} altered non-focal content")

    if find_spans(edited, canonical_value=canonical_value, role=role):
        raise InvalidEdit(f"deletion of {atom_id} left a canonical-equivalent occurrence")

    tb = tokenizer.count(message) if tokenizer else -1
    ta = tokenizer.count(edited) if tokenizer else -1
    return EditResult(
        edited,
        EditLog(
            document_id,
            atom_id,
            role,
            "del",
            len(spans),
            True,
            "",
            tb,
            ta,
            0,
            {"removed_spans": len(spans)},
        ),
    )


def insert_atom(
    message: str,
    *,
    document_id: str,
    atom_id: str,
    canonical_value: str,
    role: str,
    rendered: str,
    tokenizer=None,
    budget: int | None = None,
) -> EditResult:
    """Append the rendered atom at the frozen insertion position.

    Position policy (frozen): a new final line. Appending is the only position
    that is well defined for every message shape without a model deciding where
    the atom "belongs"; any content-sensitive placement would put a judge inside
    the intervention.

    The insertion OVERRUNS the budget; the overrun is measured and reported
    rather than avoided by eviction.
    """
    if find_spans(message, canonical_value=canonical_value, role=role):
        raise InvalidEdit(
            f"insertion requested for {atom_id} but it is already present; T was "
            "measured inconsistently"
        )
    sep = "" if not message or message.endswith("\n") else "\n"
    edited = f"{message}{sep}{rendered.strip()}"

    if not non_focal_invariant_insertion(message, edited, appended=rendered):
        raise InvalidEdit(
            f"insertion of {atom_id} altered non-focal content: the edited message must "
            "be exactly the natural message plus the appended rendering"
        )
    if not find_spans(edited, canonical_value=canonical_value, role=role):
        raise InvalidEdit(
            f"insertion of {atom_id} did not produce a matcher-detectable occurrence; "
            "renderer and matcher disagree"
        )

    tb = tokenizer.count(message) if tokenizer else -1
    ta = tokenizer.count(edited) if tokenizer else -1
    overrun = max(0, ta - budget) if (budget is not None and ta >= 0) else 0
    return EditResult(
        edited,
        EditLog(
            document_id,
            atom_id,
            role,
            "ins",
            1,
            True,
            "",
            tb,
            ta,
            overrun,
            {"inserted_chars": len(rendered.strip())},
        ),
    )


def build_counterfactual(
    message: str,
    *,
    document_id: str,
    atom_id: str,
    canonical_value: str,
    role: str,
    transmitted: int,
    rendered: str,
    tokenizer=None,
    budget: int | None = None,
) -> EditResult:
    """Construct exactly the missing availability arm."""
    if transmitted == 1:
        return delete_atom(
            message,
            document_id=document_id,
            atom_id=atom_id,
            canonical_value=canonical_value,
            role=role,
            tokenizer=tokenizer,
        )
    return insert_atom(
        message,
        document_id=document_id,
        atom_id=atom_id,
        canonical_value=canonical_value,
        role=role,
        rendered=rendered,
        tokenizer=tokenizer,
        budget=budget,
    )
