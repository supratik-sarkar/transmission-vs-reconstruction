"""The pre-registered superiority rule, family-aware as of the P-7 amendment.

A headline claim that CausalRelay outperforms recent accepted SOTA compressors
is permitted ONLY IF, at the matched budget, at least THREE primary accepted
SOTA comparators satisfy BOTH

    lower_95CI( A_ours    - A_j    ) > 0
    lower_95CI( Ccomm_ours- Ccomm_j) > 0

using a paired document-clustered bootstrap with 10,000 replicates, **and those
wins span at least three distinct declared method families.**

The family clause is the P-7 amendment (2026-09-06, zero benchmark outcomes
observed). Two of the originally pre-registered primaries were XLM-RoBERTa-large
token classifiers differing by a classifier head and sharing a training
pipeline; beating both of them is one result reported twice, not two independent
results. Counting comparators rather than families overstates breadth.

Eligibility by available families:

* four or more BENCHMARK_READY primaries -> at least 3 wins from at least 3 families
* exactly three distinct BENCHMARK_READY families -> must beat all three
* fewer than three distinct BENCHMARK_READY families -> NO SOTA-superiority headline

The rule is enforced in code, not in prose, and the failure path is a full
report WITHOUT superiority language. Comparators may not be removed after
results are seen, nor easy ones added; the denominator is fixed by the registry
before the test runs.

The legacy anchor does not count toward the three. Neither does a
CONTINGENCY_CAUSAL comparator while it holds that role.

Low reconstruction dependence is NOT a win if endpoint accuracy collapses:
C_recon is reported as a diagnostic, never as the criterion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

REQUIRED_WINS = 3

#: P-7. Distinct declared method families the winning set must span.
REQUIRED_DISTINCT_FAMILIES = 3


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
    winning_families: tuple[str, ...] = ()
    eligible_families: tuple[str, ...] = ()
    required_families: int = REQUIRED_DISTINCT_FAMILIES
    headline_eligible: bool = True
    family_map: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "wins": list(self.wins),
            "losses": list(self.losses),
            "required": self.required,
            "denominator": self.denominator,
            "eligible_comparators": list(self.eligible_comparators),
            "eligible_families": list(self.eligible_families),
            "winning_families": list(self.winning_families),
            "required_families": self.required_families,
            "headline_eligible": self.headline_eligible,
            "permitted": self.permitted,
            "statement": self.statement,
        }


def _families_of(names: Sequence[str], family_map: Mapping[str, str]) -> tuple[str, ...]:
    """Distinct families spanned by `names`.

    A comparator with no declared family is treated as its own family rather
    than being silently merged into another. Merging on absence would be the
    error this whole clause exists to prevent, only in the opposite direction.
    """
    return tuple(sorted({family_map.get(n) or n for n in names}))


def evaluate(
    comparisons: Sequence[PairedComparison],
    *,
    eligible_primary: Sequence[str],
    required: int = REQUIRED_WINS,
    registered_primary: Sequence[str] | None = None,
    family_map: Mapping[str, str] | None = None,
    required_families: int = REQUIRED_DISTINCT_FAMILIES,
) -> SuperiorityVerdict:
    eligible = tuple(sorted(eligible_primary))
    registered = tuple(sorted(registered_primary or eligible_primary))
    fam = dict(family_map or {})

    unexpected = sorted({c.comparator for c in comparisons} - set(registered))
    if unexpected:
        raise ValueError(
            "comparison supplied for methods not in the pre-registered primary suite: "
            f"{unexpected}. Comparators may not be added after results are seen."
        )

    considered = [c for c in comparisons if c.comparator in eligible]
    wins = tuple(sorted(c.comparator for c in considered if c.both_lower_bounds_positive))
    losses = tuple(sorted(c.comparator for c in considered if not c.both_lower_bounds_positive))

    eligible_families = _families_of(eligible, fam)
    winning_families = _families_of(wins, fam)

    # Gate 1 (P-7): the field itself must be broad enough for a headline to mean
    # anything. This is checked BEFORE the wins, so that a narrow field is
    # reported as a design limitation rather than as a failed comparison.
    headline_eligible = len(eligible_families) >= required_families

    if not headline_eligible:
        return SuperiorityVerdict(
            wins=wins,
            losses=losses,
            required=required,
            denominator=len(registered),
            eligible_comparators=eligible,
            permitted=False,
            statement=(
                "NO SOTA-SUPERIORITY HEADLINE: only "
                f"{len(eligible_families)} distinct BENCHMARK_READY method "
                f"{'family' if len(eligible_families) == 1 else 'families'} "
                f"({', '.join(eligible_families) or 'none'}) are available, and "
                f"{required_families} are required. Report the complete benchmark "
                "without superiority language. Do not substitute a comparator to "
                "reach the threshold after seeing results."
            ),
            winning_families=winning_families,
            eligible_families=eligible_families,
            required_families=required_families,
            headline_eligible=False,
            family_map=fam,
        )

    # Gate 2: when exactly `required_families` families are available, every one
    # of them must be beaten. There is no slack to spend.
    must_beat_all = len(eligible_families) == required_families
    wins_needed = len(eligible) if must_beat_all else required

    enough_wins = len(wins) >= wins_needed
    enough_families = len(winning_families) >= required_families
    permitted = enough_wins and enough_families

    if permitted:
        statement = (
            f"Superiority language permitted: {len(wins)} of {len(registered)} "
            f"pre-registered primary comparators cleared both lower bounds "
            f"({', '.join(wins)}), spanning {len(winning_families)} distinct method "
            f"families ({', '.join(winning_families)})."
        )
    else:
        reasons = []
        if not enough_wins:
            reasons.append(
                f"{len(wins)} of {wins_needed} required wins"
                + (
                    " (all eligible comparators must be beaten when exactly "
                    f"{required_families} families are available)"
                    if must_beat_all
                    else ""
                )
            )
        if not enough_families:
            reasons.append(
                f"wins span {len(winning_families)} of {required_families} required "
                f"distinct method families"
            )
        statement = (
            "Superiority language NOT permitted: "
            + "; ".join(reasons)
            + f". Eligible: {len(eligible)} comparators across {len(eligible_families)} "
            "families. Report the complete benchmark without superiority language; "
            "do not delete a comparator, substitute one, or change the metric."
        )

    return SuperiorityVerdict(
        wins=wins,
        losses=losses,
        required=wins_needed,
        denominator=len(registered),
        eligible_comparators=eligible,
        permitted=permitted,
        statement=statement,
        winning_families=winning_families,
        eligible_families=eligible_families,
        required_families=required_families,
        headline_eligible=True,
        family_map=fam,
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
