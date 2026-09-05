"""OpenTelemetry integration.

OTel is OBSERVABILITY, not evidence. Canonical scientific provenance remains the
artifact ledger and RESULTS_MANIFEST.json, so a missing or misconfigured
collector can never affect a result.

Two consequences in the code:

* if ``opentelemetry`` is absent, spans degrade to an in-memory recorder and
  everything still runs;
* every attribute passes through redaction, and a denylist blocks the keys most
  likely to carry a secret or a whole model response.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from ..providers.redaction import assert_no_secret, redact

SPAN_PREFIX = "handoff"

SPAN_NAMES: tuple[str, ...] = (
    "handoff.run",
    "handoff.source.load",
    "handoff.atomize",
    "handoff.sample",
    "handoff.relay",
    "handoff.transmission.match",
    "handoff.receiver.natural",
    "handoff.intervention.construct",
    "handoff.receiver.counterfactual",
    "handoff.match",
    "handoff.estimate",
    "handoff.export",
)

#: Never attach these, whatever their value.
FORBIDDEN_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "token",
        "secret",
        "password",
        "credential",
        "prompt",
        "response",
        "message",
        "raw_response",
        "relay_message",
        "receiver_output",
        "source_text",
    }
)


class TelemetryError(RuntimeError):
    pass


@dataclass(slots=True)
class RecordedSpan:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "UNSET"
    events: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InMemoryTracer:
    """Default tracer. Deterministic, offline, and the one the tests assert on."""

    spans: list[RecordedSpan] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[RecordedSpan]:
        recorded = RecordedSpan(name=name, attributes=sanitize_attributes(attributes))
        self.spans.append(recorded)
        try:
            yield recorded
            if recorded.status == "UNSET":
                recorded.status = "OK"
        except Exception:
            recorded.status = "ERROR"
            raise

    def names(self) -> list[str]:
        return [s.name for s in self.spans]

    def reset(self) -> None:
        self.spans.clear()


def sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Drop forbidden keys, redact everything else, then assert nothing leaked.

    The final assertion is deliberate: a telemetry pipeline is exactly the kind
    of place a secret escapes unnoticed, so this fails loudly instead.
    """
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        if key.lower() in FORBIDDEN_ATTRIBUTES:
            continue
        if any(bad in key.lower() for bad in ("key", "secret", "token", "authorization")):
            continue
        clean[key] = redact(value)
    assert_no_secret(clean, context="telemetry attributes")
    return clean


@dataclass(slots=True)
class OTelTracer:
    """Real OTel tracer, used only when the SDK is installed AND an exporter is
    explicitly configured. Same sanitisation path."""

    service_name: str = "handoff-fidelity"
    _tracer: Any = None

    def __post_init__(self) -> None:
        from opentelemetry import trace  # noqa: PLC0415

        self._tracer = trace.get_tracer(self.service_name)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Any]:
        clean = sanitize_attributes(attributes)
        with self._tracer.start_as_current_span(name) as otel_span:
            for k, v in clean.items():
                otel_span.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
            yield otel_span


def otel_available() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("opentelemetry") is not None
    except (ImportError, ValueError):
        return False


def build_tracer(*, prefer_otel: bool = False, service_name: str = "handoff-fidelity"):
    """In-memory by default.

    Local research runs must work with no collector, no network and no cloud
    account; opting in to OTLP is an explicit act.
    """
    if prefer_otel and otel_available():
        try:
            return OTelTracer(service_name=service_name)
        except Exception:
            return InMemoryTracer()
    return InMemoryTracer()
