"""The scientific graph.

Topology is FIXED and declared in ``app_contracts.events.STAGE_ORDER``. No model
selects it, no component reorders it, and no stage may be skipped because a
result looks unwelcome.

LangGraph is used for durable orchestration when installed. When it is not, an
equivalent deterministic sequential executor runs the SAME node functions in the
SAME order. That is not a fallback of convenience: it keeps the scientific path
runnable with no orchestration dependency at all, which is what lets the core be
tested in a minimal environment.

Checkpoint storage is runtime infrastructure. Canonical scientific truth remains
the artifact ledger and RESULTS_MANIFEST.json.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from ..app_contracts.events import STAGE_ORDER, EventStatus, EventType, Stage
from ..app_contracts.modes import AppMode, ModePolicy
from . import nodes
from .state import RunState


class GraphTopologyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GraphNode:
    stage: Stage
    fn: Callable[[RunState], RunState]


def langgraph_available() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("langgraph") is not None
    except (ImportError, ValueError):
        return False


def build_nodes(
    *, provider: Any, model: str, raw_text: str, document_id: str, window_tokens: int, tokenizer
) -> list[GraphNode]:
    """Bind runtime arguments; the ORDER is not negotiable."""
    return [
        GraphNode(Stage.PREPARE_RUN, nodes.prepare_run),
        GraphNode(
            Stage.LOAD_SOURCE,
            partial(
                nodes.load_source,
                raw_text=raw_text,
                document_id=document_id,
                window_tokens=window_tokens,
                tokenizer=tokenizer,
            ),
        ),
        GraphNode(Stage.ATOMIZE, nodes.atomize_source),
        GraphNode(Stage.SAMPLE_FOCALS, nodes.sample_focals),
        GraphNode(Stage.RELAY, partial(nodes.run_relay, provider=provider, model=model)),
        GraphNode(Stage.MATCH_TRANSMISSION, nodes.match_transmission),
        GraphNode(
            Stage.NATURAL_RECEIVER, partial(nodes.natural_receiver, provider=provider, model=model)
        ),
        GraphNode(Stage.CONSTRUCT_INTERVENTIONS, nodes.construct_interventions),
        GraphNode(
            Stage.COUNTERFACTUAL_RECEIVER,
            partial(nodes.counterfactual_receiver, provider=provider, model=model),
        ),
        GraphNode(Stage.DETERMINISTIC_MATCH, nodes.deterministic_match),
        GraphNode(Stage.ESTIMATE, nodes.estimate),
    ]


def assert_topology(graph_nodes: list[GraphNode]) -> None:
    """The declared node order must be a prefix-consistent subsequence of the
    frozen topology. A reordered or injected stage fails here, before execution."""
    index = {s: i for i, s in enumerate(STAGE_ORDER)}
    last = -1
    for node in graph_nodes:
        pos = index.get(node.stage)
        if pos is None:
            raise GraphTopologyError(f"stage {node.stage!r} is not in the frozen topology")
        if pos <= last:
            raise GraphTopologyError(f"stage {node.stage.value!r} is out of frozen topology order")
        last = pos


@dataclass(slots=True)
class SequentialExecutor:
    """Deterministic executor. Same nodes, same order, no dependency."""

    graph_nodes: list[GraphNode]
    engine: str = "sequential"

    def run(self, state: RunState) -> RunState:
        assert_topology(self.graph_nodes)
        ModePolicy(state.mode).require  # noqa: B018 - presence check only
        for node in self.graph_nodes:
            try:
                state = node.fn(state)
            except Exception as exc:
                # Deterministic failure state. The run stops; it does not skip
                # ahead, and it does not retry to obtain a different answer.
                state.events.append(
                    node.stage,
                    EventType.STAGE_FAILED,
                    EventStatus.FAILED,
                    {"error": type(exc).__name__, "message": str(exc)[:400]},
                )
                state.events.append(
                    Stage.FINALIZE_RUN,
                    EventType.RUN_FAILED,
                    EventStatus.FAILED,
                    {"failed_stage": node.stage.value},
                )
                raise
        state.events.append(
            Stage.FINALIZE_RUN,
            EventType.RUN_COMPLETED,
            EventStatus.OK,
            state.summary(),
        )
        return state


@dataclass(slots=True)
class LangGraphExecutor:
    """LangGraph wrapper. Compiles the SAME fixed topology into a linear graph.

    LangGraph contributes durability and checkpointing. It contributes no
    scientific decision: there is no conditional edge, no router and no
    model-selected branch anywhere in this graph.
    """

    graph_nodes: list[GraphNode]
    engine: str = "langgraph"

    def run(self, state: RunState) -> RunState:
        assert_topology(self.graph_nodes)
        from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

        builder: Any = StateGraph(dict)
        for node in self.graph_nodes:
            builder.add_node(node.stage.value, self._wrap(node))
        builder.add_edge(START, self.graph_nodes[0].stage.value)
        for a, b in zip(self.graph_nodes, self.graph_nodes[1:], strict=False):
            builder.add_edge(a.stage.value, b.stage.value)
        builder.add_edge(self.graph_nodes[-1].stage.value, END)
        compiled = builder.compile()
        compiled.invoke({"state": state})
        state.events.append(
            Stage.FINALIZE_RUN,
            EventType.RUN_COMPLETED,
            EventStatus.OK,
            state.summary(),
        )
        return state

    @staticmethod
    def _wrap(node: GraphNode):
        def _run(payload: dict) -> dict:
            payload["state"] = node.fn(payload["state"])
            return payload

        return _run


def build_executor(graph_nodes: list[GraphNode], *, prefer_langgraph: bool = True):
    if prefer_langgraph and langgraph_available():
        return LangGraphExecutor(graph_nodes)
    return SequentialExecutor(graph_nodes)


def topology_description() -> dict[str, Any]:
    return {
        "stages": [s.value for s in STAGE_ORDER],
        "fixed": True,
        "model_may_alter_topology": False,
        "conditional_edges": 0,
        "langgraph_available": langgraph_available(),
        "canonical_evidence": "artifact ledger and RESULTS_MANIFEST.json, not checkpoints",
    }


__all__ = [
    "AppMode",
    "GraphNode",
    "GraphTopologyError",
    "LangGraphExecutor",
    "SequentialExecutor",
    "assert_topology",
    "build_executor",
    "build_nodes",
    "langgraph_available",
    "topology_description",
]
