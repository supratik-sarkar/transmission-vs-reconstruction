"""Benchmark orchestration.

Separates PRIMARY_CAUSAL from ENDPOINT_ONLY comparators at the type level, so a
latent-state method cannot accidentally populate a T_z column.

Every method sees the same relay-visible source, the same frozen downstream
task, the same receiver, the same tokenizer and the same budget. Focal atoms are
never passed to any compressor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..baselines.base import AdapterStatus, BenchmarkRole, Compressor
from ..models import HandoffResult
from ..relay.task import GLOBAL_DOWNSTREAM_TASK


class EndpointOnlyMisuse(AssertionError):
    """Raised when an endpoint-only method is asked for a causal quantity."""


@dataclass(slots=True)
class MethodRun:
    method: str
    role: BenchmarkRole
    handoff: HandoffResult
    causal_metrics_allowed: bool


@dataclass(slots=True)
class BenchmarkPlan:
    budget: int
    methods: dict[str, Compressor]
    downstream_task: str = GLOBAL_DOWNSTREAM_TASK
    focal_values: tuple[str, ...] = ()
    warnings: list[str] = field(default_factory=list)

    def primary_causal(self) -> list[str]:
        return sorted(n for n, m in self.methods.items() if m.role is BenchmarkRole.PRIMARY_CAUSAL)

    def endpoint_only(self) -> list[str]:
        return sorted(n for n, m in self.methods.items() if m.role is BenchmarkRole.ENDPOINT_ONLY)

    def ready(self) -> list[str]:
        return sorted(n for n, m in self.methods.items() if m.status is AdapterStatus.READY)


def run_document(
    plan: BenchmarkPlan, *, source_text: str, config: Mapping[str, Any] | None = None
) -> dict[str, MethodRun]:
    """Produce one handoff per READY method for a single document.

    Methods that are NOT_READY are skipped and recorded; they are never
    substituted by an approximation.
    """
    out: dict[str, MethodRun] = {}
    for name in sorted(plan.methods):
        method = plan.methods[name]
        if method.status is AdapterStatus.NOT_READY:
            plan.warnings.append(f"{name}: NOT_READY, skipped")
            continue
        result = method.compress(
            source_text,
            plan.downstream_task,
            plan.budget,
            dict(config or {}),
            focal_values=plan.focal_values,
        )
        out[name] = MethodRun(
            method=name,
            role=method.role,
            handoff=result,
            causal_metrics_allowed=method.role is not BenchmarkRole.ENDPOINT_ONLY,
        )
    return out


def assert_causal_allowed(run: MethodRun) -> None:
    if not run.causal_metrics_allowed:
        raise EndpointOnlyMisuse(
            f"{run.method} is endpoint-only: T_z is undefined for a latent compressed "
            "state, so it must not populate the causal comparison."
        )


def partition_results(runs: Mapping[str, MethodRun]) -> dict[str, list[str]]:
    return {
        "PRIMARY_CAUSAL": sorted(
            n for n, r in runs.items() if r.role is BenchmarkRole.PRIMARY_CAUSAL
        ),
        "CONTROL": sorted(n for n, r in runs.items() if r.role is BenchmarkRole.CONTROL),
        "LEGACY_ANCHOR": sorted(
            n for n, r in runs.items() if r.role is BenchmarkRole.LEGACY_ANCHOR
        ),
        "OURS": sorted(n for n, r in runs.items() if r.role is BenchmarkRole.OURS),
        "ENDPOINT_ONLY": sorted(
            n for n, r in runs.items() if r.role is BenchmarkRole.ENDPOINT_ONLY
        ),
    }
