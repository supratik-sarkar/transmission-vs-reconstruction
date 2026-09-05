"""Typed orchestration state.

Carries REFERENCES and SUMMARIES between nodes. It is not a scientific record:
canonical evidence remains the artifact ledger and RESULTS_MANIFEST.json, and
this object is discarded when the run ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..app_contracts.events import EventLog
from ..app_contracts.modes import AppMode, RunKind
from ..models import Atom, AtomCausalRecord, FocalSelection, SourceFrame
from ..providers.ledger import ProviderLedger


@dataclass(slots=True)
class RunState:
    run_id: str
    mode: AppMode
    kind: RunKind
    budget: int
    seed: int

    source_frame: SourceFrame | None = None
    atoms: tuple[Atom, ...] = ()
    eligible: tuple[Atom, ...] = ()
    focals: tuple[FocalSelection, ...] = ()
    relay_message: str = ""
    transmission: dict[str, int] = field(default_factory=dict)
    natural_outcomes: dict[str, int] = field(default_factory=dict)
    counterfactual_messages: dict[str, str] = field(default_factory=dict)
    counterfactual_outcomes: dict[str, int] = field(default_factory=dict)
    edit_mechanisms: dict[str, str] = field(default_factory=dict)
    records: tuple[AtomCausalRecord, ...] = ()
    decomposition: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failed_edits: dict[str, str] = field(default_factory=dict)

    events: EventLog = field(default_factory=lambda: EventLog("unset"))
    ledger: ProviderLedger = field(default_factory=ProviderLedger)
    tracer: Any = None

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode.value,
            "kind": self.kind.value,
            "budget": self.budget,
            "n_atoms": len(self.atoms),
            "n_eligible": len(self.eligible),
            "n_focals": len(self.focals),
            "n_records": len(self.records),
            "n_events": len(self.events),
            "n_provider_calls": len(self.ledger),
            "n_failed_edits": len(self.failed_edits),
            "warnings": list(self.warnings),
        }
