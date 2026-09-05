#!/usr/bin/env python3
"""Hash the frozen protocol artifacts into an artifact manifest.

Step 2 of the freeze chain. The pre-registration then cites this manifest's
hash, and the freeze record cites the pre-registration's -- which is what keeps
the chain acyclic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handoff_fidelity.provenance.manifest import build_manifest, verify_manifest  # noqa: E402

DEFAULT_INCLUDE = ("protocol", "configs", "src/handoff_fidelity")
DEFAULT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--include", nargs="*", default=list(DEFAULT_INCLUDE))
    ap.add_argument("--out", default="ARTIFACT_MANIFEST.json")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    if args.verify:
        ok, failures = verify_manifest(root, out)
        print("manifest:", "VALID" if ok else "INVALID")
        for f in failures:
            print(f"  {f}")
        return 0 if ok else 1

    paths: list[Path] = []
    for entry in args.include:
        target = root / entry
        if target.is_file():
            paths.append(target)
        elif target.is_dir():
            paths.extend(
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix in DEFAULT_SUFFIXES and "__pycache__" not in p.parts
            )

    manifest = build_manifest(root, paths)
    out.write_text(manifest.to_json(), encoding="utf-8")
    print(f"hashed {len(manifest.entries)} file(s) -> {out}")
    print(f"manifest self-hash: {manifest.self_hash}")
    print("\nRecord this self-hash in the pre-registration, then write the freeze record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
