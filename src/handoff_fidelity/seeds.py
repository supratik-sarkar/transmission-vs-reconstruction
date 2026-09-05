"""Deterministic seed derivation.

Every stochastic step in the protocol derives its seed from a single frozen
master seed plus a stage label, so a run is reproducible from two integers and
a string rather than from ambient RNG state.
"""

from __future__ import annotations

import hashlib
import random


def derive_seed(master_seed: int, *labels: str) -> int:
    payload = "||".join((str(master_seed), *labels)).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def rng_for(master_seed: int, *labels: str) -> random.Random:
    return random.Random(derive_seed(master_seed, *labels))
