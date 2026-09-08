"""Immutable baseline registry.

Records, for every external method, exactly what the protocol requires to be
recorded before a benchmark number may be produced. Fields whose true value is
not yet known are ``None`` and validation reports them as unresolved -- they are
never guessed, because a fabricated commit hash would make the whole
reproducibility chain a fiction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_FIELDS: tuple[str, ...] = (
    "paper_citation_key",
    "official_repository",
    "commit",
    "release_tag",
    "checkpoint_revision",
    "licence",
    "python_requirement",
    "install_command",
    "native_benchmark",
    "native_expected_metric",
    "reproduction_tolerance",
)

#: Absolute metric difference allowed against the published number, or overlap
#: with the published interval when one is given.
DEFAULT_TOLERANCE_PP = 2.0

#: Written into a REQUIRED field when the field is genuinely inapplicable rather
#: than merely unknown -- for example a method whose inference code ships inside
#: its checkpoint repository, so that there is no upstream commit to pin.
#:
#: The sentinel only counts as resolved when the matching ``<field>_not_required_reason``
#: is also present. Without that, it is indistinguishable from a placeholder
#: someone typed to make a gate go green, and it is reported as unresolved.
RESOLVED_AS_INAPPLICABLE = "NOT_REQUIRED"


@dataclass(slots=True)
class BaselineEntry:
    name: str
    role: str
    status: str = "NOT_READY"
    produces_text: bool = True
    paper_citation_key: str | None = None
    official_repository: str | None = None
    commit: str | None = None
    release_tag: str | None = None
    checkpoint_revision: str | None = None
    licence: str | None = None
    python_requirement: str | None = None
    install_command: str | None = None
    native_benchmark: str | None = None
    native_expected_metric: float | None = None
    native_reproduced_metric: float | None = None
    reproduction_tolerance: float | None = DEFAULT_TOLERANCE_PP
    reproduction_deviation: float | None = None
    counts_toward_superiority: bool = False
    notes: str = ""

    # ---- resolution provenance -------------------------------------------
    # Populated by the Phase-3 documentation pass. Every one of these records
    # either an official fact or the reason an official fact could not be had.
    method_family: str | None = None
    code_licence: str | None = None
    commit_signature: str | None = None
    commit_not_required_reason: str = ""
    commit_unresolved_reason: str = ""
    checkpoint: str | None = None
    checkpoint_last_modified: str | None = None
    checkpoint_parameters: int | None = None
    checkpoint_weight_format: str | None = None
    checkpoint_unresolved_reason: str = ""
    tokenizer: str | None = None
    tokenizer_revision: str | None = None
    licence_unresolved_reason: str = ""
    licence_conflict: str = ""
    context_length: int | None = None
    artefact_kind: str | None = None
    base_model_required: bool = False
    memory_note: str = ""
    requires_trust_remote_code: bool = False
    runtime_network_dependency: str = ""
    data_provenance_risk: str = ""
    mps_evidence: str = ""
    nearest_published_artefact: str | None = None
    nearest_published_revision: str | None = None
    nearest_published_licence: str | None = None
    nearest_published_parameters: int | None = None
    blocking_recommendation: str = ""

    # ---- pre-outcome amendment bookkeeping (P-6) -------------------------
    added_on: str | None = None
    replaces: str | None = None
    retired_on: str | None = None
    retired_reason: str = ""
    replaced_by: str | None = None
    retention_reason: str = ""
    promotion_rule: str = ""
    promotion_permitted_reasons: list[str] = field(default_factory=list)

    # ---- provenance and feasibility --------------------------------------
    paper_title: str | None = None
    venue: str | None = None
    arxiv: str | None = None
    alternative_release: str | None = None
    pypi_package: str | None = None
    pypi_version: str | None = None
    base_model: str | None = None
    base_model_revision: str | None = None
    checkpoint_not_required_reason: str = ""
    licence_evidence: str = ""
    licence_caveat: str = ""
    python_requirement_note: str = ""
    dependency_pinning_risk: str = ""
    repository_inconsistency: str = ""
    budget_semantics: str | None = None
    budget_adapter_required: bool = False
    budget_adapter_note: str = ""
    cpu_feasibility: str | None = None
    mps_feasibility: str | None = None
    feasibility_note: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    def unresolved(self) -> list[str]:
        out: list[str] = []
        for f in REQUIRED_FIELDS:
            value = getattr(self, f)
            if value in (None, ""):
                out.append(f)
            elif value == RESOLVED_AS_INAPPLICABLE and not getattr(
                self, f"{f}_not_required_reason", ""
            ):
                # A bare sentinel is a placeholder, not a resolution.
                out.append(f)
        return out

    def benchmark_eligible(self) -> tuple[bool, str]:
        # Controls are ours: there is no upstream repository to pin and no
        # published number to reproduce. Judging them by the external-method
        # criteria would report a permanent, meaningless failure.
        if self.role == "CONTROL":
            if self.status != "READY":
                return False, f"control adapter status is {self.status}"
            return True, "control"
        if self.role == "ENDPOINT_ONLY":
            return False, "endpoint-only: T_z is undefined for a latent compressed state"
        if self.role == "RETIRED_PRE_OUTCOME":
            return False, (
                f"retired pre-outcome on {self.retired_on or 'an unrecorded date'}"
                f"{': ' + self.retired_reason.strip() if self.retired_reason else ''}"
            )
        if self.role == "CONTINGENCY_CAUSAL":
            return False, (
                "contingency comparator: not benchmark-eligible while it holds this "
                "role, and never counts toward the superiority headline. Promotion "
                "requires a pre-outcome amendment naming one of "
                f"{self.promotion_permitted_reasons or ['(none declared)']}."
            )
        missing = self.unresolved()
        if missing:
            return False, f"unresolved registry fields: {', '.join(missing)}"
        if self.status != "READY":
            return False, f"adapter status is {self.status}"
        if not self.produces_text:
            return False, "compressed state is not textual: endpoint-only"
        if self.native_reproduced_metric is None:
            return False, "native reproduction not run"
        if self.reproduction_deviation is None:
            return False, "reproduction deviation not computed"
        tol = self.reproduction_tolerance or DEFAULT_TOLERANCE_PP
        if abs(self.reproduction_deviation) > tol:
            return False, (
                f"reproduction deviation {self.reproduction_deviation:.3f} exceeds "
                f"tolerance {tol:.3f}: report as UNREPRODUCED, do not replace the method"
            )
        return True, "eligible"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Registry:
    entries: dict[str, BaselineEntry]
    resolution_date: str = ""
    method_families: dict[str, list[str]] = field(default_factory=dict)
    amendments: list[dict[str, Any]] = field(default_factory=list)
    superiority: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> Registry:
        entries: dict[str, BaselineEntry] = {}
        for name, body in (payload.get("baselines") or {}).items():
            entries[name] = BaselineEntry(name=name, **body)
        return cls(
            entries,
            resolution_date=str(payload.get("resolution_date") or ""),
            method_families=dict(payload.get("method_families") or {}),
            amendments=list(payload.get("amendments") or []),
            superiority=dict(payload.get("superiority") or {}),
        )

    def family_map(self) -> dict[str, str]:
        """method name -> declared family label.

        The per-entry ``method_family`` field and the top-level
        ``method_families`` block must agree; the top-level block wins, because
        it is the one a reader can scan for accidental merges.
        """
        declared = {m: fam for fam, members in self.method_families.items() for m in members}
        for name, entry in self.entries.items():
            if entry.method_family and name not in declared:
                declared[name] = entry.method_family
        return declared

    def families_of(self, names: list[str]) -> set[str]:
        """Distinct method families spanned by `names`.

        Wins over comparators that share a backbone and a training pipeline are
        not independent tests. A comparator with no declared family counts as
        its own family rather than being merged into someone else's.
        """
        declared = self.family_map()
        return {declared.get(n) or n for n in names}

    def headline_eligible(self) -> tuple[bool, str]:
        """Whether the field is broad enough for a SOTA-superiority headline (P-7).

        Checked on BENCHMARK_READY primaries only. A narrow field is a design
        limitation to report, not a comparison that was lost.
        """
        required = int(self.superiority.get("required_distinct_families", 3))
        ready = self.eligible_primary()
        families = self.families_of(ready)
        if len(families) >= required:
            return True, f"{len(families)} distinct families available: {sorted(families)}"
        return False, (
            f"NO SOTA-SUPERIORITY HEADLINE: {len(families)} distinct BENCHMARK_READY "
            f"method families ({sorted(families) or 'none'}), {required} required"
        )

    @classmethod
    def load(cls, path: Path) -> Registry:
        import yaml  # noqa: PLC0415 - optional at import time

        return cls.from_mapping(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    def eligible_primary(self) -> list[str]:
        out = []
        for name, entry in sorted(self.entries.items()):
            if entry.role != "PRIMARY_CAUSAL":
                continue
            ok, _ = entry.benchmark_eligible()
            if ok:
                out.append(name)
        return out

    def superiority_denominator(self) -> int:
        """Number of PRIMARY SOTA comparators. The legacy anchor is excluded by
        construction."""
        return sum(1 for e in self.entries.values() if e.role == "PRIMARY_CAUSAL")

    def report(self) -> list[dict[str, Any]]:
        rows = []
        for name, entry in sorted(self.entries.items()):
            ok, reason = entry.benchmark_eligible()
            rows.append(
                {
                    "method": name,
                    "role": entry.role,
                    "status": entry.status,
                    "eligible": ok,
                    "reason": reason,
                    "unresolved_fields": entry.unresolved(),
                }
            )
        return rows
