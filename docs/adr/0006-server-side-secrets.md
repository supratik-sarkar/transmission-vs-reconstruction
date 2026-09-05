# ADR 0006 — Secrets are server-side and typed

**Status** Accepted

## Context

Four provider credentials must reach adapters without reaching logs, traces,
error payloads, the OpenAPI document or the frontend bundle.

## Decision

Read from the environment into a `Secret` holder whose `__repr__` and `__str__`
are redacted and whose value is reachable only through an explicit `reveal()`
that the API layer never calls. A redaction layer covers logs, errors, spans and
ledger records. The provider status shape carries a boolean only — no key, no
prefix, no suffix, no length.

## Alternatives

* Plain strings — rejected: they eventually reach an f-string or a log line.
* Show a masked suffix in the UI — rejected: a partial fingerprint is
  unnecessary and is still information about a secret.

## Trade-offs

`reveal()` is slightly awkward at the call site. That awkwardness is the feature.

## Scientific risk

None directly; the risk is disclosure.
