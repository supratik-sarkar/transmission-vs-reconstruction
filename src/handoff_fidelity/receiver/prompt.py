"""Receiver prompt construction.

A SINGLE shared receiver prompt is used for the natural arm, the counterfactual
arm, the matched-skeleton arms and the no-evidence baseline. If the arms used
different prompts, a prompt difference would confound the availability
contrast, which is the entire estimand.
"""

from __future__ import annotations

import hashlib

from ..models import AtomRole
from .slots import SLOT_SCHEMAS

RECEIVER_INSTRUCTION = (
    "You are given a handoff note written by another analyst. Answer the "
    "question using the note. If the note does not state the answer, give your "
    "best single answer anyway. Reply with the requested field value only, with "
    "no explanation, no units of explanation, and no surrounding sentence."
)

NO_EVIDENCE_MARKER = "(no note was provided)"


def build_receiver_prompt(*, message: str, role: AtomRole, subject: str, attribute: str) -> str:
    schema = SLOT_SCHEMAS[role]
    question = schema.render(subject=subject, attribute=attribute)
    note = message.strip() if message.strip() else NO_EVIDENCE_MARKER
    return (
        f"{RECEIVER_INSTRUCTION}\n\n"
        f"--- HANDOFF NOTE ---\n{note}\n--- END NOTE ---\n\n"
        f"Question: {question}\n"
        f"Answer format: {schema.answer_format}\n"
        f"Answer:"
    )


def build_no_evidence_prompt(*, role: AtomRole, subject: str, attribute: str) -> str:
    """The empirical chance baseline: the same slot, no evidence at all.

    This is the operative chance level. The nominal 1/K_c is an upper bound
    only, because a receiver free to answer outside the candidate set matches
    with probability P(output in K_c)/K_c <= 1/K_c.
    """
    return build_receiver_prompt(message="", role=role, subject=subject, attribute=attribute)


def build_prior_probe_prompt(*, role: AtomRole, subject: str, attribute: str) -> str:
    """Closed-book probe, fresh context, one focal atom per query.

    A batched vector over all slots of a document would let earlier slots
    condition later ones, so the probe would partly measure self-conditioning
    rather than prior access.
    """
    schema = SLOT_SCHEMAS[role]
    question = schema.render(subject=subject, attribute=attribute)
    return (
        "Answer from your own knowledge. No document is provided.\n"
        "Reply with the requested field value only.\n\n"
        f"Question: {question}\n"
        f"Answer format: {schema.answer_format}\n"
        f"Answer:"
    )


def prompt_hashes() -> dict[str, str]:
    def h(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    return {
        "receiver_instruction": h(RECEIVER_INSTRUCTION),
        "slot_schemas": h(
            "\n".join(
                f"{r.value}|{s.question_template}|{s.answer_format}"
                for r, s in sorted(SLOT_SCHEMAS.items(), key=lambda kv: kv[0].value)
            )
        ),
    }
