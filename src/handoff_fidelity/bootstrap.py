from __future__ import annotations

import random
from collections.abc import Callable

import pandas as pd


def document_cluster_bootstrap[T](
    frame: pd.DataFrame,
    *,
    document_col: str,
    statistic: Callable[[pd.DataFrame], T],
    replicates: int,
    seed: int,
) -> list[T]:
    docs = list(frame[document_col].drop_duplicates())
    if not docs:
        raise ValueError("No documents to resample")
    rng = random.Random(seed)
    out: list[T] = []
    groups = {doc: frame.loc[frame[document_col] == doc] for doc in docs}
    for _ in range(replicates):
        sampled = [rng.choice(docs) for _ in docs]
        replicate = pd.concat([groups[d] for d in sampled], ignore_index=True)
        out.append(statistic(replicate))
    return out
