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

    # 5. Corrected Stage 1 Discovery Gate Verdict
    gate_path = audits_dir / "STAGE1_GATE_LOW_COST_PRIMARY.json"
    assert gate_path.exists(), "STAGE1_GATE_LOW_COST_PRIMARY.json missing"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["verdict"] == "STAGE1_GATE_AUDIT_CORRECTED_FAIL"
    assert gate["provisional_superseded_verdict"] == "STAGE1_GATE_PASS"
    assert gate["reconstruction_gate_verdict"] == "FAIL"
    assert gate["prior_gate_verdict"] == "FAIL"
    assert gate["proceed"] is False
    assert gate["reconstruction_contribution_c_recon"] < 0.10
    for cls in ("scope", "period", "numeric"):
        assert gate["prior_effects_matched"][cls] < 0.10

    # 6. Stage-1 Uncertainty Package
    unc_path = audits_dir / "STAGE1_UNCERTAINTY_PACKAGE.json"
    assert unc_path.exists(), "STAGE1_UNCERTAINTY_PACKAGE.json missing"
    unc = json.loads(unc_path.read_text(encoding="utf-8"))
    meta = unc["metadata"]
    assert meta["n_bootstrap_replicates"] == 10000
    assert meta["cluster_level"] == "doc_id"
    assert meta["final_test_exposure"] == 0
    assert meta["development_provider_calls"] == 0
    decomp = unc["transmission_reconstruction_decomposition"]
    assert decomp["C_recon"]["estimate"] < 0.10
    assert decomp["C_recon"]["ci_95"][1] < 0.10
    assert decomp["Cov_T_Delta"]["estimate"] < 0  # Severe negative targeting covariance
    align = unc["relay_alignment_analysis"]
    assert align["verdict"] == "SEVERE_RELAY_MISALIGNMENT"

    # 7. Completed Experiment-B Results
    exp_b_path = audits_dir / "EXPERIMENT_B_RESULTS.json"
    assert exp_b_path.exists(), "EXPERIMENT_B_RESULTS.json missing"
    exp_b = json.loads(exp_b_path.read_text(encoding="utf-8"))
    assert exp_b["total_calls"] == 108
    assert exp_b["ceiling_respected"] is True
    assert exp_b["total_spend_usd"] <= exp_b["ceiling_usd"]
    for cls in ("scope", "period", "numeric"):
        assert exp_b["by_role_summary"][cls]["delta_r_prior_matched"] == 0.0


def test_zero_development_calls_and_zero_final_test_exposure():
    import os

    raw_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    if not raw_home:
        pytest.skip("HANDOFF_PRIVATE_HOME not set")
    runs_dir = Path(raw_home) / "runs"
    if not runs_dir.exists():
        pytest.skip("runs directory not found")

    # Prove development provider calls = 0
    dev_dir = runs_dir / "stage2_dev"
    if dev_dir.exists():
        dev_files = [p for p in dev_dir.rglob("*") if p.is_file() and p.name != ".keep"]
        assert len(dev_files) == 0, f"Expected 0 development files, found {dev_files}"

    # Prove final test exposure = 0
    test_dir = runs_dir / "stage2_test"
    if test_dir.exists():
        test_files = [p for p in test_dir.rglob("*") if p.is_file() and p.name != ".keep"]
        assert len(test_files) == 0, f"Expected 0 test files, found {test_files}"

    # Prove multihop and experiment_c unexecuted
    for post_gate in ("experiment_c", "multihop"):
        d = runs_dir / post_gate
        if d.exists():
            files = [p for p in d.rglob("*") if p.is_file() and p.name != ".keep"]
            assert len(files) == 0, f"Expected 0 files in {post_gate}, found {files}"


def test_stage1_cache_homogeneity_and_terra_quarantine():
    import os

    raw_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    if not raw_home:
        pytest.skip("HANDOFF_PRIVATE_HOME not set")
    stage1_cache = Path(raw_home) / "runs" / "stage1_restart_gpt51" / "cache"
    if not stage1_cache.exists():
        pytest.skip("Stage1 restart cache not found")

    # Check all cache stages: relay, receiver, prior_probe, experiment_b
    expected_model = "gpt-5.1-2025-11-13"
    call_count = 0
    for stage_dir in stage1_cache.iterdir():
        if not stage_dir.is_dir():
            continue
        for f in stage_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            assert data.get("returned_model") == expected_model, (
                f"Alien model found in {f}: {data.get('returned_model')}"
            )
            call_count += 1

    # Total calls: 100 relay + 1192 receiver + 1730 prior probe + 108 experiment_b = 3130
    assert call_count == 3130
