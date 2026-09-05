# ADR 0004 — OPA governs lifecycle, never science

**Status** Accepted

## Context

Stage transitions have preconditions — freezes, model pins, resolved calibration
values. Encoding them in scattered `if` statements makes them hard to audit.

## Decision

Lifecycle preconditions live in version-controlled Rego with unit tests. A Python
mirror implements the same rules and is authoritative when OPA is unavailable.
On disagreement the engine denies and reports.

OPA never decides a scientific question.

## Alternatives

* OPA as the only gate — rejected: the CLI's fail-closed guards must not depend
  on an external binary.
* Python only — rejected: policy in Rego is separately reviewable and testable.
* Let policy filter observations — rejected outright: that is result selection
  wearing a governance costume.

## Trade-offs

Two implementations to keep in step, handled by a shared test-case table.

## Scientific risk

Low, and it reduces the risk of an undocumented stage transition.
