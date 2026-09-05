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
    extra: dict[str, Any] = field(default_factory=dict)

    def unresolved(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if getattr(self, f) in (None, "")]

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

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> Registry:
        entries: dict[str, BaselineEntry] = {}
        for name, body in (payload.get("baselines") or {}).items():
            entries[name] = BaselineEntry(name=name, **body)
        return cls(entries)

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
