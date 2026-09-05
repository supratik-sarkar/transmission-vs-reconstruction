"""The comparator reproduction gate.

A primary method is benchmark-eligible only after ALL of the following pass on
a non-test public/native task:

  1. environment installs
  2. official checkpoint loads
  3. canonical native example runs
  4. output is textual/hard (required for T_z to be defined)
  5. budget adapter works
  6. a selected published benchmark result is reproduced within tolerance

Debugging happens on public/native or calibration data ONLY. Final-test outputs
are never inspected while adapting an external method, and a method that fails
is reported as UNREPRODUCED rather than replaced after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..baselines.registry import DEFAULT_TOLERANCE_PP, BaselineEntry

GATE_STEPS: tuple[str, ...] = (
    "environment_installs",
    "checkpoint_loads",
    "native_example_runs",
    "output_is_textual",
    "budget_adapter_works",
    "native_metric_reproduced",
)


class TestInspectionError(RuntimeError):
    """Raised if a reproduction run is pointed at a sealed test split."""

    __test__ = False


@dataclass(slots=True)
class ReproductionRun:
    method: str
    split: str
    steps: dict[str, bool] = field(default_factory=dict)
    observed_metric: float | None = None
    expected_metric: float | None = None
    tolerance: float = DEFAULT_TOLERANCE_PP
    published_interval: tuple[float, float] | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if "test" in self.split and "dev" not in self.split:
            raise TestInspectionError(
                f"reproduction of {self.method} was pointed at split {self.split!r}. "
                "Baseline debugging must never touch the sealed test split."
            )

    @property
    def deviation(self) -> float | None:
        if self.observed_metric is None or self.expected_metric is None:
            return None
        return self.observed_metric - self.expected_metric

    @property
    def metric_ok(self) -> bool:
        dev = self.deviation
        if dev is None:
            return False
        if self.published_interval is not None:
            lo, hi = self.published_interval
            return lo <= (self.observed_metric or float("nan")) <= hi
        return abs(dev) <= self.tolerance

    def verdict(self) -> tuple[bool, list[str]]:
        failures = [s for s in GATE_STEPS[:-1] if not self.steps.get(s, False)]
        if not self.metric_ok:
            failures.append("native_metric_reproduced")
        return (not failures, failures)

    def apply_to(self, entry: BaselineEntry) -> BaselineEntry:
        ok, failures = self.verdict()
        entry.native_reproduced_metric = self.observed_metric
        entry.reproduction_deviation = self.deviation
        entry.status = "READY" if ok else "UNREPRODUCED"
        entry.notes = (
            self.notes if ok else f"reproduction failed at: {', '.join(failures)}. {self.notes}"
        ).strip()
        return entry


def summarise(runs: dict[str, ReproductionRun]) -> list[dict[str, Any]]:
    rows = []
    for name in sorted(runs):
        run = runs[name]
        ok, failures = run.verdict()
        rows.append(
            {
                "method": name,
                "split": run.split,
                "reproduced": ok,
                "failed_steps": failures,
                "expected": run.expected_metric,
                "observed": run.observed_metric,
                "deviation": run.deviation,
                "tolerance": run.tolerance,
            }
        )
    return rows
