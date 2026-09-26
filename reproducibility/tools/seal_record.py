#!/usr/bin/env python3
"""Seal and verify the reproducibility record.

Usage:
    python seal_record.py           # Generate hashes and seal the record
    python seal_record.py --verify  # Verify existing record against disk
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {
    "00_release/RECORD_MANIFEST.json",
    "00_release/RECORD_SEAL.json",
    "00_release/SHA256SUMS.txt",
}


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_record() -> int:
    manifest_path = ROOT / "00_release/RECORD_MANIFEST.json"
    seal_path = ROOT / "00_release/RECORD_SEAL.json"
    sha_path = ROOT / "00_release/SHA256SUMS.txt"

    if not manifest_path.exists() or not seal_path.exists() or not sha_path.exists():
        print("FAIL: One or more seal files are missing.", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    errors = []

    for rel_path, meta in sorted(files.items()):
        full_path = ROOT / rel_path
        if not full_path.exists():
            errors.append(f"MISSING: {rel_path}")
            continue
        actual_sha = compute_sha256(full_path)
        actual_bytes = full_path.stat().st_size
        if actual_sha != meta["sha256"]:
            errors.append(f"HASH_MISMATCH: {rel_path} (expected {meta['sha256']}, got {actual_sha})")
        if actual_bytes != meta["bytes"]:
            errors.append(f"BYTE_MISMATCH: {rel_path} (expected {meta['bytes']}, got {actual_bytes})")

    # Verify seal hashes
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    computed_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    computed_sha_sha = hashlib.sha256(sha_path.read_bytes()).hexdigest()

    if computed_manifest_sha != seal.get("record_manifest_sha256"):
        errors.append(f"SEAL_MANIFEST_MISMATCH: expected {seal.get('record_manifest_sha256')}, got {computed_manifest_sha}")
    if computed_sha_sha != seal.get("sha256sums_sha256"):
        errors.append(f"SEAL_SHA256SUMS_MISMATCH: expected {seal.get('sha256sums_sha256')}, got {computed_sha_sha}")

    if errors:
        print(f"VERIFICATION FAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"RECORD_VERIFIED: {len(files)} files matched cryptographic manifest and seal.")
    return 0


def seal_record() -> int:
    files = {}
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in EXCLUDE or rel.endswith("/.gitkeep") or rel == ".gitkeep":
            continue
        b = p.read_bytes()
        files[rel] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}

    manifest = {"schema": "causalrelay_release_manifest_v1", "status": "UNSEALED", "files": files}
    mbytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (ROOT / "00_release/RECORD_MANIFEST.json").write_bytes(mbytes)

    lines = [f"{v['sha256']}  {k}" for k, v in files.items()]
    sha = "\n".join(lines) + "\n"
    (ROOT / "00_release/SHA256SUMS.txt").write_text(sha, encoding="utf-8")

    seal = {
        "schema": "causalrelay_record_seal_v1",
        "seal_scope": "CAUSALRELAY_PUBLIC_REPRODUCIBILITY_RECORD",
        "record_manifest_sha256": hashlib.sha256(mbytes).hexdigest(),
        "sha256sums_sha256": hashlib.sha256(sha.encode()).hexdigest(),
        "status": "SEALED_STANDALONE_RECORD",
    }
    (ROOT / "00_release/RECORD_SEAL.json").write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SEALED_FILES {len(files)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        sys.exit(verify_record())
    else:
        sys.exit(seal_record())
