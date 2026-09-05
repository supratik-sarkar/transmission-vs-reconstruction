"""Content hashing primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CHUNK = 1 << 20


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    """Canonical JSON hash: sorted keys, no incidental whitespace, so two
    logically identical configurations hash identically."""
    return sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str))


def sha256_tree(paths: Iterable[Path]) -> str:
    """Order-independent hash of a set of files, binding path AND content."""
    rows = sorted((str(p), sha256_file(Path(p))) for p in paths)
    return sha256_json(rows)
