"""The deterministic atom renderer.

The SAME renderer is used by CausalRelay and by the Uniform-atoms control.
That is the whole point of the control: holding rendering fixed, the difference
between the two isolates ALLOCATION POLICY rather than presentation.

No language model may be called inside this module. A learned renderer would
make the comparison "our allocation plus our phrasing" versus "their
allocation", which is not the claim being made.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ..models import Atom

RENDERER_VERSION = "atomline-v1"


def render_atom(atom: Atom) -> str:
    """One atom, one line. The canonical value is emitted verbatim so that the
    matcher can detect it; renderer and matcher must agree, and the editor
    asserts that they do."""
    return f"- {atom.role.value}: {atom.canonical_value}"


def render_message(atoms: Sequence[Atom], *, header: str | None = None) -> str:
    """Atoms in source order.

    Source order, not predicted-utility order: ordering by utility would leak
    the policy's ranking into the surface form, so a receiver could in principle
    exploit position. Sorting by source position keeps the surface form a
    function of the document alone.
    """
    ordered = sorted(atoms, key=lambda a: (a.char_start, a.role.value, a.atom_id))
    lines = [render_atom(a) for a in ordered]
    if header:
        lines.insert(0, header.strip())
    return "\n".join(lines)


def rendered_token_cost(atom: Atom, tokenizer) -> int:
    """Token cost of including this atom, INCLUDING its line separator, so the
    knapsack budget matches the realised message length."""
    return tokenizer.count(render_atom(atom) + "\n")


def renderer_hash() -> str:
    payload = "|".join(
        (
            RENDERER_VERSION,
            render_atom.__doc__ or "",
            "- {role}: {canonical_value}",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
