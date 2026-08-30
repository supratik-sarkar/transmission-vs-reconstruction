from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AtomRole(StrEnum):
    ENTITY = "entity"
    SCOPE = "scope"
    PERIOD = "period"
    NUMERIC = "numeric"
    PROVENANCE = "provenance"


class Atom(BaseModel):
    document_id: str
    atom_id: str
    role: AtomRole
    value: str
    canonical_value: str
    source_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FocalSelection(BaseModel):
    document_id: str
    atom_id: str
    role: AtomRole
    pi: float = Field(gt=0, le=1)
    stratum_size: int = Field(gt=0)
    populated_strata: int = Field(ge=3)


class ReceiverOutcome(BaseModel):
    document_id: str
    atom_id: str
    availability: int = Field(ge=0, le=1)
    recovered: int = Field(ge=0, le=1)
    raw_output: str | None = None


class AtomCausalRecord(BaseModel):
    document_id: str
    atom_id: str
    role: AtomRole
    pi: float = Field(gt=0, le=1)
    transmitted: int = Field(ge=0, le=1)
    r_minus: float = Field(ge=0, le=1)
    d_plus: float = Field(ge=0, le=1)

    @property
    def delta_avail(self) -> float:
        return self.d_plus - self.r_minus


class GateResult(BaseModel):
    reconstruction_contribution: float
    prior_effects: dict[str, float]
    reconstruction_gate: float
    prior_gate: float
    eligible_prior_classes: list[str]
    proceed: bool
    reason: str


class FreezeRecord(BaseModel):
    preregistration_sha256: str
    artifact_manifest_sha256: str
    source_pool_sha256: str
    git_commit: str
    frozen_utc: str
    relay_model: str
    receiver_model: str


@dataclass(frozen=True)
class ArtifactHash:
    path: Path
    sha256: str
