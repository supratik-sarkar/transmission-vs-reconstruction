"""FastAPI application.

Read-only over canonical artifacts, plus synthetic demo runs in DEMO_MODE. There
is deliberately NO endpoint that starts a real stage: development execution is
CLI-controlled and the sealed final test is CLI plus freeze-policy controlled, so
the browser cannot become a route around the scientific protocol.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from handoff_fidelity.app_contracts.errors import AppError, ErrorClass
from handoff_fidelity.app_contracts.modes import ModePolicy
from handoff_fidelity.baselines.registry import Registry
from handoff_fidelity.orchestration.graph import topology_description
from handoff_fidelity.policy.decisions import Action, PolicyInput, Subject
from handoff_fidelity.policy.engine import PolicyEngine
from handoff_fidelity.providers.adapters import provider_status_table
from handoff_fidelity.providers.redaction import redact
from handoff_fidelity.telemetry.guardrails import resolve as guardrails_status
from handoff_fidelity.telemetry.langsmith import resolve as langsmith_status
from handoff_fidelity.telemetry.spans import otel_available

from .config import ApiSettings, load_settings
from .store import RunStore, record_from_mock

API_PREFIX = "/api/v1"
API_VERSION = "1.0.0"


def create_app(settings: ApiSettings | None = None, store: RunStore | None = None):
    from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse

    cfg = settings or load_settings()
    runs = store or RunStore()
    policy = PolicyEngine()

    app = FastAPI(
        title="handoff-fidelity",
        version=API_VERSION,
        description=(
            "Read-only research instrument over canonical artifacts. Scientific "
            "execution is CLI-controlled; this API does not expose it."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = cfg
    app.state.runs = runs

    # Explicit origins only. A wildcard with credentials is never configured.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def _guards(request: Request, call_next):
        body_len = request.headers.get("content-length")
        if body_len and int(body_len) > cfg.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error_class": ErrorClass.VALIDATION_ERROR.value,
                    "message": "request body too large",
                },
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        # Redacted, structured, no stack trace.
        return JSONResponse(status_code=exc.http_status, content=redact(exc.to_dict()))

    # ---- health and capability ------------------------------------------
    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "api_version": API_VERSION}

    @app.get(f"{API_PREFIX}/capabilities")
    def capabilities() -> dict[str, Any]:
        ls = langsmith_status(cfg.mode)
        gr = guardrails_status(cfg.mode)
        return {
            "api_version": API_VERSION,
            "settings": cfg.public_dict(),
            "orchestration": topology_description(),
            "telemetry": {
                "otel_sdk_available": otel_available(),
                "canonical_evidence": "artifact ledger, not telemetry",
            },
            "langsmith": ls.to_dict(),
            "guardrails": gr.to_dict(),
            "policy": policy.describe(),
            "browser_may_launch_final_test": ModePolicy(cfg.mode).browser_may_launch_final_test,
            "browser_may_launch_synthetic_run": ModePolicy(
                cfg.mode
            ).browser_may_launch_synthetic_run,
            "empirical_results_available": False,
        }

    @app.get(f"{API_PREFIX}/providers")
    def providers() -> dict[str, Any]:
        # status_dict carries no key, prefix, suffix or length by construction.
        return {"providers": provider_status_table()}

    # ---- runs -------------------------------------------------------------
    @app.get(f"{API_PREFIX}/runs")
    def list_runs() -> dict[str, Any]:
        return {"runs": runs.list()}

    def _require(run_id: str):
        record = runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")
        return record

    @app.get(f"{API_PREFIX}/runs/{{run_id}}")
    def get_run(run_id: str) -> dict[str, Any]:
        r = _require(run_id)
        return {
            "run_id": r.run_id,
            "kind": r.kind,
            "mode": r.mode,
            "status": r.status,
            "marker": r.marker,
            "evidentiary_status": r.evidentiary_status,
            "summary": r.summary,
            "decomposition": r.decomposition,
            "provider_calls": r.provider_calls,
            "spans": r.spans,
            "relay_message": r.relay_message,
            "counterfactuals": r.counterfactuals,
        }

    @app.get(f"{API_PREFIX}/runs/{{run_id}}/atoms")
    def get_atoms(run_id: str) -> dict[str, Any]:
        return {"atoms": _require(run_id).atoms}

    @app.get(f"{API_PREFIX}/runs/{{run_id}}/artifacts")
    def get_artifacts(run_id: str) -> dict[str, Any]:
        return {"artifacts": _require(run_id).artifacts}

    @app.get(f"{API_PREFIX}/runs/{{run_id}}/trace")
    def get_trace(run_id: str, after: int = Query(0, ge=0)) -> dict[str, Any]:
        r = _require(run_id)
        return {"events": [e for e in r.events if int(e["sequence"]) > after], "spans": r.spans}

    @app.get(f"{API_PREFIX}/runs/{{run_id}}/stream")
    async def stream(run_id: str, after: int = Query(0, ge=0)):
        _require(run_id)

        async def gen():
            for event in runs.events_after(run_id, after):
                yield (
                    f"id: {event['sequence']}\nevent: {event['event_type']}\n"
                    f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                )
                await asyncio.sleep(0)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.websocket(f"{API_PREFIX}/runs/{{run_id}}/ws")
    async def ws(websocket: WebSocket, run_id: str):
        await websocket.accept()
        try:
            after = 0
            record = runs.get(run_id)
            if record is None:
                await websocket.close(code=4404)
                return
            for event in runs.events_after(run_id, after):
                await websocket.send_json(event)
            await websocket.close()
        except Exception:
            await websocket.close(code=1011)

    # ---- benchmark / manuscript / preregistration -------------------------
    @app.get(f"{API_PREFIX}/benchmarks")
    def benchmarks() -> dict[str, Any]:
        try:
            registry = Registry.load("configs/baselines.yaml")
            rows = registry.report()
            denominator = registry.superiority_denominator()
            eligible = registry.eligible_primary()
        except Exception:
            rows, denominator, eligible = [], 4, []
        return {
            "methods": rows,
            "eligible_primary": eligible,
            "required_wins": 3,
            "superiority_denominator": denominator,
            "empirical_results_available": False,
            "note": "Readiness only. No comparison has been run.",
        }

    @app.get(f"{API_PREFIX}/manuscript/assets")
    def manuscript_assets() -> dict[str, Any]:
        from handoff_fidelity.export.figures import (
            CONTAINER_FLOAT_LABELS,
            FIGURE_TARGETS,
            STATIC_CONCEPTUAL_FIGURES,
        )
        from handoff_fidelity.export.tables import STATIC_STRUCTURAL_TABLES, TABLE_TARGETS

        return {
            "tables": [
                {"label": k, "file": v, "kind": "empirical", "available": False}
                for k, v in sorted(TABLE_TARGETS.items())
            ]
            + [
                {"label": k, "file": None, "kind": "static_structural", "available": True}
                for k in sorted(STATIC_STRUCTURAL_TABLES)
            ],
            "figures": [
                {"label": k, "file": v, "kind": "empirical", "available": False}
                for k, v in sorted(FIGURE_TARGETS.items())
            ]
            + [
                {"label": k, "file": None, "kind": "conceptual", "available": True}
                for k in sorted(STATIC_CONCEPTUAL_FIGURES)
            ]
            + [
                {"label": k, "file": None, "kind": "container", "available": True}
                for k in sorted(CONTAINER_FLOAT_LABELS)
            ],
            "results_manifest_present": False,
            "editable_from_browser": False,
        }

    @app.get(f"{API_PREFIX}/preregistration/status")
    def prereg_status() -> dict[str, Any]:
        return {
            "binding": False,
            "resolved": False,
            "accounting": {"total": 142, "frozen": 136, "proposed": 4, "must_pin": 2},
            "unresolved": [
                {"path": "budget.primary_output_tokens", "stage": "CALIBRATION"},
                {"path": "experiment_c.eviction_tolerance_tokens", "stage": "CALIBRATION"},
                {"path": "experiment_c.subset_size", "stage": "CALIBRATION"},
                {"path": "causalrelay.primary_family", "stage": "DEVELOPMENT"},
            ],
            "models_pinned": False,
            "final_test": "SEALED - NOT EXECUTED",
        }

    # ---- demo execution (DEMO_MODE only) ---------------------------------
    @app.post(f"{API_PREFIX}/demo/runs")
    def create_demo_run(seed: int = Query(2, ge=0), budget: int = Query(300, ge=50)):
        decision = policy.evaluate(
            PolicyInput(
                action=Action.RUN_DEMO_SYNTHETIC,
                subject=Subject.BROWSER,
                mode=cfg.mode.value,
                provider="mock",
            )
        )
        if not decision.allow:
            raise AppError(
                ErrorClass.POLICY_DENIED,
                "synthetic demo run refused by policy",
                "; ".join(decision.reasons),
            )
        from handoff_fidelity.orchestration.mock_pipeline import run_mock_pipeline

        result = run_mock_pipeline(seed=seed, budget=budget)
        record = runs.put(record_from_mock(result))
        return {"run_id": record.run_id, "marker": record.marker, "evidentiary_status": "NONE"}

    return app


def main() -> int:  # pragma: no cover - server entry point
    import uvicorn

    cfg = load_settings()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")
    return 0
