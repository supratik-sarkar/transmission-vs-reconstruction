#!/usr/bin/env python3
"""Run the test suite without pytest.

The same test functions run under pytest. This runner exists so the suite can be
executed with MINIMAL DEPENDENCIES -- no pytest, no dev extras -- because a test
suite that only runs under one harness is a test suite that quietly stops being
run.

The guarantee is about dependencies, NOT about interpreters. The supported
runtime is Python 3.12; this runner requires it like everything else in the
project, and refuses to run below it rather than failing later with a confusing
SyntaxError from a 3.12-only construct.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
import traceback
from pathlib import Path

REQUIRED_PYTHON = (3, 12)

if sys.version_info < REQUIRED_PYTHON:  # pragma: no cover - environment guard
    raise SystemExit(
        f"handoff-fidelity requires Python "
        f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} or later; this interpreter is "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}. "
        "The project uses 3.12 syntax (PEP 695 generics, enum.StrEnum, datetime.UTC) "
        "and does not support older interpreters. This runner drops pytest, not the "
        "Python version requirement."
    )

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

MODULES = [
    "tests.test_source_frame",
    "tests.test_sampling",
    "tests.test_matcher",
    "tests.test_editing",
    "tests.test_causal",
    "tests.test_interventions",
    "tests.test_benchmark",
    "tests.test_causalrelay",
    "tests.test_inference",
    "tests.test_provenance",
    "tests.test_export",
    "tests.test_privacy_scan",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-k", default=None, help="substring filter on test name")
    args = ap.parse_args()

    passed = failed = skipped = 0
    failures: list[tuple[str, str]] = []

    for module_name in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            failures.append((module_name, traceback.format_exc()))
            failed += 1
            continue
        for name, fn in sorted(vars(module).items()):
            if not name.startswith("test_") or not inspect.isfunction(fn):
                continue
            if fn.__module__ != module_name:
                continue
            if args.k and args.k not in name:
                continue
            required = [
                p
                for p in inspect.signature(fn).parameters.values()
                if p.default is inspect.Parameter.empty
            ]
            if required:
                skipped += 1
                continue
            try:
                fn()
            except Exception:
                failed += 1
                failures.append((f"{module_name}::{name}", traceback.format_exc()))
                if args.verbose:
                    print(f"FAIL {module_name}::{name}")
            else:
                passed += 1
                if args.verbose:
                    print(f"ok   {module_name}::{name}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    for name, tb in failures:
        print(f"\n----- {name}\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
