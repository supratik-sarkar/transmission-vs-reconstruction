# ADR 0003 — LangSmith optional and off by default

**Status** Accepted

## Context

LangGraph integrates with LangSmith through environment variables. Setting one
flag would begin exporting trace content.

## Decision

Off by default in both modes. **Refused** in research mode even when explicitly
requested; `enforce_disabled_in_research` raises.

## Alternatives

* On by default for convenience — rejected: real source text and real model
  output would leave the machine merely because a library supports it.
* Allow it in research mode with a warning — rejected: a warning is not a
  control, and the data would already be gone.

## Trade-offs

Less convenient tracing during research. Demo tracing remains available.

## Scientific risk

The decision removes a confidentiality risk. Leaving it enabled would also make
the effective experimental configuration depend on an environment variable.
