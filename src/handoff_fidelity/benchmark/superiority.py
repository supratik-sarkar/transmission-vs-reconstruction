"""The pre-registered superiority rule.

A headline claim that CausalRelay outperforms recent accepted SOTA compressors
is permitted ONLY IF, at the matched budget, at least THREE primary accepted
SOTA comparators satisfy BOTH

    lower_95CI( A_ours    - A_j    ) > 0
    lower_95CI( Ccomm_ours- Ccomm_j) > 0

using a paired document-clustered bootstrap with 10,000 replicates.

The rule is enforced in code, not in prose, and the failure path is a full
report WITHOUT superiority language. Comparators may not be removed after
results are seen, nor easy ones added; the denominator is fixed by the registry
before the test runs.

The legacy anchor does not count toward the three.

Low reconstruction dependence is NOT a win if endpoint accuracy collapses:
C_recon is reported as a diagnostic, never as the criterion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

REQUIRED_WINS = 3


@dataclass(frozen=True, slots=True)
class PairedComparison:
    comparator: str
    delta_a: tuple[float, float, float]  # point, lower, upper
    delta_c_comm: tuple[float, float, float]

    @property
    def both_lower_bounds_positive(self) -> bool:
        return self.delta_a[1] > 0.0 and self.delta_c_comm[1] > 0.0


@dataclass(frozen=True, slots=True)
class SuperiorityVerdict:
    wins: tuple[str, ...]
    losses: tuple[str, ...]
    required: int
    denominator: int
    eligible_comparators: tuple[str, ...]
    permitted: bool
    statement: str


def evaluate(
    comparisons: Sequence[PairedComparison],
    *,
    eligible_primary: Sequence[str],
    required: int = REQUIRED_WINS,
    registered_primary: Sequence[str] | None = None,
) -> SuperiorityVerdict:
    eligible = tuple(sorted(eligible_primary))
    registered = tuple(sorted(registered_primary or eligible_primary))

    unexpected = sorted({c.comparator for c in comparisons} - set(registered))
    if unexpected:
        raise ValueError(
            "comparison supplied for methods not in the pre-registered primary suite: "
            f"{unexpected}. Comparators may not be added after results are seen."
        )

    considered = [c for c in comparisons if c.comparator in eligible]
    wins = tuple(sorted(c.comparator for c in considered if c.both_lower_bounds_positive))
    losses = tuple(sorted(c.comparator for c in considered if not c.both_lower_bounds_positive))
    permitted = len(wins) >= required

    if permitted:
        statement = (
            f"Superiority language permitted: {len(wins)} of {len(registered)} "
            f"pre-registered primary comparators cleared both lower bounds "
            f"({', '.join(wins)})."
        )
    else:
        statement = (
            f"Superiority language NOT permitted: {len(wins)} of {required} required "
            f"wins among {len(eligible)} eligible primary comparators. Report the "
            "complete benchmark without superiority language; do not delete a "
            "comparator, substitute one, or change the metric."
        )
    return SuperiorityVerdict(
        wins, losses, required, len(registered), eligible, permitted, statement
    )


def format_report(verdict: SuperiorityVerdict, comparisons: Sequence[PairedComparison]) -> str:
    lines = [verdict.statement, ""]
    for c in sorted(comparisons, key=lambda x: x.comparator):
        lines.append(
            f"  {c.comparator:<24s} dA={c.delta_a[0]:+.4f} [{c.delta_a[1]:+.4f}, {c.delta_a[2]:+.4f}]  "
            f"dCcomm={c.delta_c_comm[0]:+.4f} [{c.delta_c_comm[1]:+.4f}, {c.delta_c_comm[2]:+.4f}]  "
            f"{'WIN' if c.both_lower_bounds_positive else '--'}"
        )
    return "\n".join(lines)
