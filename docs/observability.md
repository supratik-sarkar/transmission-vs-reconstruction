# Observability

OpenTelemetry is the observability layer. It is **not** evidence.

Canonical scientific provenance remains the artifact ledger and
`RESULTS_MANIFEST.json`, so a missing, misconfigured or unavailable collector can
never affect a result. That separation is the point: telemetry is allowed to be
best-effort precisely because nothing scientific depends on it.

## Spans

```
handoff.run                       handoff.intervention.construct
handoff.source.load               handoff.receiver.counterfactual
handoff.atomize                   handoff.match
handoff.sample                    handoff.estimate
handoff.relay                     handoff.export
handoff.transmission.match
handoff.receiver.natural
```

## What is never attached

A denylist blocks the keys most likely to carry a secret or an entire payload:
credentials and authorization headers, and `prompt`, `response`, `message`,
`raw_response`, `relay_message`, `receiver_output`, `source_text`.

Everything that survives the denylist passes through redaction, and the result is
then **asserted** to contain no secret. That final assertion is deliberate: a
telemetry pipeline is exactly where a credential escapes unnoticed, so this fails
loudly rather than exporting.

## Defaults

Local research runs work with no collector, no network and no cloud account. The
default tracer is in-memory; OTLP export is an explicit opt-in.

## LangSmith

Optional, off by default, and refused in research mode. See
[research-vs-demo.md](research-vs-demo.md).
