import json
from pathlib import Path

import pytest

from scripts.run_stage1 import FailClosedRestartDiskCache


def test_mixed_model_cache_fail_closed(tmp_path):
    cache_dir = tmp_path / "runs" / "stage1_restart_gpt51" / "cache" / "test_stage"
    cache = FailClosedRestartDiskCache(cache_dir, expected_model="gpt-5.1-2025-11-13")

    # Putting mismatched model must raise MIXED_MODEL_CACHE_VIOLATION
    with pytest.raises(RuntimeError, match="MIXED_MODEL_CACHE_VIOLATION"):
        cache.put("key_terra", {"returned_model": "gpt-5.6-terra", "raw_text": "hello"})

    # Putting valid model must succeed
    cache.put("key_valid", {"returned_model": "gpt-5.1-2025-11-13", "raw_text": "hello"})
    rec = cache.get("key_valid")
    assert rec is not None
    assert rec["returned_model"] == "gpt-5.1-2025-11-13"

    # Manually corrupted disk record with alien model must raise on get()
    corrupt_file = cache_dir / "key_corrupt.json"
    corrupt_file.write_text(json.dumps({"returned_model": "deepseek-v4-pro"}))
    with pytest.raises(RuntimeError, match="MIXED_MODEL_CACHE_VIOLATION"):
        cache.get("key_corrupt")


def test_terra_cache_dir_overlap_rejected(tmp_path):
    terra_dir = tmp_path / "runs" / "stage1" / "cache" / "relay"
    with pytest.raises(AssertionError, match="MIXED_MODEL_CACHE_VIOLATION"):
        FailClosedRestartDiskCache(terra_dir, expected_model="gpt-5.1-2025-11-13")


def test_chronology_and_quarantine_artifacts():
    import os

    raw_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    if not raw_home:
        pytest.skip("HANDOFF_PRIVATE_HOME not set; skipping private audit tests")
    audits_dir = Path(raw_home) / "audits"
    if not audits_dir.exists():
        pytest.skip("Private workspace audits not found")

    # 1. P11 Record
    p11_path = audits_dir / "P11_COST_DRIVEN_PRIMARY_MODEL_REPIN_AND_STAGE1_RESTART.json"
    assert p11_path.exists(), "P11 amendment record missing"
    p11 = json.loads(p11_path.read_text(encoding="utf-8"))
    assert p11["scientific_integrity_attestation"]["partial_terra_stage1_existed"] is True
    assert (
        p11["scientific_integrity_attestation"]["terra_stage1_canonical_status"]
        == "ABORTED_TECHNICAL_COST_REPIN"
    )
    assert p11["scientific_integrity_attestation"]["development_and_final_test_touched"] is False

    # 2. Terra Quarantine Manifest
    q_path = audits_dir / "TERRA_STAGE1_QUARANTINE_MANIFEST.json"
    assert q_path.exists(), "Terra quarantine manifest missing"
    q = json.loads(q_path.read_text(encoding="utf-8"))
    assert q["status"] == "QUARANTINED_ABORTED_TECHNICAL_COST_REPIN"
    assert "NONCANONICAL" in q["classification"]
    assert q["total_calls_recorded"] == 1558
    assert (
        q["historical_interim_metrics_sealed"]["status"] == "INVALID_FOR_SCIENTIFIC_INTERPRETATION"
    )

    # 3. Model Selection
    sel_path = audits_dir / "LOW_COST_PRIMARY_MODEL_SELECTION.json"
    assert sel_path.exists(), "Low-cost model selection missing"
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    assert sel["selected_model"] == "gpt-5.1-2025-11-13"
    assert sel["m_star"] == 2
    assert sel["receiver_regime"] == "S_CONFIRMED"

    # 4. Restarted Stage 1 Results
    res_path = audits_dir / "STAGE1_RESULTS_LOW_COST_PRIMARY.json"
    assert res_path.exists(), "Restarted Stage 1 results missing"
    res = json.loads(res_path.read_text(encoding="utf-8"))
    assert res["model"] == "gpt-5.1-2025-11-13"
    assert res["gate_verdict"] == "STAGE1_GATE_PASS"
    assert res["overall_intervention_failure_rate"] <= 0.15
    assert res["differential_intervention_failure_rate"] <= 0.05
