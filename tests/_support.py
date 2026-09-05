"""Shared synthetic fixtures.

Every test in this suite uses fabricated content. No real filing, no real
issuer, no model call. That is a hard rule: a test that needed a network or a
credential could not run in CI, and one that used real data would put private
material in the repository.
"""

from __future__ import annotations

from contextlib import contextmanager

from handoff_fidelity.models import Atom, AtomCausalRecord, AtomRole, VerificationStatus

FRAME_TEXT = (
    "Alder Ridge Holdings reported results for FY2019. "
    "North America segment margin improved by 6.2% during the period. "
    "Europe revenue declined 3.5% year over year. "
    "Further detail is provided in Note 12 to the consolidated statements."
)


@contextmanager
def raises(exc_type):
    """Minimal stand-in so the suite runs with or without pytest installed."""
    try:
        yield
    except exc_type:
        return
    except Exception as other:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


def atom(
    role: AtomRole,
    canonical: str,
    *,
    doc: str = "doc1",
    start: int = 0,
    surface: str | None = None,
    sentence: int = 0,
    verified: bool = True,
    occurrences: int = 1,
) -> Atom:
    surface = canonical if surface is None else surface
    return Atom(
        document_id=doc,
        atom_id=f"{doc}:{role.value}:{canonical}",
        role=role,
        canonical_value=canonical,
        surface_form=surface,
        char_start=start,
        char_end=start + len(surface),
        token_start=-1,
        token_end=-1,
        local_context="",
        sentence_index=sentence,
        verification=VerificationStatus.ACCEPTED if verified else VerificationStatus.UNVERIFIED,
        occurrence_count=occurrences,
    )


def inventory(n_roles: int = 4, per_role: int = 2, doc: str = "doc1") -> list[Atom]:
    roles = list(AtomRole)[:n_roles]
    return [
        atom(r, f"{r.value}-{i}", doc=doc, start=(ri * 100 + i * 10), sentence=i)
        for ri, r in enumerate(roles)
        for i in range(per_role)
    ]


def record(
    *,
    doc: str = "d0",
    aid: str = "a0",
    role: AtomRole = AtomRole.NUMERIC,
    pi: float = 0.5,
    t: int = 1,
    r_minus: float = 0.0,
    d_plus: float = 1.0,
) -> AtomCausalRecord:
    return AtomCausalRecord(
        document_id=doc,
        atom_id=aid,
        role=role,
        pi=pi,
        transmitted=t,
        r_minus=r_minus,
        d_plus=d_plus,
    )


class FakeTokenizer:
    """Whitespace tokenizer. Deterministic and dependency-free, so budget logic
    is testable without the frozen tokenizer installed."""

    name = "fake-whitespace"

    def encode(self, text: str) -> list[int]:
        return [len(w) for w in text.split()]

    def count(self, text: str) -> int:
        return len(text.split())

    def truncate(self, text: str, max_tokens: int) -> tuple[str, bool]:
        words = text.split()
        if len(words) <= max_tokens:
            return text, False
        return " ".join(words[:max_tokens]), True
