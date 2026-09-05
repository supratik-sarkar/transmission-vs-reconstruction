"""Eligibility filtering and human-verification tooling.

Eligibility is decided BEFORE treatment is observed. Filtering after seeing
transmission would make the analysis set a function of the relay's decisions,
which is the exact selection the design exists to remove.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ..models import Atom, VerificationStatus

#: Reasons an atom is removed from the target population, pre-treatment.
EXCLUSION_REASONS: tuple[str, ...] = (
    "conflict_group",
    "entangled_surface",
    "degenerate_value",
    "human_rejected",
    "unverified",
)


@dataclass(frozen=True, slots=True)
class EligibilityReport:
    eligible: tuple[Atom, ...]
    excluded: tuple[tuple[Atom, str], ...]

    def rates(self) -> dict[str, float]:
        total = len(self.eligible) + len(self.excluded)
        if total == 0:
            return dict.fromkeys(EXCLUSION_REASONS, 0.0)
        counts: dict[str, int] = defaultdict(int)
        for _, reason in self.excluded:
            counts[reason] += 1
        return {r: counts[r] / total for r in EXCLUSION_REASONS}


def _conflict_ids(atoms: Sequence[Atom]) -> set[str]:
    """An atom is in a conflict group when the same canonical value is claimed
    by more than one role in the same document: presence would then be
    ambiguous and the availability edit ill-defined."""
    by_value: dict[str, set[str]] = defaultdict(set)
    for a in atoms:
        by_value[a.canonical_value].add(a.role.value)
    bad = {v for v, roles in by_value.items() if len(roles) > 1}
    return {a.atom_id for a in atoms if a.canonical_value in bad}


def _entangled(atom: Atom, frame_text: str) -> bool:
    """A surface form is entangled when deleting it cannot leave a
    well-formed sentence by the frozen mechanical rule: it is hyphen-joined to
    a neighbouring token, or it is the entire sentence."""
    s, e = atom.char_start, atom.char_end
    before = frame_text[max(0, s - 1) : s]
    after = frame_text[e : e + 1]
    if before == "-" or after == "-":
        return True
    return len(atom.surface_form.strip()) >= len(frame_text.strip())


def filter_eligible(
    atoms: Sequence[Atom],
    frame_text: str,
    *,
    require_human_verification: bool = True,
) -> EligibilityReport:
    conflicts = _conflict_ids(atoms)
    eligible: list[Atom] = []
    excluded: list[tuple[Atom, str]] = []
    for atom in atoms:
        if atom.atom_id in conflicts:
            excluded.append((atom, "conflict_group"))
        elif not atom.canonical_value.strip():
            excluded.append((atom, "degenerate_value"))
        elif _entangled(atom, frame_text):
            excluded.append((atom, "entangled_surface"))
        elif atom.verification is VerificationStatus.REJECTED:
            excluded.append((atom, "human_rejected"))
        elif require_human_verification and atom.verification is not VerificationStatus.ACCEPTED:
            excluded.append((atom, "unverified"))
        else:
            eligible.append(atom)
    return EligibilityReport(tuple(eligible), tuple(excluded))


REVIEW_COLUMNS = (
    "document_id",
    "atom_id",
    "role",
    "canonical_value",
    "surface_form",
    "char_start",
    "char_end",
    "occurrence_count",
    "local_context",
    "decision",
    "reviewer",
    "note",
)


def write_review_template(atoms: Iterable[Atom], path: Path) -> int:
    """Emit a blank human-verification sheet. ``decision`` is filled by a human
    with accepted/rejected; nothing else in the file should be edited."""
    rows = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for atom in atoms:
            writer.writerow(
                {
                    "document_id": atom.document_id,
                    "atom_id": atom.atom_id,
                    "role": atom.role.value,
                    "canonical_value": atom.canonical_value,
                    "surface_form": atom.surface_form,
                    "char_start": atom.char_start,
                    "char_end": atom.char_end,
                    "occurrence_count": atom.occurrence_count,
                    "local_context": atom.local_context.replace("\n", " "),
                    "decision": "",
                    "reviewer": "",
                    "note": "",
                }
            )
            rows += 1
    return rows


def apply_review(atoms: Sequence[Atom], path: Path) -> list[Atom]:
    decisions: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            decisions[row["atom_id"]] = (row.get("decision") or "").strip().lower()
    out: list[Atom] = []
    for atom in atoms:
        d = decisions.get(atom.atom_id, "")
        if d == "accepted":
            out.append(replace(atom, verification=VerificationStatus.ACCEPTED))
        elif d == "rejected":
            out.append(replace(atom, verification=VerificationStatus.REJECTED))
        else:
            out.append(atom)
    return out


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Inter-rater agreement for the atomizer calibration set."""
    if len(a) != len(b) or not a:
        raise ValueError("rating vectors must be non-empty and equal length")
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
    expected = sum(
        (sum(1 for x in a if x == lab) / n) * (sum(1 for y in b if y == lab) / n) for lab in labels
    )
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)
