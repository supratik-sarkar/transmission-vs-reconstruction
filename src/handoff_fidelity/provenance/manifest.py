"""Artifact manifests.

The freeze chain is deliberately non-circular:

    1. freeze prompts / specs / code / support files / source artefacts
    2. hash them into an ARTIFACT MANIFEST
    3. finalise the preregistration, which CITES the manifest hash
    4. create a FREEZE RECORD containing the preregistration hash, the manifest
       hash, the source-pool hash, the commit, model versions and a UTC stamp
    5. verify before running
    6. record every deviation

Step 3 citing step 2 -- and not the reverse -- is what keeps it acyclic.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_file, sha256_json


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    sha256: str
    bytes: int


@dataclass(frozen=True, slots=True)
class Manifest:
    root: str
    entries: tuple[ManifestEntry, ...]

    @property
    def self_hash(self) -> str:
        return sha256_json([(e.path, e.sha256, e.bytes) for e in self.entries])

    def to_json(self) -> str:
        return (
            json.dumps(
                {
                    "root": self.root,
                    "self_sha256": self.self_hash,
                    "entries": [
                        {"path": e.path, "sha256": e.sha256, "bytes": e.bytes} for e in self.entries
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def build_manifest(root: Path, paths: Sequence[Path]) -> Manifest:
    root = Path(root).resolve()
    entries: list[ManifestEntry] = []
    for p in sorted({Path(x) for x in paths}):
        full = p if p.is_absolute() else root / p
        full = full.resolve()
        entries.append(
            ManifestEntry(str(full.relative_to(root)), sha256_file(full), full.stat().st_size)
        )
    entries.sort(key=lambda e: e.path)
    return Manifest(str(root), tuple(entries))


def verify_manifest(root: Path, manifest_path: Path) -> tuple[bool, list[str]]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    failures: list[str] = []
    for row in payload.get("entries", []):
        target = Path(root) / row["path"]
        if not target.exists():
            failures.append(f"missing: {row['path']}")
            continue
        if sha256_file(target) != row["sha256"]:
            failures.append(f"hash mismatch: {row['path']}")
    recomputed = sha256_json(
        [(e["path"], e["sha256"], e["bytes"]) for e in payload.get("entries", [])]
    )
    if recomputed != payload.get("self_sha256"):
        failures.append("manifest self-hash mismatch: the manifest itself was edited")
    return (not failures, failures)
