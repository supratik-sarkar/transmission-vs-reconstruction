"""Atom inventory serialisation.

The inventory that enters the experiment is the HUMAN-VERIFIED one. Loading
deliberately refuses rows without an explicit verification decision rather than
defaulting them to accepted: the inventory defines the target population, so a
silently-accepted row silently changes what the paper is about.

Uses the stdlib csv module so the scientific core has no pandas dependency.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..models import Atom, AtomRole, VerificationStatus

COLUMNS: tuple[str, ...] = (
    "document_id",
    "atom_id",
    "role",
    "canonical_value",
    "surface_form",
    "char_start",
    "char_end",
    "token_start",
    "token_end",
    "sentence_index",
    "occurrence_count",
    "verification",
    "local_context",
)


def write_inventory(atoms: Iterable[Atom], path: Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for atom in atoms:
            w.writerow(
                {
                    "document_id": atom.document_id,
                    "atom_id": atom.atom_id,
                    "role": atom.role.value,
                    "canonical_value": atom.canonical_value,
                    "surface_form": atom.surface_form,
                    "char_start": atom.char_start,
                    "char_end": atom.char_end,
                    "token_start": atom.token_start,
                    "token_end": atom.token_end,
                    "sentence_index": atom.sentence_index,
                    "occurrence_count": atom.occurrence_count,
                    "verification": atom.verification.value,
                    "local_context": atom.local_context.replace("\n", " "),
                }
            )
            n += 1
    return n


def read_inventory(path: Path, *, require_verified: bool = True) -> list[Atom]:
    atoms: list[Atom] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            status = VerificationStatus(row.get("verification", "unverified") or "unverified")
            if require_verified and status is not VerificationStatus.ACCEPTED:
                continue
            atoms.append(
                Atom(
                    document_id=row["document_id"],
                    atom_id=row["atom_id"],
                    role=AtomRole(row["role"]),
                    canonical_value=row["canonical_value"],
                    surface_form=row["surface_form"],
                    char_start=int(row["char_start"]),
                    char_end=int(row["char_end"]),
                    token_start=int(row.get("token_start") or -1),
                    token_end=int(row.get("token_end") or -1),
                    local_context=row.get("local_context", ""),
                    sentence_index=int(row.get("sentence_index") or 0),
                    verification=status,
                    occurrence_count=int(row.get("occurrence_count") or 1),
                )
            )
    return atoms


def issuer_disjoint(a: Sequence[str], b: Sequence[str], issuer_of: dict[str, str]) -> bool:
    return not (
        {issuer_of[d] for d in a if d in issuer_of} & {issuer_of[d] for d in b if d in issuer_of}
    )
