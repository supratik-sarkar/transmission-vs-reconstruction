# ADR 0007 — The frontend is read-only for research

**Status** Accepted

## Context

A browser control that starts a real run is convenient and dangerous.

## Decision

The API exposes **no endpoint** that starts a real scientific stage. Development
execution is CLI-controlled; the sealed final test additionally requires a valid
freeze record. The browser may launch a synthetic demo run in demo mode and
nothing else. Policy denies every real stage to the `browser` subject in every
mode.

## Alternatives

* Expose development execution with a confirmation dialog — rejected: a dialog is
  not a protocol control.
* Expose the final test behind a permission — rejected: the final test is used
  exactly once and must not look like a retryable operation.

## Trade-offs

Operators use the CLI for real work. Correct.

## Scientific risk

The decision removes a serious one: a browser route around the protocol.
