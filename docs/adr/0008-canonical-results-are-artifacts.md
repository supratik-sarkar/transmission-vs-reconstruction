# ADR 0008 — Canonical results are artifacts

**Status** Accepted

## Context

The stack now includes a SQLite-shaped run index, LangGraph checkpoints, OTel
spans and a UI store. Each could plausibly be treated as the record of a result.

## Decision

None of them is. Canonical evidence is the immutable artifact set, the run
ledger and `RESULTS_MANIFEST.json`. Everything else is a cache that must be
rebuildable from artifacts. The browser recomputes no scientific quantity; it
renders delivered values and names missing ones.

## Alternatives

* Serve results from the run index — rejected: the index is mutable and
  rebuildable, which is the opposite of what evidence must be.
* Let the UI compute derived metrics — rejected: it would create a second
  implementation that could disagree with the estimator.

## Trade-offs

The UI cannot show a quantity the backend has not produced. That is intended: it
is why an unmeasured value renders as `NOT ESTIMATED` rather than zero.

## Scientific risk

Low, and it forecloses a class of silent divergence.
