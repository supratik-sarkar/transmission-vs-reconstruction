"""Secret-leakage tests.

Fake credentials are injected deliberately and must not survive into any egress
surface. The fixtures are shaped like real keys on purpose -- a test using
`not-a-key` would prove nothing about the patterns that matter.
"""

from __future__ import annotations

import json
import os

from handoff_fidelity.providers.adapters import provider_status_table
from handoff_fidelity.providers.ledger import (
    CallStatus,
    ProviderCall,
    ProviderLedger,
    content_hash,
    utcnow,
)
from handoff_fidelity.providers.redaction import (
    REDACTED,
    assert_no_secret,
    redact,
    redact_text,
)
from handoff_fidelity.telemetry.spans import InMemoryTracer, sanitize_attributes

FAKE_OPENAI = "sk-test_openai_secret_DO_NOT_USE_0123456789abcdef"
FAKE_DEEPSEEK = "sk-test_deepseek_secret_DO_NOT_USE_0123456789ab"
FAKE_GOOGLE = "AIzaTestGoogleSecretDoNotUse0123456789abcd"


class _Env:
    """Install fake credentials for the duration of a test."""

    def __enter__(self):
        os.environ["OPENAI_API_KEY"] = FAKE_OPENAI
        os.environ["DEEPSEEK_API_KEY"] = FAKE_DEEPSEEK
        os.environ["GEMINI_API_KEY"] = FAKE_GOOGLE
        return self

    def __exit__(self, *exc):
        for k in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(k, None)
        return False


def test_live_secret_values_are_redacted_from_text():
    with _Env():
        assert FAKE_OPENAI not in redact_text(f"authorization: Bearer {FAKE_OPENAI}")
        assert REDACTED in redact_text(f"key={FAKE_OPENAI}")


def test_credential_shapes_are_redacted_without_env():
    for shaped in (
        FAKE_OPENAI,
        FAKE_GOOGLE,
        "AKIAIOSFODNN7EXAMPLE",
        "-----BEGIN RSA PRIVATE KEY-----",
    ):
        assert shaped not in redact_text(f"leaked: {shaped}")


def test_sensitive_keys_are_redacted_by_name():
    out = redact({"api_key": "anything", "nested": {"authorization": "Bearer x"}})
    assert out["api_key"] == REDACTED
    assert out["nested"]["authorization"] == REDACTED


def test_provider_status_never_contains_key_material():
    """The status table is what reaches the API and the browser."""
    with _Env():
        table = provider_status_table()
        payload = json.dumps(table)
        assert_no_secret(payload, context="provider status table")
        for row in table:
            assert set(row) >= {"provider", "state", "secret_configured", "model_pinned"}
            # Presence only: no prefix, suffix or length anywhere.
            assert "key" not in json.dumps(row).lower().replace("api_key_configured", "")
        openai = next(r for r in table if r["provider"] == "openai")
        assert openai["secret_configured"] is True


def test_ledger_refuses_to_write_a_leaked_secret():
    with _Env():
        ledger = ProviderLedger()
        call = ProviderCall(
            call_id="c1",
            run_id="r1",
            provider="openai",
            requested_model="m",
            attempt=1,
            started_at=utcnow(),
            completed_at=utcnow(),
            latency_s=0.1,
            status=CallStatus.OK,
            prompt_hash=content_hash("p"),
            request_hash=content_hash("p"),
            extra={"note": f"debugging with {FAKE_OPENAI}"},
        )
        # extra is redacted on the way in, so the write succeeds and is clean.
        ledger.append(call)
        assert_no_secret([r.to_dict() for r in ledger.records()], context="ledger")


def test_telemetry_attributes_drop_forbidden_keys_and_redact():
    with _Env():
        clean = sanitize_attributes(
            {
                "run_id": "r1",
                "prompt": "the entire prompt",
                "api_key": FAKE_OPENAI,
                "note": f"token {FAKE_DEEPSEEK}",
                "budget": 300,
            }
        )
        assert "prompt" not in clean  # whole payloads never attach
        assert "api_key" not in clean
        assert clean["run_id"] == "r1" and clean["budget"] == 300
        assert_no_secret(clean, context="span attributes")


def test_tracer_spans_carry_no_secret():
    with _Env():
        tracer = InMemoryTracer()
        with tracer.span("handoff.relay", run_id="r", note=f"key {FAKE_OPENAI}"):
            pass
        assert_no_secret([s.attributes for s in tracer.spans], context="tracer")
