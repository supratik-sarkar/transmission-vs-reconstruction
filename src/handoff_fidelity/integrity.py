from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import FreezeRecord


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(root: Path, paths: list[Path], output: Path) -> None:
    rows = []
    for path in sorted(paths):
        full = path if path.is_absolute() else root / path
        rows.append({"path": str(full.relative_to(root)), "sha256": sha256_file(full)})
    output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def verify_manifest(root: Path, manifest: Path) -> tuple[bool, list[str]]:
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    for row in rows:
        path = root / row["path"]
        if not path.exists():
            failures.append(f"missing: {row['path']}")
            continue
        actual = sha256_file(path)
        if actual != row["sha256"]:
            failures.append(f"hash mismatch: {row['path']}")
    return (not failures, failures)


def load_freeze_record(path: Path) -> FreezeRecord:
    return FreezeRecord.model_validate_json(path.read_text(encoding="utf-8"))


def verify_freeze(private_home: Path) -> tuple[bool, list[str]]:
    freeze = private_home / "protocol_freeze" / "FREEZE_RECORD.json"
    if not freeze.exists():
        return False, [f"missing freeze record: {freeze}"]
    record = load_freeze_record(freeze)
    checks: list[str] = []
    prereg = private_home / "protocol_freeze" / "PREREGISTRATION.md"
    manifest = private_home / "protocol_freeze" / "ARTIFACT_MANIFEST.json"
    pool = private_home / "source_manifests" / "FINAL_SOURCE_POOL.csv"
    expected = {
        prereg: record.preregistration_sha256,
        manifest: record.artifact_manifest_sha256,
        pool: record.source_pool_sha256,
    }
    for path, digest in expected.items():
        if not path.exists():
            checks.append(f"missing: {path}")
        elif sha256_file(path) != digest:
            checks.append(f"hash mismatch: {path}")
    if "UNFROZEN" in {record.relay_model, record.receiver_model}:
        checks.append("model version still UNFROZEN")
    return (not checks, checks)
