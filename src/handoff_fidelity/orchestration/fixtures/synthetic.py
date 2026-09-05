"""Synthetic demonstration fixtures.

EVERY value here is fabricated. The issuer names are invented, the figures are
invented, and nothing in this module has any evidentiary status whatsoever. The
document identifiers are prefixed ``SYNTHETIC-`` so a fixture can never be
mistaken for a corpus document in a log, an artifact or a screenshot.

The pack is designed to exercise the cases a demo must show:

  * an atom transmitted and used
  * an atom omitted but reconstructed from prior knowledge
  * an atom omitted and lost
  * a negative availability surplus (interference)
  * a deletion intervention and an insertion intervention
  * multi-hop disappearance and multi-hop reconstruction
"""

from __future__ import annotations

from dataclasses import dataclass

SYNTHETIC_PREFIX = "SYNTHETIC-"

SYNTHETIC_MDNA = """\
Alder Ridge Holdings reported results for FY2019 across its principal segments.
North America segment margin improved by 6.2% during the period, reflecting
pricing discipline and a favourable product mix. Europe revenue declined 3.5%
year over year, driven by softness in the Commercial channel. Asia Pacific
delivered operating income growth of 11.4% in Q3 FY2019. Management notes that
the Consumer business absorbed $412.0 million of restructuring charges during
the year. Further detail on segment allocation is provided in Note 12 to the
consolidated statements. The Enterprise segment recorded a 2.8% decline in gross
margin, which management attributes to component costs. Additional commentary on
liquidity appears in Item 7A of this report.
"""

SECOND_HOP_SOURCE = """\
Brant Vale Systems reported FY2018 results. The Cloud segment margin improved by
4.9% while Latin America revenue grew 7.1%. Software gross margin declined 1.2%
in Q2 FY2018. Restructuring of $95.0 million was recorded. See Note 8 for
segment detail.
"""


@dataclass(frozen=True, slots=True)
class ScriptedCase:
    """One demonstrable behaviour, and what the receiver is scripted to answer."""

    label: str
    description: str
    canonical_value: str
    role: str
    transmitted: bool
    reconstructed_when_absent: bool
    note: str = ""


#: The demonstration matrix. Each row is a behaviour the UI must be able to show.
SCRIPTED_CASES: tuple[ScriptedCase, ...] = (
    ScriptedCase(
        "transmitted",
        "Present in the handoff and used by the receiver.",
        "6.2%",
        "numeric",
        transmitted=True,
        reconstructed_when_absent=False,
        note="Deletion intervention. Delta^av is positive: availability mattered.",
    ),
    ScriptedCase(
        "omitted_reconstructed",
        "Absent from the handoff, yet the receiver supplies it from prior knowledge.",
        "north america",
        "scope",
        transmitted=False,
        reconstructed_when_absent=True,
        note="Insertion intervention. The endpoint looks correct without transmission.",
    ),
    ScriptedCase(
        "omitted_lost",
        "Absent and not recovered.",
        "Note 12",
        "provenance",
        transmitted=False,
        reconstructed_when_absent=False,
        note="Insertion intervention. Delta^av is positive; the atom needed sending.",
    ),
    ScriptedCase(
        "negative_surplus",
        "Present, but its presence DEGRADES recovery through interference.",
        "FY2019",
        "period",
        transmitted=True,
        reconstructed_when_absent=True,
        note="Delta^av is negative. Under the overrun rule this cannot be displacement.",
    ),
)


def synthetic_documents() -> list[dict[str, str]]:
    return [
        {
            "document_id": f"{SYNTHETIC_PREFIX}MDNA-0001",
            "text": SYNTHETIC_MDNA,
            "issuer_id": f"{SYNTHETIC_PREFIX}ISSUER-A",
            "provenance": "fabricated",
        },
        {
            "document_id": f"{SYNTHETIC_PREFIX}MDNA-0002",
            "text": SECOND_HOP_SOURCE,
            "issuer_id": f"{SYNTHETIC_PREFIX}ISSUER-B",
            "provenance": "fabricated",
        },
    ]


def relay_script(*, omit: tuple[str, ...] = ()) -> str:
    """A relay message that deliberately omits the requested canonical values.

    Scripted rather than generated, so the demo shows the same behaviours every
    time and a UI test can assert on them.
    """
    lines = [
        "- entity: Alder Ridge Holdings",
        "- scope: North America",
        "- period: FY2019",
        "- numeric: 6.2%",
        "- provenance: Note 12",
    ]
    return "\n".join(
        line for line in lines if not any(o.casefold() in line.casefold() for o in omit)
    )


def mock_script(*, reconstructs: tuple[str, ...] = ()) -> dict[str, str]:
    """Receiver answers keyed by a fragment of the prompt.

    An atom in ``reconstructs`` is answered correctly even when the note does not
    contain it -- which is precisely the phenomenon under study.
    """
    script: dict[str, str] = {}
    for case in SCRIPTED_CASES:
        answer = (
            case.canonical_value
            if (case.transmitted or case.canonical_value in reconstructs)
            else "unknown"
        )
        script[f"the {case.role} value"] = answer
    return script


# --- a receiver mock that actually exhibits the phenomenon -------------------

_SLOT_ROLE = {
    "which company or organisation": "entity",
    "business segment or geography": "scope",
    "which reporting period": "period",
    "reported value of": "numeric",
    "which note, item or exhibit": "provenance",
}

_NOTE_START = "--- HANDOFF NOTE ---"
_NOTE_END = "--- END NOTE ---"


def _note_of(prompt: str) -> str:
    if _NOTE_START not in prompt or _NOTE_END not in prompt:
        return ""
    return prompt.split(_NOTE_START, 1)[1].split(_NOTE_END, 1)[0]


def _role_of(prompt: str) -> str:
    question = prompt.split("Question:", 1)[-1]
    for phrase, role in _SLOT_ROLE.items():
        if phrase in question:
            return role
    return ""


def make_receiver_script(prior_knowledge: dict[str, str] | None = None):
    r"""Build a deterministic receiver mock.

    Its answer is DERIVED, not looked up:

    1. if the handoff note states a value for the asked role, return it
       -- transmission followed by use, contributing to :math:`D^+`;
    2. otherwise, if the role appears in ``prior_knowledge``, return that
       -- reconstruction after omission, contributing to :math:`R^-`;
    3. otherwise return ``unknown`` -- omitted and lost.

    Step 2 is the entire phenomenon under study: an endpoint that looks correct
    although nothing was communicated. The receiver is never shown the focal
    value, exactly as in a real run.
    """
    prior = dict(prior_knowledge or {})

    def script(prompt: str) -> str:
        role = _role_of(prompt)
        if not role:
            return ""
        for line in _note_of(prompt).splitlines():
            if line.strip().startswith(f"- {role}:"):
                return line.split(":", 1)[1].strip()
        return prior.get(role, "unknown")

    return script


#: Declared prior knowledge for the demo receiver. Fabricated, and chosen so the
#: fixture pack exhibits reconstruction on some roles and loss on others.
DEMO_PRIOR_KNOWLEDGE: dict[str, str] = {
    "scope": "North America",  # reconstructed when omitted
    "entity": "Alder Ridge Holdings",
    "period": "FY2019",
    # numeric and provenance deliberately absent: omitted -> lost
}
