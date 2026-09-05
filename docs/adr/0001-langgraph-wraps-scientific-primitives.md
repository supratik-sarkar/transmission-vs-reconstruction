# ADR 0001 — LangGraph wraps scientific primitives

**Status** Accepted

## Context

The programme needs durable, resumable orchestration across a long multi-stage
run. LangGraph provides that. It also provides conditional edges and
model-selected routing.

## Decision

LangGraph is used for durability and checkpointing only. Graph topology is
declared once in `app_contracts.events.STAGE_ORDER`, asserted before execution,
and contains **zero** conditional edges. Nodes are thin wrappers that call
existing, independently tested scientific primitives.

An equivalent deterministic sequential executor runs the same nodes in the same
order when LangGraph is absent.

## Alternatives

* Put causal logic in graph nodes — rejected: it would create a second,
  divergent implementation of the science.
* Allow conditional routing on intermediate results — rejected: a graph that can
  skip a measurement because a value looks unwelcome is a graph that can produce
  the answer you wanted.
* Depend on LangGraph unconditionally — rejected: the scientific path must be
  runnable and testable with no orchestration dependency.

## Trade-offs

Duplicate executors cost a little code. In exchange the scientific route has no
hard orchestration dependency and the topology is verifiable by inspection.

## Scientific risk

Low, and deliberately bounded. The risk this decision removes is high: dynamic
topology would make the executed protocol differ from the pre-registered one.
