"""Read model for the API.

The API is READ-ONLY over canonical artifacts, plus synthetic demo runs. It
never recomputes a scientific quantity: everything served here was produced by
the scientific core and is passed through unchanged.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from handoff_fidelity.orchestration.mock_pipeline import MockRunResult


@dataclass(slots=True)
class RunRecord:
    run_id: str
    kind: str
    mode: str
    status: str
    marker: str
    summary: dict[str, Any]
    decomposition: dict[str, Any]
    events: list[dict[str, Any]]
    atoms: list[dict[str, Any]]
    provider_calls: dict[str, Any]
    spans: list[str]
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    relay_message: str = ""
    counterfactuals: dict[str, str] = field(default_factory=dict)
    evidentiary_status: str = "NONE"

    def index_entry(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "mode": self.mode,
            "status": self.status,
            "marker": self.marker,
            "evidentiary_status": self.evidentiary_status,
            "n_atoms": self.summary.get("n_atoms", 0),
            "n_records": self.summary.get("n_records", 0),
        }


class RunStore:
    """In-memory index. NOT canonical evidence -- a UI accelerator that must be
    rebuildable from artifacts at any time."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()

    def put(self, record: RunRecord) -> RunRecord:
        with self._lock:
            self._runs[record.run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list(self) -> list[dict[str, Any]]:
        return [r.index_entry() for r in sorted(self._runs.values(), key=lambda r: r.run_id)]

    def events_after(self, run_id: str, sequence: int) -> list[dict[str, Any]]:
        record = self.get(run_id)
        if record is None:
            return []
        return [e for e in record.events if int(e["sequence"]) > sequence]


def record_from_mock(result: MockRunResult) -> RunRecord:
    state = result.state
    focal_ids = {f.atom_id for f in state.focals}
    records = {r.atom_id: r for r in state.records}

    atoms: list[dict[str, Any]] = []
    for atom in state.eligible:
        rec = records.get(atom.atom_id)
        focal = atom.atom_id in focal_ids
        atoms.append(
            {
                "atom_id": atom.atom_id,
                "role": atom.role.value,
                "canonical_value": atom.canonical_value,
                "surface_form": atom.surface_form,
                "char_start": atom.char_start,
                "char_end": atom.char_end,
                "focal": focal,
                # Absent quantities are explicitly typed, never zero-filled: a zero
                # and an unmeasured value must not look alike.
                "transmitted": (
                    state.transmission.get(atom.atom_id)
                    if atom.atom_id in state.transmission
                    else None
                ),
                "inclusion_probability": next(
                    (f.pi for f in state.focals if f.atom_id == atom.atom_id), None
                ),
                "r_minus": rec.r_minus if rec else None,
                "d_plus": rec.d_plus if rec else None,
                "delta_avail": rec.delta_avail if rec else None,
                "edit_mechanism": rec.edit_mechanism if rec else None,
                "status": ("ESTIMATED" if rec else "NOT_ESTIMATED" if focal else "NOT_APPLICABLE"),
            }
        )

    return RunRecord(
        run_id=state.run_id,
        kind=state.kind.value,
        mode=state.mode.value,
        status="COMPLETED",
        marker=result.marker,
        summary=state.summary(),
        decomposition=state.decomposition,
        events=[e.to_dict() for e in state.events.all()],
        atoms=atoms,
        provider_calls=state.ledger.summary(),
        spans=list(getattr(state.tracer, "names", list)()),
        relay_message=state.relay_message,
        counterfactuals=dict(state.counterfactual_messages),
        evidentiary_status="NONE",
    )
