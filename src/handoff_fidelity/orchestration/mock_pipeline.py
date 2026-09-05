"""The mock end-to-end pipeline.

Runs the complete route -- synthetic source, atomizer, mock relay, matcher, mock
receiver, availability intervention, mock counterfactual receiver, estimators,
artifacts, telemetry, event stream -- with no network and no provider account.

Its purpose is to prove WIRING. Every number it produces is fabricated and has
ZERO evidentiary status; the run is labelled MOCK end to end and its artifacts
carry a synthetic marker so they can never be mistaken for results.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from ..app_contracts.events import EventLog
from ..app_contracts.modes import AppMode, RunKind
from ..providers.adapters import MockAdapter
from ..providers.ledger import ProviderLedger
from ..telemetry.spans import InMemoryTracer, build_tracer
from ..tokenization import get_tokenizer
from .fixtures.synthetic import (
    DEMO_PRIOR_KNOWLEDGE,
    SYNTHETIC_MDNA,
    make_receiver_script,
    relay_script,
)
from .graph import build_executor, build_nodes
from .state import RunState

SYNTHETIC_MARKER = "SYNTHETIC - MOCK RUN - NOT A SCIENTIFIC RESULT"

#: Chosen because it surfaces all three headline behaviours in one 3-focal run:
#: an atom transmitted and used, an atom omitted but RECONSTRUCTED, and an atom
#: omitted and lost. The resulting figures are A = 2/3 with C_comm = 0 and
#: C_recon = 2/3 -- every bit of endpoint correctness came from reconstruction
#: and none from communication, which is the phenomenon the project exists to
#: measure. The numbers are fabricated and prove nothing; they make the demo
#: legible.
DEMO_SEED = 2


@dataclass(frozen=True, slots=True)
class MockRunResult:
    state: RunState
    engine: str
    marker: str = SYNTHETIC_MARKER

    def to_dict(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "evidentiary_status": "NONE",
            "engine": self.engine,
            "summary": self.state.summary(),
            "decomposition": self.state.decomposition,
            "events": [e.to_dict() for e in self.state.events.all()],
            "provider_calls": self.state.ledger.summary(),
            "spans": (
                self.state.tracer.names() if isinstance(self.state.tracer, InMemoryTracer) else []
            ),
        }


def run_mock_pipeline(
    *,
    run_id: str | None = None,
    budget: int = 300,
    seed: int = DEMO_SEED,
    omit: tuple[str, ...] = ("Note 12", "North America"),
    reconstructs: tuple[str, ...] | None = None,
    prefer_langgraph: bool = False,
    source_text: str = SYNTHETIC_MDNA,
    document_id: str = "SYNTHETIC-MDNA-0001",
    window_tokens: int = 2000,
) -> MockRunResult:
    """Execute the full synthetic route.

    ``omit`` makes the scripted relay drop those atoms. ``reconstructs`` selects
    which roles the receiver "knows" from prior knowledge; ``None`` uses the full
    demo set. The combination reproduces the phenomenon under study: an endpoint
    that looks correct although the information was never transmitted.
    """
    rid = run_id or f"mock-{uuid.uuid4().hex[:12]}"

    relay = MockAdapter(script={"Handoff note:": relay_script(omit=omit)})
    prior = (
        dict(DEMO_PRIOR_KNOWLEDGE)
        if reconstructs is None
        else {role: value for role, value in DEMO_PRIOR_KNOWLEDGE.items() if role in reconstructs}
    )
    receiver = MockAdapter(script_fn=make_receiver_script(prior))

    state = RunState(
        run_id=rid,
        mode=AppMode.DEMO,
        kind=RunKind.MOCK,
        budget=budget,
        seed=seed,
        events=EventLog(rid),
        ledger=ProviderLedger(),
        tracer=build_tracer(),
    )

    tokenizer = get_tokenizer(allow_fallback=True)
    graph_nodes = build_nodes(
        provider=relay,
        model="mock-deterministic-v1",
        raw_text=source_text,
        document_id=document_id,
        window_tokens=window_tokens,
        tokenizer=tokenizer,
    )
    # The relay and the receiver are separate adapters with separate scripts,
    # exactly as they are separate models in a real run.
    from functools import partial

    from . import nodes as _nodes

    for i, node in enumerate(graph_nodes):
        if node.stage.value == "natural_receiver":
            graph_nodes[i] = type(node)(
                node.stage,
                partial(_nodes.natural_receiver, provider=receiver, model="mock-deterministic-v1"),
            )
        elif node.stage.value == "counterfactual_receiver":
            graph_nodes[i] = type(node)(
                node.stage,
                partial(
                    _nodes.counterfactual_receiver, provider=receiver, model="mock-deterministic-v1"
                ),
            )

    executor = build_executor(graph_nodes, prefer_langgraph=prefer_langgraph)
    state = executor.run(state)
    return MockRunResult(state=state, engine=executor.engine)
