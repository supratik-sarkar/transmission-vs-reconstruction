"""Frozen pre-treatment source-side features.

Everything here is computable from the source frame alone, before the relay
runs and before any receiver is queried. That is the containment property that
makes CausalRelay deployable: at test time the policy sees only the document.

FORBIDDEN as features, enforced by ``assert_pretreatment``:
  final-test receiver outcomes, availability interventions, R^-, D^+, Delta,
  matched-skeleton outcomes, and any label derived from them.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Atom, AtomRole, SourceFrame

FEATURE_SCHEMA_VERSION = "srcfeat-v1"

FEATURE_NAMES: tuple[str, ...] = (
    "role_entity",
    "role_scope",
    "role_period",
    "role_numeric",
    "role_provenance",
    "relative_position",
    "sentence_index_norm",
    "canonical_char_len",
    "canonical_token_len_est",
    "occurrence_count",
    "log_occurrence_count",
    "redundancy_share",
    "local_digit_density",
    "local_context_len",
    "is_first_sentence",
    "is_last_quartile",
    "numeric_is_pct",
    "numeric_is_currency",
    "distinct_roles_in_sentence",
)

FORBIDDEN_FEATURE_TOKENS: tuple[str, ...] = (
    "r_minus",
    "d_plus",
    "delta",
    "surplus_label",
    "receiver",
    "recovered",
    "y_obs",
    "outcome",
    "intervention",
    "transmitted",
    "skeleton",
)


class FeatureLeakError(AssertionError):
    pass


def assert_pretreatment(names: Sequence[str]) -> None:
    lowered = [n.casefold() for n in names]
    for name in lowered:
        for bad in FORBIDDEN_FEATURE_TOKENS:
            if bad in name:
                raise FeatureLeakError(
                    f"feature {name!r} looks like a post-treatment quantity; CausalRelay "
                    "may use only frozen pre-treatment source-side features"
                )


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    names: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    atom_ids: tuple[str, ...]
    document_ids: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.rows)


def _digit_density(text: str) -> float:
    if not text:
        return 0.0
    return sum(c.isdigit() for c in text) / len(text)


def extract(frame: SourceFrame, atoms: Sequence[Atom]) -> FeatureMatrix:
    assert_pretreatment(FEATURE_NAMES)
    n_chars = max(1, len(frame.text))
    total_occ = max(1, sum(a.occurrence_count for a in atoms))
    per_sentence: dict[int, set[str]] = {}
    for a in atoms:
        per_sentence.setdefault(a.sentence_index, set()).add(a.role.value)
    max_sentence = max((a.sentence_index for a in atoms), default=0) or 1

    rows: list[tuple[float, ...]] = []
    ids: list[str] = []
    docs: list[str] = []
    for atom in sorted(atoms, key=lambda a: a.atom_id):
        subtype = str(atom.metadata.get("subtype", ""))
        rel = atom.char_start / n_chars
        rows.append(
            (
                float(atom.role is AtomRole.ENTITY),
                float(atom.role is AtomRole.SCOPE),
                float(atom.role is AtomRole.PERIOD),
                float(atom.role is AtomRole.NUMERIC),
                float(atom.role is AtomRole.PROVENANCE),
                rel,
                atom.sentence_index / max_sentence,
                float(len(atom.canonical_value)),
                float(max(1, len(atom.canonical_value.split()))),
                float(atom.occurrence_count),
                math.log1p(atom.occurrence_count),
                atom.occurrence_count / total_occ,
                _digit_density(atom.local_context),
                float(len(atom.local_context)),
                float(atom.sentence_index == 0),
                float(rel >= 0.75),
                float(subtype == "pct"),
                float(subtype == "currency"),
                float(len(per_sentence.get(atom.sentence_index, ()))),
            )
        )
        ids.append(atom.atom_id)
        docs.append(atom.document_id)
    return FeatureMatrix(FEATURE_NAMES, tuple(rows), tuple(ids), tuple(docs))


def schema_hash() -> str:
    return hashlib.sha256(
        (FEATURE_SCHEMA_VERSION + "|" + "|".join(FEATURE_NAMES)).encode("utf-8")
    ).hexdigest()
