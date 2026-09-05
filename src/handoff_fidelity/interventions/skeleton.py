"""Experiment B: the matched skeleton H_{-z}.

The naive contrast between a natural document and a value-randomised twin
confounds prior access with context composition, and forcing the focal atom
absent in both arms removes neither. If both arms are generated from a COMMON
skeleton -- identical slots present, identical slots absent, matched position
and length -- the context-composition term vanishes and the contrast identifies
the prior-access effect alone.

Construction rules:

  * a tuple is drawn from a frozen bounded local window (same sentence, or a
    frozen local source window), so it is relationally coherent;
  * NOT all five roles are required. Requiring all five would exclude most real
    sentences and silently redefine the population;
  * the focal slot is rendered as <<OMITTED>> in BOTH arms;
  * only the identity/value mapping differs between arms. Slot structure,
    order, position and intended length rule are identical.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import Atom, AtomRole

OMITTED = "<<OMITTED>>"
MIN_POPULATED_ROLES = 3
SLOT_ORDER: tuple[AtomRole, ...] = (
    AtomRole.ENTITY,
    AtomRole.SCOPE,
    AtomRole.PERIOD,
    AtomRole.NUMERIC,
    AtomRole.PROVENANCE,
)


class TupleIneligible(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateTuple:
    document_id: str
    slot_id: str
    sentence_index: int
    slots: dict[AtomRole, Atom]

    @property
    def populated_roles(self) -> tuple[AtomRole, ...]:
        return tuple(r for r in SLOT_ORDER if r in self.slots)


def build_candidate_tuples(
    atoms: Sequence[Atom], *, min_roles: int = MIN_POPULATED_ROLES
) -> list[CandidateTuple]:
    """Group atoms by frozen local window (sentence index) into tuples."""
    by_sentence: dict[int, dict[AtomRole, Atom]] = {}
    for atom in sorted(atoms, key=lambda a: (a.sentence_index, a.char_start, a.atom_id)):
        slot = by_sentence.setdefault(atom.sentence_index, {})
        slot.setdefault(atom.role, atom)
    out: list[CandidateTuple] = []
    for idx in sorted(by_sentence):
        slots = by_sentence[idx]
        if len(slots) >= min_roles:
            doc = next(iter(slots.values())).document_id
            out.append(CandidateTuple(doc, f"{doc}:tuple:{idx}", idx, dict(slots)))
    return out


def is_eligible(
    tup: CandidateTuple, focal_role: AtomRole, *, min_roles: int = MIN_POPULATED_ROLES
) -> bool:
    return focal_role in tup.slots and len(tup.populated_roles) >= min_roles


def render_skeleton(
    tup: CandidateTuple,
    focal_role: AtomRole,
    mapping: Mapping[AtomRole, str],
) -> str:
    """Render H_{-z} under a value mapping.

    The focal slot is OMITTED in both arms; only the non-focal values change
    between the natural and prior-blocked mappings.
    """
    if not is_eligible(tup, focal_role):
        raise TupleIneligible(f"{tup.slot_id} is not eligible with focal role {focal_role.value}")
    lines: list[str] = []
    for role in tup.populated_roles:
        value = (
            OMITTED if role is focal_role else mapping.get(role, tup.slots[role].canonical_value)
        )
        lines.append(f"- {role.value}: {value}")
    return "\n".join(lines)


def natural_mapping(tup: CandidateTuple) -> dict[AtomRole, str]:
    return {role: atom.canonical_value for role, atom in tup.slots.items()}


_SLOT_LINE = re.compile(r"^- (?P<role>[a-z]+): (?P<value>.*)$")


def slot_structure(rendered: str) -> list[str]:
    """The structural signature used to verify that two arms share a skeleton:
    slot order and which slot is omitted, with values erased."""
    out: list[str] = []
    for line in rendered.split("\n"):
        m = _SLOT_LINE.match(line)
        if not m:
            raise ValueError(f"malformed skeleton line: {line!r}")
        out.append(f"{m.group('role')}:{'OMITTED' if m.group('value') == OMITTED else 'VALUE'}")
    return out


def assert_matched(natural_render: str, blocked_render: str) -> None:
    """Identical slot structure, identical focal absence, matched position.

    Verified mechanically rather than assumed: if the two arms drift apart
    structurally, the contrast stops identifying prior access.
    """
    if slot_structure(natural_render) != slot_structure(blocked_render):
        raise AssertionError("matched-skeleton arms differ in slot structure or focal absence")
    if natural_render.count(OMITTED) != 1 or blocked_render.count(OMITTED) != 1:
        raise AssertionError("exactly one slot must be omitted in each arm")
