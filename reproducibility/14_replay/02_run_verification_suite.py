#!/usr/bin/env python3
"""TVR / handoff-fidelity — Replay Step 02: Run Verification Test Suite.

Executes the project unit, property, and regression test suites to verify
the measurement algorithms, atomizer extraction, causal interventions,
matching contracts, and privacy boundaries.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("=" * 60)
    print("TVR Replay 02: Running Project Verification Test Suite")
    print("=" * 60)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if res.returncode == 0:
        print("[PASS] All verification tests passed successfully.")
    else:
        print("[FAIL] Test suite execution failed.", file=sys.stderr)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
