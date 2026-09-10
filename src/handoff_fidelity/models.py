"""Core record types.

Deliberately stdlib-only (dataclasses, not pydantic) so that the scientific
core can be imported, executed and tested without any third-party runtime.
Heavier dependencies are confined to optional adapters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AtomRole(StrEnum):
    """Tier-1 roles. Tier-2 (relation strength, certainty, counterevidence) is
    deliberately excluded from the causal core: those atoms are paraphrasable,
    so presence detection would require a model judge inside the primary
    outcome."""

    ENTITY = "entity"
    SCOPE = "scope"
    PERIOD = "period"
    NUMERIC = "numeric"
    PROVENANCE = "provenance"


TIER1_ROLES: tuple[AtomRole, ...] = (
    AtomRole.ENTITY,
    AtomRole.SCOPE,
    AtomRole.PERIOD,
    AtomRole.NUMERIC,
    AtomRole.PROVENANCE,
)


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class SourceFrame:
    """The relay-visible source window.

    Everything downstream -- atomizer, eligibility filter, focal sampler and
    every compressor -- operates on exactly ``text``. No atom may exist outside
    it, because an atom the compressor never saw cannot be a transmission
    failure.
    """

    document_id: str
    text: str
    token_count: int
    tokenizer: str
    window_tokens: int
    truncated: bool
    sha256: str
    section: str = "mdna"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Atom:
    document_id: str
    atom_id: str
    role: AtomRole
    canonical_value: str
    surface_form: str
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    local_context: str
    sentence_index: int
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    occurrence_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        d["verification"] = self.verification.value
        return d


@dataclass(frozen=True, slots=True)
class FocalSelection:
    """One sampled focal atom together with its first-order inclusion
    probability under the fixed-size role-stratified design."""

    document_id: str
    atom_id: str
    role: AtomRole
    pi: float
    stratum_size: int
    populated_strata: int
    k: int


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Uniform return type for every compressor/relay adapter."""

    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    method: str
    revision: str
    configuration_hash: str
    warnings: tuple[str, ...] = ()
    budget: int | None = None

    @property
    def within_budget(self) -> bool:
        return self.budget is None or self.output_tokens <= self.budget


@dataclass(frozen=True, slots=True)
class AtomCausalRecord:
    """One focal atom, fully instrumented.

    ``r_minus`` and ``d_plus`` are on the mean-response scale; under decoder
    regime (D) they are {0,1}-valued, under (S) they are unbiased single draws
    (or means of ``m`` draws).
    """

    document_id: str
    atom_id: str
    role: AtomRole
    pi: float
    transmitted: int
    r_minus: float
    d_plus: float
    method: str = "natural"
    q: float = 1.0
    edit_mechanism: str = ""
    eligible: bool = True

    @property
    def delta_avail(self) -> float:
        return self.d_plus - self.r_minus

    @property
    def y_obs(self) -> float:
        return self.d_plus if self.transmitted == 1 else self.r_minus

    @property
    def sign(self) -> int:
        """s = 2T - 1. Deletion (T=1) and insertion (T=0) require opposite
        offsets when correcting for the editor's mechanical artefact."""
        return 2 * self.transmitted - 1


@dataclass(frozen=True, slots=True)
class BudgetNeutralRecord:
    """Experiment C: matched-length insert/evict swap."""

    document_id: str
    atom_id: str
    role: AtomRole
    transmitted: int
    delta_budget: float
    rendered_tokens: int
    evicted_atom_id: str | None = None
    value: float = 1.0


@dataclass(frozen=True, slots=True)
class MatchedSkeletonRecord:
    """Experiment B: one focal slot under a common skeleton H_{-z}, focal atom
    absent in BOTH arms."""

    document_id: str
    slot_id: str
    role: AtomRole
    natural_recovered: int
    blocked_recovered: int
    k_eff: int
    prior_probe: float | None = None
    t_bar_natural: float | None = None
    t_bar_blocked: float | None = None

    @property
    def paired_difference(self) -> int:
        return self.natural_recovered - self.blocked_recovered


@dataclass(frozen=True, slots=True)
class GateResult:
    reconstruction_contribution: float
    prior_effects: dict[str, float | None]
    reconstruction_gate: float
    prior_gate: float
    eligible_prior_classes: tuple[str, ...]
    proceed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class FreezeRecord:
    kind: str
    preregistration_sha256: str
    artifact_manifest_sha256: str
    source_pool_sha256: str
    git_commit: str
    frozen_utc: str
    relay_model: str
    receiver_model: str
    extra: dict[str, str] = field(default_factory=dict)
