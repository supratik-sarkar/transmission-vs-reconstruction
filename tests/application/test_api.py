"""FastAPI application test matrix, OpenAPI verification, and route security."""

from __future__ import annotations

from handoff_api.app import create_app
from handoff_api.config import ApiSettings
from starlette.testclient import TestClient

from handoff_fidelity.app_contracts.modes import AppMode


def test_api_healthz():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["api_version"] == "1.0.0"


def test_api_openapi_generation_and_secret_hygiene():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    openapi_text = resp.text
    openapi_json = resp.json()

    assert openapi_json["info"]["title"] == "handoff-fidelity"
    assert "/healthz" in openapi_json["paths"]
    assert "/api/v1/capabilities" in openapi_json["paths"]
    assert "/api/v1/providers" in openapi_json["paths"]
    assert "/api/v1/runs" in openapi_json["paths"]
    assert "/api/v1/benchmarks" in openapi_json["paths"]
    assert "/api/v1/preregistration/status" in openapi_json["paths"]

    # Security check: No secret keys or private machine paths in OpenAPI
    assert "sk-" not in openapi_text
    assert "AIza" not in openapi_text
    assert "/Users/" not in openapi_text
    assert "/home/" not in openapi_text


def test_api_capabilities_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_version"] == "1.0.0"
    assert data["empirical_results_available"] is False
    assert data["browser_may_launch_final_test"] is False
    assert data["orchestration"]["fixed"] is True
    assert data["orchestration"]["conditional_edges"] == 0
    assert data["telemetry"]["canonical_evidence"] == "artifact ledger, not telemetry"


def test_api_providers_endpoint_does_not_disclose_secrets():
    client = TestClient(create_app())
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    for prov in data["providers"]:
        assert "provider" in prov
        assert "state" in prov
        assert "secret_configured" in prov
        assert isinstance(prov["secret_configured"], bool)
        # Verify no secret key, prefix, suffix or length is exposed
        assert "key" not in prov
        assert "api_key" not in prov
        assert "key_prefix" not in prov
        assert "key_suffix" not in prov
        assert "key_length" not in prov


def test_api_benchmarks_endpoint_readiness_only():
    client = TestClient(create_app())
    resp = client.get("/api/v1/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["empirical_results_available"] is False
    assert "methods" in data
    assert "superiority_denominator" in data
    assert "required_wins" in data


def test_api_preregistration_status():
    client = TestClient(create_app())
    resp = client.get("/api/v1/preregistration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["accounting"]["total"] == 142
    assert data["accounting"]["frozen"] == 136
    assert data["accounting"]["proposed"] == 4
    assert data["accounting"]["must_pin"] == 2
    assert data["final_test"] == "SEALED - NOT EXECUTED"
    assert len(data["unresolved"]) == 4


def test_api_manuscript_assets():
    client = TestClient(create_app())
    resp = client.get("/api/v1/manuscript/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results_manifest_present"] is False
    assert data["editable_from_browser"] is False
    assert len(data["tables"]) > 0
    assert len(data["figures"]) > 0


def test_api_security_headers_and_cors():
    client = TestClient(create_app())
    resp = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["cache-control"] == "no-store"
    # CORS headers
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") is None  # allow_credentials=False


def test_api_body_size_limit():
    settings = ApiSettings(max_request_bytes=10)
    client = TestClient(create_app(settings=settings))
    resp = client.post("/api/v1/demo/runs", content=b"a" * 100)
    assert resp.status_code == 413
    assert resp.json()["error_class"] == "VALIDATION_ERROR"


def test_api_research_mode_prohibits_demo_run():
    settings = ApiSettings(mode=AppMode.RESEARCH)
    client = TestClient(create_app(settings=settings))
    resp = client.post("/api/v1/demo/runs")
    assert resp.status_code == 403
    data = resp.json()
    assert data["error_class"] == "POLICY_DENIED"


def test_api_demo_mode_synthetic_run_and_artifacts():
    settings = ApiSettings(mode=AppMode.DEMO)
    client = TestClient(create_app(settings=settings))

    # Create synthetic run
    resp = client.post("/api/v1/demo/runs?seed=2&budget=300")
    assert resp.status_code == 200
    created = resp.json()
    run_id = created["run_id"]
    assert created["evidentiary_status"] == "NONE"

    # List runs
    resp_list = client.get("/api/v1/runs")
    assert resp_list.status_code == 200
    runs_data = resp_list.json()["runs"]
    assert any(r["run_id"] == run_id for r in runs_data)

    # Get run details
    resp_get = client.get(f"/api/v1/runs/{run_id}")
    assert resp_get.status_code == 200
    run_detail = resp_get.json()
    assert run_detail["evidentiary_status"] == "NONE"
    assert "summary" in run_detail
    assert "decomposition" in run_detail
    assert "relay_message" in run_detail

    # Get atoms
    resp_atoms = client.get(f"/api/v1/runs/{run_id}/atoms")
    assert resp_atoms.status_code == 200
    atoms = resp_atoms.json()["atoms"]
    assert len(atoms) > 0

    # Get artifacts
    resp_artifacts = client.get(f"/api/v1/runs/{run_id}/artifacts")
    assert resp_artifacts.status_code == 200

    # Get trace
    resp_trace = client.get(f"/api/v1/runs/{run_id}/trace")
    assert resp_trace.status_code == 200
    events = resp_trace.json()["events"]
    assert len(events) > 0

    # Test SSE stream
    resp_stream = client.get(f"/api/v1/runs/{run_id}/stream")
    assert resp_stream.status_code == 200
    stream_text = resp_stream.text
    assert "event: STAGE_STARTED" in stream_text or "event:" in stream_text

    # 404 for nonexistent run
    resp_404 = client.get("/api/v1/runs/nonexistent_id")
    assert resp_404.status_code == 404
