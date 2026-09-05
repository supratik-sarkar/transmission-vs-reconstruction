"""Matcher validation against a blinded human-audited sample.

Both precision AND recall are blocking. Precision alone is not sufficient: a
matcher that almost never fires would pass a precision-only gate while
systematically understating T, which biases every downstream estimand.

The audit sample is stratified 100 presence / 100 absence. A simple random 200
would leave recall estimated on however many presence cases happened to land,
which is exactly the quantity most at risk.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PRECISION_GATE = 0.95
RECALL_GATE = 0.95
PRESENCE_STRATUM = 100
ABSENCE_STRATUM = 100


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    n: int
    n_presence: int
    n_absence: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def precision(self) -> float:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else 1.0

    @property
    def passed(self) -> bool:
        return (
            self.precision >= PRECISION_GATE
            and self.recall >= RECALL_GATE
            and self.n_presence >= PRESENCE_STRATUM
            and self.n_absence >= ABSENCE_STRATUM
        )

    def report(self) -> dict[str, float | int | bool]:
        return {
            "n": self.n,
            "n_presence": self.n_presence,
            "n_absence": self.n_absence,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "precision_gate": PRECISION_GATE,
            "recall_gate": RECALL_GATE,
            "passed": self.passed,
        }


def score(predicted: Sequence[bool], truth: Sequence[bool]) -> ValidationOutcome:
    if len(predicted) != len(truth):
        raise ValueError("predicted and truth must have equal length")
    tp = sum(1 for p, t in zip(predicted, truth, strict=False) if p and t)
    fp = sum(1 for p, t in zip(predicted, truth, strict=False) if p and not t)
    fn = sum(1 for p, t in zip(predicted, truth, strict=False) if not p and t)
    tn = sum(1 for p, t in zip(predicted, truth, strict=False) if not p and not t)
    return ValidationOutcome(
        n=len(truth),
        n_presence=sum(1 for t in truth if t),
        n_absence=sum(1 for t in truth if not t),
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
    )


AUDIT_COLUMNS = ("item_id", "role", "canonical_value", "message", "human_present")


def write_audit_template(rows: Sequence[dict[str, str]], path: Path) -> int:
    """Blinded sheet: the matcher's own prediction is deliberately absent so the
    auditor cannot anchor on it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=AUDIT_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in AUDIT_COLUMNS})
    return len(rows)


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))
