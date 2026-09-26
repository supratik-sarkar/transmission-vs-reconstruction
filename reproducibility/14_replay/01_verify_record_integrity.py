#!/usr/bin/env python3
"""TVR / handoff-fidelity — Replay Step 01: Verify Record Integrity.

Cryptographically verifies that all protocol specifications, manifests, schemas,
and receipt records match the sealed release manifest and SHA256 sums.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPRO_DIR = Path(__file__).resolve().parents[1]
SEAL_TOOL = REPRO_DIR / "tools" / "seal_record.py"


def main() -> int:
    print("=" * 60)
    print("TVR Replay 01: Verifying Reproducibility Record Integrity")
    print("=" * 60)

    cmd = [sys.executable, str(SEAL_TOOL), "--verify"]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("[PASS] Reproducibility record verified successfully.")
    else:
        print("[FAIL] Record verification failed.", file=sys.stderr)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
