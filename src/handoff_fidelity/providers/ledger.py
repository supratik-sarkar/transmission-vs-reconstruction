"""Append-only provider-call ledger.

Every attempt is recorded, including failures and retries, so a run's provider
history is reconstructable. Content is HASHED here; raw prompts and responses
live in the private workspace and never enter the public repository or the
browser.

The ledger is JSONL and append-only: rewriting history would defeat its purpose.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .redaction import assert_no_secret, redact

LEDGER_SCHEMA_VERSION = "1.0.0"


class CallStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    REFUSED = "REFUSED"
    CACHED = "CACHED"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderCall:
    call_id: str
    run_id: str
    provider: str
    requested_model: str
    attempt: int
    started_at: str
    completed_at: str
    latency_s: float
    status: CallStatus
    prompt_hash: str
    request_hash: str
    response_hash: str = ""
    returned_model: str = ""
    provider_request_id: str = ""
    input_tokens: int = -1
    output_tokens: int = -1
    error_class: str = ""
    cache_hit: bool = False
    config_hash: str = ""
    stage: str = ""
    schema_version: str = LEDGER_SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        # Defence in depth: `extra` is provider-specific and the least
        # predictable field on this record.
        d["extra"] = redact(d["extra"])
        return d


class ProviderLedger:
    """Append-only JSONL writer.

    ``path=None`` keeps the ledger in memory, which is what the mock pipeline and
    the tests use.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._records: list[ProviderCall] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def __len__(self) -> int:
        return len(self._records)

    def append(self, call: ProviderCall) -> ProviderCall:
        payload = call.to_dict()
        # Fail closed: a leaked credential must stop the run, not be written.
        assert_no_secret(payload, context="provider ledger record")
        self._records.append(call)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
        return call

    def records(self) -> tuple[ProviderCall, ...]:
        return tuple(self._records)

    def for_run(self, run_id: str) -> Iterator[ProviderCall]:
        yield from (r for r in self._records if r.run_id == run_id)

    def summary(self) -> dict[str, Any]:
        by_provider: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in self._records:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        return {
            "total_calls": len(self._records),
            "by_provider": dict(sorted(by_provider.items())),
            "by_status": dict(sorted(by_status.items())),
            "input_tokens": sum(max(0, r.input_tokens) for r in self._records),
            "output_tokens": sum(max(0, r.output_tokens) for r in self._records),
            "retries": sum(1 for r in self._records if r.attempt > 1),
        }


def new_call_id(run_id: str, stage: str, sequence: int) -> str:
    return f"{run_id}:{stage}:{sequence:06d}"


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
