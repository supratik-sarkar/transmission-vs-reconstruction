# ADR 0005 — NeMo Guardrails is a demo perimeter only

**Status** Accepted

## Context

A public demo may accept untrusted input and benefit from a safety perimeter.

## Decision

Guardrails may sit at demo input/output positions only. They may **never** sit
between relay and receiver, or between intervention and receiver. The check is by
**position**, refusing every scientific-path position even in demo mode, so a
demo configuration cannot leak into a research run. Default off.

## Alternatives

* Guardrails on all model traffic — rejected: they can modify or block a message,
  so the measured message would not be the message the relay produced. $T$, $R^-$
  and $D^+$ would all be silently invalid.
* Rely on mode alone — rejected: a position check is the stronger invariant and
  costs nothing.

## Trade-offs

No safety filtering inside the scientific path. Acceptable: that path processes
our own corpus, not untrusted public input.

## Scientific risk

The decision removes a severe one. Enabling guardrails there would invalidate the
measurement without producing any visible error.
