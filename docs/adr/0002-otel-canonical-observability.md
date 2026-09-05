# ADR 0002 — OpenTelemetry is observability, not evidence

**Status** Accepted

## Context

Telemetry is useful for diagnosing a long run. It is also lossy, sampled and
often exported to infrastructure outside our control.

## Decision

OTel carries spans and metrics. Canonical scientific provenance remains the
artifact ledger and `RESULTS_MANIFEST.json`. A missing or misconfigured collector
cannot affect a result. The default tracer is in-memory and offline.

## Alternatives

* Use traces as the provenance record — rejected: sampled, mutable, and often
  third-party hosted. Evidence must be none of those.
* Require a collector — rejected: local research must work with no network.

## Trade-offs

Two record-keeping paths. Accepted, because they answer different questions:
telemetry answers "what happened and how long did it take", the ledger answers
"what exactly produced this number".

## Scientific risk

Low. The decision explicitly prevents telemetry availability from becoming a
dependency of scientific validity.
