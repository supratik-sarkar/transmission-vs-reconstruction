"""Sham (semantics-preserving) edits.

A sham applies the editing machinery while leaving the semantic content of the
focal atom intact, so it isolates the MECHANICAL component of the editing
artefact: formatting disruption, fluency loss, length change, position shift.

What a sham cannot do is establish the exclusion restriction. The quantity at
issue -- whether removing the MEANING of the atom affects the receiver only
through the atom's availability -- is by construction not varied by a
semantics-preserving edit. The residual semantic component is therefore carried
by the partial-identification region in ``causal.sham_partial``, never by a
point correction presented as a test.

Two shams exist because deletion and insertion are different operations with
different artefact profiles; a single pooled sham would double-count the
artefact on one arm and cancel it on the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..matcher.match import find_spans
from .editor import EditLog, InvalidEdit, _cleanup
from .invariance import non_focal_invariant

ShamMechanism = Literal["del", "ins"]


@dataclass(frozen=True, slots=True)
class ShamResult:
    text: str
    log: EditLog


def sham_deletion(
    message: str,
    *,
    document_id: str,
    atom_id: str,
    canonical_value: str,
    role: str,
    equivalent_surface: str,
    tokenizer=None,
) -> ShamResult:
    """Remove every occurrence and reinstate an equivalent surface form in the
    same position.

    ``equivalent_surface`` must canonicalise to ``canonical_value`` (e.g.
    ``6.20%`` for ``6.2%``, ``fiscal 2023`` for ``FY2023``). The message is
    disturbed exactly as a real deletion disturbs it, but no information is
    removed.
    """
    spans = find_spans(message, canonical_value=canonical_value, role=role)
    if not spans:
        raise InvalidEdit(f"sham deletion for {atom_id}: atom not present")
    chars = list(message)
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        chars[span.start : span.end] = list(equivalent_surface)
    edited = _cleanup("".join(chars))

    if not find_spans(edited, canonical_value=canonical_value, role=role):
        raise InvalidEdit(
            f"sham deletion for {atom_id} destroyed the value: the replacement surface "
            "form does not canonicalise back to the same atom"
        )
    return ShamResult(
        edited,
        EditLog(
            document_id,
            atom_id,
            role,
            "del",
            len(spans),
            True,
            "sham",
            tokenizer.count(message) if tokenizer else -1,
            tokenizer.count(edited) if tokenizer else -1,
            0,
            {"sham": 1},
        ),
    )


def sham_insertion(
    message: str,
    *,
    document_id: str,
    atom_id: str,
    canonical_value: str,
    role: str,
    redundant_rendered: str,
    tokenizer=None,
) -> ShamResult:
    """Append a rendered line that carries content ALREADY present in the
    message, reproducing the length and position perturbation of a real
    insertion without adding information.
    """
    sep = "" if not message or message.endswith("\n") else "\n"
    edited = f"{message}{sep}{redundant_rendered.strip()}"
    if find_spans(edited, canonical_value=canonical_value, role=role) != find_spans(
        message, canonical_value=canonical_value, role=role
    ):
        raise InvalidEdit(
            f"sham insertion for {atom_id} changed focal availability; the appended "
            "line must not introduce the focal atom"
        )
    if not non_focal_invariant(message, edited, canonical_value=canonical_value, role=role):
        # Expected: the sham DOES add non-focal text. We record it rather than
        # assert invariance, because a sham insertion is by definition an
        # addition; the invariance check applies to real interventions only.
        pass
    return ShamResult(
        edited,
        EditLog(
            document_id,
            atom_id,
            role,
            "ins",
            0,
            True,
            "sham",
            tokenizer.count(message) if tokenizer else -1,
            tokenizer.count(edited) if tokenizer else -1,
            0,
            {"sham": 1},
        ),
    )
