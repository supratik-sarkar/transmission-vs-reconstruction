from __future__ import annotations

import hashlib


def derive_seed(master_seed: int, stage_name: str) -> int:
    digest = hashlib.sha256(f"{master_seed}||{stage_name}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)
