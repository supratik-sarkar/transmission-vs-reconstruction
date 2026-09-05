"""Manifests, freeze records, results provenance, stage guards."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_fidelity.config import (
    Settings,
    UnfrozenModelError,
    credential_presence,
    require_frozen_models,
)
from handoff_fidelity.privacy.boundary import PrivateBoundaryError, assert_private_workspace
from handoff_fidelity.provenance.freeze import (
    PROTOCOL_FIELDS,
    TEST_FIELDS,
    FreezeIncomplete,
    load_record,
    new_record,
    verify_record,
)
from handoff_fidelity.provenance.hashing import sha256_json, sha256_text, sha256_tree
from handoff_fidelity.provenance.manifest import build_manifest, verify_manifest
from handoff_fidelity.provenance.results_manifest import ResultEntry, ResultsManifest
from handoff_fidelity.stages.guards import DryRunOnly, ExecutionRequest, authorise
from handoff_fidelity.stages.spec import (
    STAGES,
    Stage,
    StageGuardError,
    check_dev_test_disjoint,
    check_split_disjoint,
)

from ._support import raises


def _filled(fields):
    return {f: f"value-for-{f}" for f in fields}


def test_json_hash_is_key_order_independent():
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})


def test_manifest_detects_content_change(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "b.txt").write_text("beta", encoding="utf-8")
    manifest = build_manifest(root, [root / "a.txt", root / "b.txt"])
    (root / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    ok, failures = verify_manifest(root, root / "manifest.json")
    assert ok is True and failures == []

    (root / "a.txt").write_text("ALPHA", encoding="utf-8")
    ok, failures = verify_manifest(root, root / "manifest.json")
    assert ok is False
    assert any("hash mismatch" in f for f in failures)


def test_manifest_detects_edits_to_itself(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest = build_manifest(root, [root / "a.txt"])
    payload = json.loads(manifest.to_json())
    payload["entries"][0]["sha256"] = sha256_text("alpha")
    payload["entries"].append({"path": "ghost.txt", "sha256": "0" * 64, "bytes": 0})
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    ok, failures = verify_manifest(root, root / "manifest.json")
    assert ok is False
    assert any("self-hash" in f for f in failures)


def test_manifest_is_order_independent(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    for name in ("a.txt", "b.txt", "c.txt"):
        (root / name).write_text(name, encoding="utf-8")
    paths = [root / "a.txt", root / "b.txt", root / "c.txt"]
    assert build_manifest(root, paths).self_hash == build_manifest(root, paths[::-1]).self_hash
    assert sha256_tree(paths) == sha256_tree(paths[::-1])


def test_freeze_record_rejects_placeholder_values():
    """Blanks are blanks by design. Filling them with a plausible string would
    make the record false at signing."""
    fields = _filled(PROTOCOL_FIELDS)
    fields["relay_model"] = "UNFROZEN"
    with raises(FreezeIncomplete):
        new_record("protocol", **fields).validate()
    for placeholder in ("TBD", "PROPOSED", "", None):
        broken = _filled(PROTOCOL_FIELDS)
        broken["git_commit"] = placeholder
        with raises(FreezeIncomplete):
            new_record("protocol", **broken).validate()


def test_complete_protocol_record_validates_and_round_trips(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    record = new_record("protocol", **_filled(PROTOCOL_FIELDS))
    path = record.write(root / "FREEZE.json")
    assert load_record(path).kind == "protocol"
    ok, problems = verify_record(path)
    assert ok is True, problems


def test_test_freeze_requires_strictly_more_than_the_protocol_freeze():
    partial = new_record("final_test", **_filled(PROTOCOL_FIELDS))
    missing = partial.missing()
    assert "causalrelay_artifact_sha256" in missing
    assert "test_document_manifest_sha256" in missing
    complete = new_record("final_test", **_filled(TEST_FIELDS))
    complete.validate()


def test_freeze_verification_detects_a_changed_artefact(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    target = root / "prereg.md"
    target.write_text("original", encoding="utf-8")
    fields = _filled(PROTOCOL_FIELDS)
    fields["preregistration_sha256"] = __import__(
        "handoff_fidelity.provenance.hashing", fromlist=["sha256_file"]
    ).sha256_file(target)
    path = new_record("protocol", **fields).write(root / "FREEZE.json")
    ok, _ = verify_record(path, referenced={"preregistration_sha256": target})
    assert ok is True
    target.write_text("edited after the freeze", encoding="utf-8")
    ok, problems = verify_record(path, referenced={"preregistration_sha256": target})
    assert ok is False
    assert any("changed since freeze" in p for p in problems)


def test_results_manifest_reports_missing_provenance():
    manifest = ResultsManifest()
    manifest.add(ResultEntry(artifact="tables/benchmark_main.tex", kind="table"))
    gaps = manifest.unprovenanced()
    assert "tables/benchmark_main.tex" in gaps
    for field in ("run_ids", "source_hashes", "config_hashes", "model_revisions"):
        assert field in gaps["tables/benchmark_main.tex"]


def test_fully_provenanced_entry_passes(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    artefact = root / "t.tex"
    artefact.write_text("x", encoding="utf-8")
    manifest = ResultsManifest()
    manifest.add(
        ResultEntry(
            artifact="tables/t.tex",
            kind="table",
            run_ids=["r1"],
            source_hashes=["s1"],
            config_hashes=["c1"],
            model_revisions={"receiver": "v1"},
        )
    )
    manifest.stamp("tables/t.tex", artefact)
    assert manifest.unprovenanced() == {}


def test_results_manifest_round_trips(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    manifest = ResultsManifest()
    manifest.add(ResultEntry(artifact="figures/f.pdf", kind="figure", run_ids=["r"]))
    path = manifest.write(root / "RESULTS_MANIFEST.json")
    assert "figures/f.pdf" in ResultsManifest.load(path).entries


def test_stage1_and_stage2_must_be_disjoint():
    check_split_disjoint(["a", "b"], ["c", "d"])
    with raises(StageGuardError):
        check_split_disjoint(["a", "b"], ["b", "c"])


def test_issuer_disjointness_is_checked():
    with raises(StageGuardError):
        check_split_disjoint(["a"], ["b"], {"a": "issuer1", "b": "issuer1"})


def test_dev_and_test_must_be_disjoint():
    with raises(StageGuardError):
        check_dev_test_disjoint(["d1"], ["d1"])


def test_execution_requires_an_explicit_opt_in():
    settings = Settings(relay_model="m", receiver_model="m")
    with raises(DryRunOnly):
        authorise(ExecutionRequest(stage=Stage.STAGE1), settings)


def test_execution_requires_pinned_models():
    with raises(UnfrozenModelError):
        authorise(ExecutionRequest(stage=Stage.STAGE1, execute=True), Settings())


def test_final_test_requires_a_test_freeze_record(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    protocol = root / "protocol.json"
    protocol.write_text("{}", encoding="utf-8")
    settings = Settings(relay_model="m", receiver_model="m")
    gate = __import__(
        "handoff_fidelity.causal.gates", fromlist=["evaluate_stage1_gate"]
    ).evaluate_stage1_gate(reconstruction_contribution=0.5, prior_effects={})
    with raises(StageGuardError):
        authorise(
            ExecutionRequest(
                stage=Stage.STAGE2_TEST, execute=True, protocol_freeze=protocol, gate=gate
            ),
            settings,
        )


def test_proposed_stages_are_flagged_when_authorised(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    for name in ("p.json", "t.json"):
        (root / name).write_text("{}", encoding="utf-8")
    gate = __import__(
        "handoff_fidelity.causal.gates", fromlist=["evaluate_stage1_gate"]
    ).evaluate_stage1_gate(reconstruction_contribution=0.5, prior_effects={})
    checks = authorise(
        ExecutionRequest(
            stage=Stage.STAGE2_TEST,
            execute=True,
            protocol_freeze=root / "p.json",
            test_freeze=root / "t.json",
            gate=gate,
        ),
        Settings(relay_model="m", receiver_model="m"),
    )
    assert any("PROPOSED" in c for c in checks)


def test_stage_table_marks_unapproved_sizes():
    assert STAGES[Stage.STAGE1].proposed is False
    assert STAGES[Stage.STAGE2_TEST].proposed is True


def test_settings_summary_never_contains_a_credential(monkeypatch=None):
    import os

    # Deliberately NOT shaped like a real key: a realistic-looking literal would
    # trip the repository's own secret scan, and the property under test is that
    # the value never appears, whatever its shape.
    sentinel = "CREDENTIAL-VALUE-THAT-MUST-NEVER-APPEAR"
    os.environ["OPENAI_API_KEY"] = sentinel
    try:
        summary = Settings().public_summary()
        assert sentinel not in json.dumps(summary)
        presence = credential_presence()
        assert presence["OPENAI_API_KEY"] is True
        assert sentinel not in json.dumps(presence)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_require_frozen_models_names_the_offenders():
    try:
        require_frozen_models(Settings())
    except UnfrozenModelError as exc:
        assert "relay_model" in str(exc) and "receiver_model" in str(exc)
    else:
        raise AssertionError("expected UnfrozenModelError")


def test_private_workspace_must_not_be_a_git_repo(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    private = root / "private"
    private.mkdir()
    assert_private_workspace(private, root / "public")
    (private / ".git").mkdir()
    with raises(PrivateBoundaryError):
        assert_private_workspace(private)


def test_private_workspace_must_be_outside_the_public_repo(tmp_path=None):
    root = Path(tmp_path or __import__("tempfile").mkdtemp())
    public = root / "public"
    inside = public / "private"
    inside.mkdir(parents=True)
    with raises(PrivateBoundaryError):
        assert_private_workspace(inside, public)


def test_guarded_runners_dry_run_and_fail_closed():
    from handoff_fidelity.stages.runners import (
        run_calibration,
        run_experiment_c,
        run_multihop,
        run_stage1,
        run_stage2_dev,
        run_stage2_test,
    )

    # Dry-run returns resolved plans
    assert run_calibration().status == "DRY_RUN"
    assert run_stage1().status == "DRY_RUN"
    assert run_stage2_dev().status == "DRY_RUN"
    assert run_stage2_test().status == "DRY_RUN"
    assert run_experiment_c().status == "DRY_RUN"
    assert run_multihop().status == "DRY_RUN"

    # Execution fails closed when models are unfrozen
    unpinned_settings = Settings(relay_model="UNFROZEN", receiver_model="UNFROZEN")
    with raises(UnfrozenModelError):
        run_stage1(execute=True, settings=unpinned_settings)

    with raises(UnfrozenModelError):
        run_stage2_test(execute=True, settings=unpinned_settings)


def test_guarded_runners_mock_verification():
    from handoff_fidelity.stages.runners import (
        run_calibration,
        run_experiment_c,
        run_multihop,
        run_stage1,
        run_stage2_dev,
        run_stage2_test,
    )

    cal = run_calibration(mock=True)
    assert cal.status == "MOCK_VERIFIED"
    assert cal.output["editor_validity"] is True

    s1 = run_stage1(mock=True)
    assert s1.status == "MOCK_VERIFIED"
    assert s1.gate_result is not None and s1.gate_result.proceed is True

    s2d = run_stage2_dev(mock=True)
    assert s2d.status == "MOCK_VERIFIED"
    assert s2d.output["fitted"] is True

    s2t = run_stage2_test(mock=True)
    assert s2t.status == "MOCK_VERIFIED"

    exp_c = run_experiment_c(mock=True)
    assert exp_c.status == "MOCK_VERIFIED"

    mhop = run_multihop(mock=True)
    assert mhop.status == "MOCK_VERIFIED"
    assert len(mhop.output["hop_estimates"]) == 2


# --- pre-registration accounting (RC-0.1) ----------------------------------


def test_no_scientific_parameter_is_frozen_silently():
    """Every leaf in the pre-registration must carry an explicit binding status.

    A parameter with a value and no status has been frozen by omission, which is
    exactly the failure the pre-registration exists to prevent. RC-0.1 found one
    (`source_frame.section`) that a hand-written audit had missed.
    """
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "prereg_accounting.py")],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "undeclared leaves (silently frozen if any): 0" in result.stdout


def test_preregistration_is_not_yet_binding():
    """Guards against a stray edit flipping the document to binding while
    values remain PROPOSED and integrity fields remain blank."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    doc = yaml.safe_load(
        (root / "configs" / "preregistration_v1_2.yaml").read_text(encoding="utf-8")
    )
    assert doc["binding"] is False
    assert doc["resolved"] is False
    integrity = doc.get("integrity", {})
    assert any(v in (None, "") for v in integrity.values()), (
        "integrity fields are filled but the document still says binding: false"
    )
