"""Graph nodes.

Every node is a thin wrapper that calls an EXISTING scientific primitive and
records an event. No causal mathematics lives here; if a node computed an
estimand itself, the orchestration layer would have quietly become a second
implementation of the science.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from ..app_contracts.events import EventStatus, EventType, Stage
from ..atomizer.rules import atomize
from ..atomizer.verify import filter_eligible
from ..causal.estimands import decompose
from ..causalrelay.renderer import render_atom
from ..corpus.frame import assert_inventory_within_frame, build_source_frame
from ..editing.editor import InvalidEdit, build_counterfactual
from ..matcher.match import is_transmitted, recovered
from ..models import AtomCausalRecord
from ..providers.ledger import CallStatus, ProviderCall, content_hash, new_call_id, utcnow
from ..providers.protocol import GenerationRequest
from ..receiver.prompt import build_receiver_prompt
from ..relay.task import GLOBAL_DOWNSTREAM_TASK
from ..sampling.design import all_inclusion_probabilities, select_focal
from .state import RunState

NodeFn = Callable[[RunState], RunState]


def _emit(
    state: RunState, stage: Stage, event_type: EventType, status: EventStatus, **payload
) -> None:
    state.events.append(stage, event_type, status, payload)


def _span(state: RunState, name: str, **attrs):
    from contextlib import nullcontext

    if state.tracer is None:
        return nullcontext()
    return state.tracer.span(name, run_id=state.run_id, **attrs)


def prepare_run(state: RunState) -> RunState:
    _emit(
        state,
        Stage.PREPARE_RUN,
        EventType.RUN_STARTED,
        EventStatus.RUNNING,
        mode=state.mode.value,
        kind=state.kind.value,
        budget=state.budget,
    )
    return state


def load_source(
    state: RunState, *, raw_text: str, document_id: str, window_tokens: int, tokenizer
) -> RunState:
    _emit(state, Stage.LOAD_SOURCE, EventType.STAGE_STARTED, EventStatus.RUNNING)
    with _span(state, "handoff.source.load", document_id=document_id):
        state.source_frame = build_source_frame(
            document_id=document_id,
            raw_text=raw_text,
            window_tokens=window_tokens,
            tokenizer=tokenizer,
            section="full",
            require_section=False,
        )
    _emit(
        state,
        Stage.LOAD_SOURCE,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        source_sha256=state.source_frame.sha256,
        token_count=state.source_frame.token_count,
        truncated=state.source_frame.truncated,
    )
    return state


def atomize_source(state: RunState) -> RunState:
    assert state.source_frame is not None
    _emit(state, Stage.ATOMIZE, EventType.STAGE_STARTED, EventStatus.RUNNING)
    with _span(state, "handoff.atomize"):
        atoms = atomize(state.source_frame.document_id, state.source_frame.text)
        # The inventory must lie inside the relay-visible frame. Checked, not assumed.
        assert_inventory_within_frame(state.source_frame, atoms)
        report = filter_eligible(atoms, state.source_frame.text, require_human_verification=False)
    state.atoms = tuple(atoms)
    state.eligible = report.eligible
    _emit(
        state,
        Stage.ATOMIZE,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        n_atoms=len(atoms),
        n_eligible=len(report.eligible),
        exclusion_rates=report.rates(),
    )
    return state


def sample_focals(state: RunState) -> RunState:
    _emit(state, Stage.SAMPLE_FOCALS, EventType.STAGE_STARTED, EventStatus.RUNNING)
    with _span(state, "handoff.sample"):
        rng = random.Random(state.seed)
        # Sampling happens BEFORE the relay and is never shown to it.
        focals = select_focal(list(state.eligible), rng=rng)
        pis = all_inclusion_probabilities(list(state.eligible))
    state.focals = tuple(focals)
    _emit(
        state,
        Stage.SAMPLE_FOCALS,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        n_focals=len(focals),
        sum_pi=round(sum(pis.values()), 12),
        roles=[f.role.value for f in focals],
    )
    return state


def run_relay(state: RunState, *, provider, model: str) -> RunState:
    assert state.source_frame is not None
    _emit(state, Stage.RELAY, EventType.STAGE_STARTED, EventStatus.RUNNING)
    prompt = (
        f"{GLOBAL_DOWNSTREAM_TASK}\n\nToken budget: {state.budget}.\n\n"
        f"--- SOURCE ---\n{state.source_frame.text}\n--- END SOURCE ---\n\nHandoff note:"
    )
    started = utcnow()
    with _span(state, "handoff.relay", provider=provider.name, budget=state.budget):
        response = provider.generate(
            GenerationRequest(
                prompt=prompt,
                max_output_tokens=state.budget,
                model=model,
                seed=state.seed,
            )
        )
    state.relay_message = response.text
    state.ledger.append(
        ProviderCall(
            call_id=new_call_id(state.run_id, "relay", 1),
            run_id=state.run_id,
            provider=response.provider,
            requested_model=response.requested_model,
            returned_model=response.returned_model,
            attempt=1,
            started_at=started,
            completed_at=utcnow(),
            latency_s=response.latency_s,
            status=CallStatus.OK,
            prompt_hash=content_hash(prompt),
            request_hash=content_hash(prompt),
            response_hash=content_hash(response.text),
            provider_request_id=response.provider_request_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stage="relay",
        )
    )
    _emit(
        state,
        Stage.RELAY,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        message_chars=len(response.text),
        provider=response.provider,
    )
    return state


def match_transmission(state: RunState) -> RunState:
    _emit(state, Stage.MATCH_TRANSMISSION, EventType.STAGE_STARTED, EventStatus.RUNNING)
    by_id = {a.atom_id: a for a in state.eligible}
    with _span(state, "handoff.transmission.match"):
        for focal in state.focals:
            atom = by_id[focal.atom_id]
            state.transmission[atom.atom_id] = int(
                is_transmitted(
                    state.relay_message,
                    canonical_value=atom.canonical_value,
                    role=atom.role.value,
                )
            )
    _emit(
        state,
        Stage.MATCH_TRANSMISSION,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        transmitted=sum(state.transmission.values()),
        n=len(state.transmission),
    )
    return state


def _ask_receiver(
    state: RunState, provider, model: str, atom, message: str, stage_label: str, sequence: int
) -> int:
    prompt = build_receiver_prompt(
        message=message,
        role=atom.role,
        subject=state.source_frame.document_id if state.source_frame else "the source",
        attribute=f"the {atom.role.value} value",
    )
    started = utcnow()
    response = provider.generate(
        GenerationRequest(
            prompt=prompt,
            max_output_tokens=64,
            model=model,
            seed=state.seed,
        )
    )
    state.ledger.append(
        ProviderCall(
            call_id=new_call_id(state.run_id, stage_label, sequence),
            run_id=state.run_id,
            provider=response.provider,
            requested_model=response.requested_model,
            returned_model=response.returned_model,
            attempt=1,
            started_at=started,
            completed_at=utcnow(),
            latency_s=response.latency_s,
            status=CallStatus.OK,
            prompt_hash=content_hash(prompt),
            request_hash=content_hash(prompt),
            response_hash=content_hash(response.text),
            provider_request_id=response.provider_request_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stage=stage_label,
        )
    )
    return int(recovered(response.text, canonical_value=atom.canonical_value, role=atom.role.value))


def natural_receiver(state: RunState, *, provider, model: str) -> RunState:
    _emit(state, Stage.NATURAL_RECEIVER, EventType.STAGE_STARTED, EventStatus.RUNNING)
    by_id = {a.atom_id: a for a in state.eligible}
    with _span(state, "handoff.receiver.natural"):
        for i, focal in enumerate(state.focals, start=1):
            atom = by_id[focal.atom_id]
            state.natural_outcomes[atom.atom_id] = _ask_receiver(
                state,
                provider,
                model,
                atom,
                state.relay_message,
                "receiver_natural",
                i,
            )
    _emit(
        state,
        Stage.NATURAL_RECEIVER,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        recovered=sum(state.natural_outcomes.values()),
    )
    return state


def construct_interventions(state: RunState) -> RunState:
    """Build ONLY the missing availability arm. The natural message is never edited."""
    _emit(state, Stage.CONSTRUCT_INTERVENTIONS, EventType.STAGE_STARTED, EventStatus.RUNNING)
    by_id = {a.atom_id: a for a in state.eligible}
    with _span(state, "handoff.intervention.construct"):
        for focal in state.focals:
            atom = by_id[focal.atom_id]
            t = state.transmission[atom.atom_id]
            try:
                result = build_counterfactual(
                    state.relay_message,
                    document_id=atom.document_id,
                    atom_id=atom.atom_id,
                    canonical_value=atom.canonical_value,
                    role=atom.role.value,
                    transmitted=t,
                    rendered=render_atom(atom),
                    budget=state.budget,
                )
            except InvalidEdit as exc:
                # Recorded, never silently dropped: the failure rate is a
                # reported quantity with a STOP_AND_REPAIR cap.
                state.failed_edits[atom.atom_id] = str(exc)
                continue
            state.counterfactual_messages[atom.atom_id] = result.text
            state.edit_mechanisms[atom.atom_id] = result.log.mechanism
    _emit(
        state,
        Stage.CONSTRUCT_INTERVENTIONS,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        constructed=len(state.counterfactual_messages),
        failed=len(state.failed_edits),
    )
    return state


def counterfactual_receiver(state: RunState, *, provider, model: str) -> RunState:
    _emit(state, Stage.COUNTERFACTUAL_RECEIVER, EventType.STAGE_STARTED, EventStatus.RUNNING)
    by_id = {a.atom_id: a for a in state.eligible}
    with _span(state, "handoff.receiver.counterfactual"):
        for i, (atom_id, message) in enumerate(sorted(state.counterfactual_messages.items()), 1):
            state.counterfactual_outcomes[atom_id] = _ask_receiver(
                state,
                provider,
                model,
                by_id[atom_id],
                message,
                "receiver_counterfactual",
                i,
            )
    _emit(
        state,
        Stage.COUNTERFACTUAL_RECEIVER,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        n=len(state.counterfactual_outcomes),
    )
    return state


def deterministic_match(state: RunState) -> RunState:
    """Assemble atom records. Under regime (D) the natural and counterfactual
    queries ARE the two potential outcomes."""
    _emit(state, Stage.DETERMINISTIC_MATCH, EventType.STAGE_STARTED, EventStatus.RUNNING)
    by_focal = {f.atom_id: f for f in state.focals}
    records: list[AtomCausalRecord] = []
    with _span(state, "handoff.match"):
        for atom_id, focal in sorted(by_focal.items()):
            if atom_id not in state.counterfactual_outcomes:
                continue
            t = state.transmission[atom_id]
            natural = state.natural_outcomes[atom_id]
            counterfactual = state.counterfactual_outcomes[atom_id]
            d_plus, r_minus = (natural, counterfactual) if t == 1 else (counterfactual, natural)
            records.append(
                AtomCausalRecord(
                    document_id=focal.document_id,
                    atom_id=atom_id,
                    role=focal.role,
                    pi=focal.pi,
                    transmitted=t,
                    r_minus=float(r_minus),
                    d_plus=float(d_plus),
                    edit_mechanism=state.edit_mechanisms.get(atom_id, ""),
                )
            )
    state.records = tuple(records)
    _emit(
        state,
        Stage.DETERMINISTIC_MATCH,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        n_records=len(records),
    )
    return state


def estimate(state: RunState) -> RunState:
    """Delegates entirely to the tested estimator. No arithmetic here."""
    _emit(state, Stage.ESTIMATE, EventType.STAGE_STARTED, EventStatus.RUNNING)
    if not state.records:
        state.warnings.append("no instrumented records; estimation skipped")
        _emit(state, Stage.ESTIMATE, EventType.STAGE_COMPLETED, EventStatus.SKIPPED)
        return state
    with _span(state, "handoff.estimate", n_records=len(state.records)):
        state.decomposition = decompose(state.records).to_dict()
    _emit(
        state,
        Stage.ESTIMATE,
        EventType.STAGE_COMPLETED,
        EventStatus.OK,
        identity_residual=state.decomposition["identity_residual"],
    )
    return state
