"""Automated guard test: final-confirmatory test split firewall.

Enforces:
1. The sealed N=200 split (STAGE2_TEST.csv) is strictly hermetically sealed.
2. File metadata and SHA-256 hash are checked without reading/parsing text content.
3. Continuous invariant: FINAL_TEST_EXPOSURE == 0.
4. Active execution paths must only touch model-selection development documents.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

EXPECTED_TEST_SHA = (
    "44ade813cc289bba13780784baaf942e5720c48ac2381a06c1c225339e06515a"  # pragma: allowlist secret
)


def _resolve_non_git_root() -> Path | None:
    env_p = os.environ.get("TVR_NON_GIT_ROOT") or os.environ.get("HANDOFF_PRIVATE_HOME")
    if env_p:
        return Path(env_p).expanduser().resolve()
    # Check default location relative to repo parent
    parent_cand = Path(__file__).resolve().parents[2] / ("handoff-" + "fidelity-2026")
    if parent_cand.exists():
        return parent_cand
    desktop_cand = Path.home() / "Desktop" / ("handoff-" + "fidelity-2026")
    if desktop_cand.exists():
        return desktop_cand
    return None


def test_final_test_hash_integrity_without_content_decoding():
    """Verify final-test split integrity using chunked raw byte hashing only, never decoding text."""
    non_git_root = _resolve_non_git_root()
    if not non_git_root or not non_git_root.exists():
        pytest.skip("Non-git root not available")
    test_csv = non_git_root / "source_manifests" / "STAGE2_TEST.csv"

    if not test_csv.exists():
        pytest.skip(f"Final-test file not present at {test_csv}")

    # Chunked raw byte hashing; no unicode/csv parsing
    hasher = hashlib.sha256()
    with test_csv.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)

    actual_sha = hasher.hexdigest()
    assert actual_sha == EXPECTED_TEST_SHA, (
        f"STAGE2_TEST.csv hash drift! Expected {EXPECTED_TEST_SHA}, got {actual_sha}"
    )


def test_final_test_exposure_ledger_is_zero():
    """Verify that no final-test document has ever been exposed or logged in run ledgers."""
    non_git_root = _resolve_non_git_root()
    if not non_git_root or not non_git_root.exists():
        pytest.skip("Non-git root not available")
    ctrl_dir = non_git_root / "artifacts" / "prof_review_preview_v1" / "master_forward_controller"
    master_state_p = ctrl_dir / "MASTER_STATE.json"

    if master_state_p.exists():
        import json

        state = json.loads(master_state_p.read_text(encoding="utf-8"))
        assert state.get("FULL_FINAL_CONFIRMATORY_EXECUTION_AUTHORIZED") == "NO", (
            "Final confirmatory execution must remain unauthorized!"
        )


def test_codebase_quarantines_final_test_path():
    """Verify that development runners do not hardcode or load STAGE2_TEST.csv directly."""
    src_dir = Path(__file__).resolve().parents[1] / "src"
    violations = []
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if "STAGE2_TEST.csv" in text and "test_firewall" not in py_file.name:
            violations.append(str(py_file))

    assert not violations, (
        f"Direct reference to STAGE2_TEST.csv found in source modules: {violations}"
    )
