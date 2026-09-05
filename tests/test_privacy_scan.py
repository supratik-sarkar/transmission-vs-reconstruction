"""Privacy scan, boundary guard and provider credential hygiene."""

from __future__ import annotations

import tempfile
from pathlib import Path

from handoff_fidelity.privacy.scan import (
    DOC_SCOPE,
    SELF_ALLOWLIST,
    scan_repository,
    scan_text,
)
from handoff_fidelity.providers import MockProvider, build_provider
from handoff_fidelity.providers.base import NetworkDisabled, ProviderNotConfigured
from handoff_fidelity.providers.determinism import audit

from ._support import raises


def test_absolute_user_paths_are_flagged():
    findings = scan_text("src/x.py", "path = '/Users/someone/Desktop/project'")
    rules = {f.rule for f in findings}
    assert "absolute_user_path" in rules


def test_credential_patterns_are_flagged():
    cases = {
        "openai_key": "key = 'sk-abcdefghijklmnopqrstuvwxyz'",
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "private_key_block": "-----BEGIN RSA PRIVATE KEY-----",
        "assigned_secret": "api_key: 'averylongsecretvalue123'",
    }
    for rule, line in cases.items():
        assert rule in {f.rule for f in scan_text("src/x.py", line)}, rule


def test_real_email_flagged_but_placeholders_allowed():
    assert scan_text("docs/x.md", "contact: real.person@somewhere.org")
    assert not [
        f for f in scan_text("docs/x.md", "contact: you@example.com") if f.rule == "email_address"
    ]


def test_private_workspace_and_parent_names_are_flagged():
    assert "private_workspace_name" in {
        f.rule for f in scan_text("src/x.py", "root = 'handoff-fidelity-2026'")
    }
    assert "private_git_parent" in {f.rule for f in scan_text("src/x.py", "cd My_Git")}


def test_assistant_instructions_are_flagged():
    assert scan_text("docs/x.md", "instructions for the assistant tool ChatGPT here")


def test_submission_language_flagged_in_docs_only():
    """Venue names are legitimate in a bibliography; they are flagged only in
    public prose, where they would make the repository read as a submission
    workspace."""
    line = "accepted at ICLR 2025"
    assert "submission_language" in {f.rule for f in scan_text("README.md", line)}
    assert "submission_language" not in {f.rule for f in scan_text("refs.bib", line)}


def test_claim_hygiene_flagged_in_readme():
    rules = {f.rule for f in scan_text("README.md", "our method outperforms all baselines")}
    assert "claim_hygiene" in rules


def test_scanner_allowlists_itself_and_its_test():
    assert "src/handoff_fidelity/privacy/scan.py" in SELF_ALLOWLIST
    assert "tests/test_privacy_scan.py" in SELF_ALLOWLIST
    assert scan_text("src/handoff_fidelity/privacy/scan.py", "/Users/anyone") == []


def test_doc_scope_covers_the_public_prose():
    assert "README.md" in DOC_SCOPE
    assert "docs/" in DOC_SCOPE


def test_clean_file_produces_no_findings():
    assert scan_text("src/x.py", "value = compute(a, b)  # ordinary code") == []


def test_repository_scan_reports_and_skips_binaries():
    root = Path(tempfile.mkdtemp())
    (root / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (root / "image.png").write_bytes(b"\x89PNG\r\n")
    report = scan_repository(root, paths=[root / "clean.py", root / "image.png"])
    assert report.ok is True
    assert report.files_scanned == 1
    assert "PASS" in report.render()


def test_repository_scan_fails_on_a_dirty_file():
    root = Path(tempfile.mkdtemp())
    (root / "dirty.py").write_text("home = '/Users/someone'\n", encoding="utf-8")
    report = scan_repository(root, paths=[root / "dirty.py"])
    assert report.ok is False
    assert "FAIL" in report.render()


def test_the_repository_itself_is_clean():
    """The real check. If this fails, something private is tracked."""
    root = Path(__file__).resolve().parents[1]
    report = scan_repository(root)
    assert report.ok, report.render()


def test_provider_repr_never_exposes_configuration_secrets():
    provider = build_provider("openai", "some-model", allow_network=False)
    text = repr(provider)
    assert "OPENAI_API_KEY" not in text
    assert "_key_env" not in text


def test_remote_provider_requires_a_pinned_model():
    provider = build_provider("openai", "UNFROZEN")
    with raises(ProviderNotConfigured):
        provider.generate("prompt", max_tokens=10)


def test_remote_provider_requires_a_credential_then_network():
    import os

    provider = build_provider("openai", "pinned-model-v1")
    # Not shaped like a real key, for the same reason as above.
    os.environ["OPENAI_API_KEY"] = "PRESENCE-ONLY-SENTINEL"
    try:
        with raises(NetworkDisabled):
            provider.generate("prompt", max_tokens=10)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_mock_provider_is_deterministic_and_offline():
    provider = MockProvider()
    assert provider.generate("hello", max_tokens=5) == provider.generate("hello", max_tokens=5)
    assert provider.allow_network is False


def test_unknown_provider_is_refused():
    with raises(ProviderNotConfigured):
        build_provider("not-a-provider", "m")


def test_determinism_audit_requires_exact_agreement():
    """Temperature zero is not evidence. Regime (D) is a claim about an
    endpoint, verified by repetition."""
    clean = audit({"p1": ["a", "a", "a"], "p2": ["b", "b", "b"]})
    assert clean.regime == "D"
    assert clean.exact_agreement_rate == 1.0

    dirty = audit({"p1": ["a", "a", "a"], "p2": ["b", "b", "c"]})
    assert dirty.regime == "S"
    assert "must NOT be labelled regime (D)" in dirty.verdict
    assert "p2" in dirty.disagreeing_prompts


def test_determinism_audit_rejects_a_single_draw():
    with raises(ValueError):
        audit({"p1": ["a"]})
    with raises(ValueError):
        audit({"p1": ["a", "a"], "p2": ["b"]})
