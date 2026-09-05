"""Hop-indexed estimands.

The decomposition applies verbatim at each hop, since nothing in its proof
refers to the provenance of the non-focal message content.

What does NOT follow is monotonicity. Tbar^(h) is non-increasing in h only if
relays cannot reintroduce an atom, and a receiver that RECONSTRUCTS z at hop h
may cause z to be transmitted at hop h+1 -- so Tbar^(h) can rise. No
monotonicity is enforced and no data-processing-inequality claim is made:
with fixed weights the chain remains Markov, and decoding accuracy is not
mutual information.

Depth 1 establishes the mechanism. Depth >= 3 is what turns it into a workflow
result, because "A^(h) stays flat while Tbar^(h) falls" is only visible once
several handoffs have accumulated. Reporting A^(h) alone would be precisely the
error this project is about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..models import AtomCausalRecord
from .estimands import Decomposition, decompose

DEPTHS: tuple[int, ...] = (1, 2, 3, 5)


@dataclass(frozen=True, slots=True)
class HopEstimates:
    hop: int
    decomposition: Decomposition

    @property
    def summary(self) -> dict[str, float | None]:
        d = self.decomposition
        return {
            "hop": float(self.hop),
            "A": d.endpoint_fidelity,
            "T_bar": d.t_bar,
            "R_bar_0": d.r_bar_zero,
            "C_comm": d.c_comm,
            "C_recon": d.c_recon,
            "alignment": d.alignment,
        }


def decompose_by_hop(
    records_by_hop: Mapping[int, Sequence[AtomCausalRecord]], **kwargs
) -> list[HopEstimates]:
    out: list[HopEstimates] = []
    for hop in sorted(records_by_hop):
        recs = records_by_hop[hop]
        if recs:
            out.append(HopEstimates(hop, decompose(recs, **kwargs)))
    return out


def divergence_curve(estimates: Sequence[HopEstimates]) -> list[tuple[int, float]]:
    """A^(h) - Tbar^(h) as a function of h.

    A widening gap is the workflow claim: endpoint accuracy stays high while
    genuinely transmitted information deteriorates.
    """
    return [(e.hop, e.decomposition.endpoint_fidelity - e.decomposition.t_bar) for e in estimates]
