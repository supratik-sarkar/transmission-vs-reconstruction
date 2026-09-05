"""Operational determinism audit.

Decoder regime (D) is a CLAIM ABOUT AN ENDPOINT, not a configuration flag.
Setting temperature to zero does not make a hosted API deterministic, and
several do not guarantee it. The audit issues the same request repeatedly at
the same configuration and requires EXACT output agreement.

If agreement is not exact the receiver must not be labelled regime (D). The
options are to switch to a genuinely deterministic receiver, or to issue a
revised preregistration under regime (S) -- under which atom-level statistics
such as P[Delta < 0] are not identified from one query per availability.

The audit runs on DISJOINT CALIBRATION PROMPTS, never on experimental content.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

EXACT_AGREEMENT_REQUIRED = 1.0
DEFAULT_REPEATS = 5


@dataclass(frozen=True, slots=True)
class DeterminismResult:
    n_prompts: int
    repeats: int
    exact_agreement_rate: float
    disagreeing_prompts: tuple[str, ...]

    @property
    def regime(self) -> str:
        return "D" if self.exact_agreement_rate >= EXACT_AGREEMENT_REQUIRED else "S"

    @property
    def verdict(self) -> str:
        if self.regime == "D":
            return (
                f"Exact agreement on {self.n_prompts} calibration prompts x {self.repeats} "
                "repeats. Regime (D) is supported."
            )
        return (
            f"Only {self.exact_agreement_rate:.3f} of {self.n_prompts} calibration prompts "
            f"agreed exactly across {self.repeats} repeats. The receiver must NOT be "
            "labelled regime (D). Either switch to a genuinely deterministic receiver, or "
            "issue a revised preregistration under regime (S) and drop atom-level "
            "statistics that are not identified from one query per availability."
        )


def audit(outputs_by_prompt: dict[str, Sequence[str]]) -> DeterminismResult:
    if not outputs_by_prompt:
        raise ValueError("determinism audit requires at least one calibration prompt")
    repeats = {len(v) for v in outputs_by_prompt.values()}
    if len(repeats) != 1:
        raise ValueError("every prompt must be repeated the same number of times")
    n_repeats = repeats.pop()
    if n_repeats < 2:
        raise ValueError("determinism cannot be assessed from a single draw")
    disagreeing = tuple(
        sorted(p for p, outs in outputs_by_prompt.items() if len(Counter(outs)) > 1)
    )
    agree = 1.0 - len(disagreeing) / len(outputs_by_prompt)
    return DeterminismResult(len(outputs_by_prompt), n_repeats, agree, disagreeing)
