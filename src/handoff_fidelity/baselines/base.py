"""The common compressor adapter interface.

Every textual compressor -- controls, external SOTA and CausalRelay -- is
wrapped behind:

    compress(source_text, downstream_task, token_budget, config) -> HandoffResult

Two invariants are enforced here rather than trusted:

  * BUDGET. Every adapter verifies the realised output against the hard
    ceiling. No method gets a larger effective context because its native
    tokenizer differs.
  * FOCAL SECRECY. Focal atom identities and values never enter a compressor
    prompt or configuration. Otherwise focal sampling becomes supervision for
    query-aware methods.

Adapter status is explicit. A method that is not installed and reproduced is
NOT_READY and reports as such; it is never approximated and labelled SOTA.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from ..models import HandoffResult
from ..relay.task import assert_no_focal_leak


class AdapterStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    UNREPRODUCED = "UNREPRODUCED"
    ENDPOINT_ONLY = "ENDPOINT_ONLY"


class BenchmarkRole(StrEnum):
    CONTROL = "CONTROL"
    PRIMARY_CAUSAL = "PRIMARY_CAUSAL"
    LEGACY_ANCHOR = "LEGACY_ANCHOR"
    ENDPOINT_ONLY = "ENDPOINT_ONLY"
    OURS = "OURS"


class AdapterNotReady(RuntimeError):
    """Raised when a comparator is invoked before its installation and
    reproduction gates have passed. Deliberately fatal: producing a plausible
    approximation and calling it SOTA would misrepresent the benchmark."""


class BudgetViolation(AssertionError):
    pass


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class Compressor(Protocol):
    name: str
    revision: str
    status: AdapterStatus
    role: BenchmarkRole

    def compress(
        self,
        source_text: str,
        downstream_task: str,
        token_budget: int,
        config: dict[str, Any] | None = None,
        *,
        focal_values: Sequence[str] = (),
        enforce_budget: bool = True,
    ) -> HandoffResult: ...


@dataclass(slots=True)
class BaseCompressor:
    name: str
    revision: str
    status: AdapterStatus
    role: BenchmarkRole
    tokenizer: Any = None
    produces_text: bool = True

    # -- subclasses implement this ----------------------------------------
    def _compress(
        self, source_text: str, downstream_task: str, token_budget: int, config: dict[str, Any]
    ) -> tuple[str, tuple[str, ...]]:
        raise NotImplementedError

    def compress(
        self,
        source_text: str,
        downstream_task: str,
        token_budget: int,
        config: dict[str, Any] | None = None,
        *,
        focal_values: Sequence[str] = (),
        enforce_budget: bool = True,
    ) -> HandoffResult:
        cfg = dict(config or {})
        if self.status is AdapterStatus.NOT_READY:
            raise AdapterNotReady(
                f"{self.name} is NOT_READY: install the official implementation, pin its "
                "revision, and pass the reproduction gate before benchmarking it."
            )
        if focal_values:
            assert_no_focal_leak(downstream_task, list(focal_values))
            assert_no_focal_leak(json.dumps(cfg, sort_keys=True, default=str), list(focal_values))

        started = time.perf_counter()
        text, warnings = self._compress(source_text, downstream_task, token_budget, cfg)
        elapsed = time.perf_counter() - started

        out_tokens = self.tokenizer.count(text) if self.tokenizer else -1
        in_tokens = self.tokenizer.count(source_text) if self.tokenizer else -1
        if enforce_budget and self.tokenizer and out_tokens > token_budget:
            raise BudgetViolation(
                f"{self.name} produced {out_tokens} tokens against a hard budget of "
                f"{token_budget}. The budget adapter must be calibrated on development "
                "data before the final test."
            )
        return HandoffResult(
            text=text,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_s=elapsed,
            method=self.name,
            revision=self.revision,
            configuration_hash=config_hash(cfg),
            warnings=warnings,
            budget=token_budget,
        )
