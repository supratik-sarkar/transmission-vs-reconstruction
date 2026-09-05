"""The canonical run-event envelope.

One shape, one schema version, monotonic sequence numbers. The frontend renders
these and nothing else; it never recomputes a scientific quantity from them.

Reconnect replays from the canonical store. A gap in the sequence is surfaced as
a gap -- it is never interpolated, because an invented event would look exactly
like a real one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

EVENT_SCHEMA_VERSION = "1.0.0"


class Stage(StrEnum):
    PREPARE_RUN = "prepare_run"
    LOAD_SOURCE = "load_source"
    ATOMIZE = "atomize"
    SAMPLE_FOCALS = "sample_focals"
    RELAY = "relay"
    MATCH_TRANSMISSION = "match_transmission"
    NATURAL_RECEIVER = "natural_receiver"
    CONSTRUCT_INTERVENTIONS = "construct_interventions"
    COUNTERFACTUAL_RECEIVER = "counterfactual_receiver"
    DETERMINISTIC_MATCH = "deterministic_match"
    ESTIMATE = "estimate"
    EXPORT_ARTIFACTS = "export_artifacts"
    FINALIZE_RUN = "finalize_run"


#: The fixed scientific topology. Declared once, here, and asserted by the
#: orchestrator. No component may reorder or skip it.
STAGE_ORDER: tuple[Stage, ...] = (
    Stage.PREPARE_RUN,
    Stage.LOAD_SOURCE,
    Stage.ATOMIZE,
    Stage.SAMPLE_FOCALS,
    Stage.RELAY,
    Stage.MATCH_TRANSMISSION,
    Stage.NATURAL_RECEIVER,
    Stage.CONSTRUCT_INTERVENTIONS,
    Stage.COUNTERFACTUAL_RECEIVER,
    Stage.DETERMINISTIC_MATCH,
    Stage.ESTIMATE,
    Stage.EXPORT_ARTIFACTS,
    Stage.FINALIZE_RUN,
)


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    STAGE_STARTED = "stage.started"
    STAGE_PROGRESS = "stage.progress"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    ARTIFACT_WRITTEN = "artifact.written"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class EventStatus(StrEnum):
    OK = "ok"
    RUNNING = "running"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    kind: str  # table | figure | json | jsonl | csv | tex | svg | pdf
    path: str  # relative; never an absolute host path
    sha256: str
    bytes: int = 0


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str
    sequence: int
    stage: Stage
    event_type: EventType
    status: EventStatus
    payload: dict[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[ArtifactRef, ...] = ()
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    schema_version: str = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stage"] = self.stage.value
        d["event_type"] = self.event_type.value
        d["status"] = self.status.value
        d["artifact_refs"] = [asdict(a) for a in self.artifact_refs]
        return d

    def to_sse(self) -> str:
        return (
            f"id: {self.sequence}\nevent: {self.event_type.value}\n"
            f"data: {json.dumps(self.to_dict(), separators=(',', ':'))}\n\n"
        )


class SequenceError(AssertionError):
    pass


class EventLog:
    """Append-only, strictly monotonic, replayable.

    Canonical for the UI stream. It is NOT canonical scientific evidence -- that
    remains the artifact ledger and RESULTS_MANIFEST.json.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: list[RunEvent] = []

    def __len__(self) -> int:
        return len(self._events)

    @property
    def next_sequence(self) -> int:
        return len(self._events) + 1

    def append(
        self,
        stage: Stage,
        event_type: EventType,
        status: EventStatus,
        payload: dict[str, Any] | None = None,
        artifact_refs: Iterable[ArtifactRef] = (),
    ) -> RunEvent:
        event = RunEvent(
            run_id=self.run_id,
            sequence=self.next_sequence,
            stage=stage,
            event_type=event_type,
            status=status,
            payload=dict(payload or {}),
            artifact_refs=tuple(artifact_refs),
        )
        self._events.append(event)
        return event

    def replay(self, after_sequence: int = 0) -> Iterator[RunEvent]:
        """Events strictly after ``after_sequence``, in order.

        A reconnecting client sends its last sequence and receives exactly what
        it missed. Nothing is synthesised to fill a gap.
        """
        if after_sequence < 0:
            raise SequenceError("after_sequence must be non-negative")
        yield from (e for e in self._events if e.sequence > after_sequence)

    def all(self) -> tuple[RunEvent, ...]:
        return tuple(self._events)

    def assert_monotonic(self) -> None:
        for i, event in enumerate(self._events, start=1):
            if event.sequence != i:
                raise SequenceError(
                    f"sequence {event.sequence} at position {i}: the log is not monotonic"
                )

    def assert_topology(self) -> None:
        """Observed stages must be a prefix-consistent subsequence of the frozen
        order. Catches a reordered or injected stage."""
        seen = [e.stage for e in self._events if e.event_type is EventType.STAGE_STARTED]
        index = {s: i for i, s in enumerate(STAGE_ORDER)}
        last = -1
        for stage in seen:
            pos = index[stage]
            if pos <= last:
                raise SequenceError(f"stage {stage.value!r} started out of frozen topology order")
            last = pos
