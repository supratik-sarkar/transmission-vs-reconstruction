"""Document-clustered nonparametric bootstrap.

Atoms are nested in documents and share one realisation of the relay policy, so
atom-level residuals are dependent within document. Resampling atoms would
understate every interval in the paper.

n is reported in DOCUMENTS, not atoms.

Paired method comparisons resample the SAME document draw for both methods, so
the difference removes document-level heterogeneity; that pairing is what makes
the superiority rule a paired test rather than two independent ones.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

import numpy as np

FINAL_REPLICATES = 10_000
SMOKE_REPLICATES = 200


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    lower: float
    upper: float
    replicates: int
    n_documents: int

    @property
    def excludes_zero_above(self) -> bool:
        return self.lower > 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.point, self.lower, self.upper)


def _group[T](items: Sequence[T], key: Callable[[T], Hashable]) -> dict[Hashable, list[T]]:
    out: dict[Hashable, list[T]] = {}
    for item in items:
        out.setdefault(key(item), []).append(item)
    return out


def cluster_bootstrap[T](
    items: Sequence[T],
    *,
    document_key: Callable[[T], Hashable],
    statistic: Callable[[Sequence[T]], float],
    replicates: int = FINAL_REPLICATES,
    seed: int = 0,
    alpha: float = 0.05,
) -> Interval:
    groups = _group(items, document_key)
    docs = sorted(groups, key=str)
    if not docs:
        raise ValueError("no documents to resample")
    rng = random.Random(seed)
    point = statistic(items)
    draws: list[float] = []
    n = len(docs)
    for _ in range(replicates):
        sampled: list[T] = []
        for _ in range(n):
            sampled.extend(groups[docs[rng.randrange(n)]])
        try:
            draws.append(statistic(sampled))
        except Exception:
            continue
    if not draws:
        raise RuntimeError("every bootstrap replicate failed")
    arr = np.asarray(draws, dtype=float)
    lo = float(np.percentile(arr, 100 * alpha / 2))
    hi = float(np.percentile(arr, 100 * (1 - alpha / 2)))
    return Interval(float(point), lo, hi, len(draws), n)


def paired_cluster_bootstrap[T](
    items_a: Sequence[T],
    items_b: Sequence[T],
    *,
    document_key: Callable[[T], Hashable],
    statistic: Callable[[Sequence[T]], float],
    replicates: int = FINAL_REPLICATES,
    seed: int = 0,
    alpha: float = 0.05,
) -> Interval:
    """Interval for statistic(a) - statistic(b) with a shared document draw.

    Both arms must cover the same document set: comparing methods on different
    documents would confound the method contrast with the document draw.
    """
    ga = _group(items_a, document_key)
    gb = _group(items_b, document_key)
    docs = sorted(set(ga) & set(gb), key=str)
    if not docs:
        raise ValueError("no overlapping documents between the two arms")
    missing = (set(ga) | set(gb)) - set(docs)
    if missing:
        raise ValueError(
            f"{len(missing)} documents present in only one arm; paired comparison "
            "requires a common document set"
        )
    rng = random.Random(seed)
    point = statistic(items_a) - statistic(items_b)
    draws: list[float] = []
    n = len(docs)
    for _ in range(replicates):
        idx = [rng.randrange(n) for _ in range(n)]
        sa: list[T] = []
        sb: list[T] = []
        for i in idx:
            sa.extend(ga[docs[i]])
            sb.extend(gb[docs[i]])
        try:
            draws.append(statistic(sa) - statistic(sb))
        except Exception:
            continue
    if not draws:
        raise RuntimeError("every paired bootstrap replicate failed")
    arr = np.asarray(draws, dtype=float)
    return Interval(
        float(point),
        float(np.percentile(arr, 100 * alpha / 2)),
        float(np.percentile(arr, 100 * (1 - alpha / 2))),
        len(draws),
        n,
    )


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))
