"""Standard controls.

Every final primary table carries all four:

  * Full context      -- reference only, NOT budget matched.
  * Head truncation   -- the trivial fixed-budget baseline.
  * Uniform atoms     -- the SAME renderer as CausalRelay, uniform selection.
  * Vanilla LLM relay -- a fixed-budget relay under the frozen global task.

The uniform-atoms control is mandatory: holding the renderer fixed, CausalRelay
versus Uniform isolates allocation policy rather than structured rendering.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..causalrelay.renderer import render_message, rendered_token_cost
from ..models import Atom
from ..relay.task import GLOBAL_DOWNSTREAM_TASK
from .base import AdapterStatus, BaseCompressor, BenchmarkRole


@dataclass(slots=True)
class FullContext(BaseCompressor):
    name: str = "full_context"
    revision: str = "control-v1"
    status: AdapterStatus = AdapterStatus.READY
    role: BenchmarkRole = BenchmarkRole.CONTROL

    def _compress(self, source_text, downstream_task, token_budget, config):
        return source_text, ("not budget matched: reference upper bound only",)

    def compress(self, *args: Any, **kwargs: Any):
        # Explicit unbound call rather than zero-argument super(): @dataclass(slots=True)
        # rebuilds the class, which leaves the implicit __class__ cell pointing at the
        # pre-rebuild type and makes super() raise at runtime.
        kwargs["enforce_budget"] = False
        return BaseCompressor.compress(self, *args, **kwargs)


@dataclass(slots=True)
class HeadTruncation(BaseCompressor):
    name: str = "head_truncation"
    revision: str = "control-v1"
    status: AdapterStatus = AdapterStatus.READY
    role: BenchmarkRole = BenchmarkRole.CONTROL

    def _compress(self, source_text, downstream_task, token_budget, config):
        if self.tokenizer is None:
            raise RuntimeError("head truncation requires a tokenizer")
        text, truncated = self.tokenizer.truncate(source_text, token_budget)
        return text.rstrip(), (("truncated",) if truncated else ())


@dataclass(slots=True)
class UniformAtoms(BaseCompressor):
    """Uniform random atom selection rendered by the SHARED renderer."""

    name: str = "uniform_atoms"
    revision: str = "control-v1"
    status: AdapterStatus = AdapterStatus.READY
    role: BenchmarkRole = BenchmarkRole.CONTROL
    atoms: Sequence[Atom] = ()
    seed: int = 0

    def _compress(self, source_text, downstream_task, token_budget, config):
        if self.tokenizer is None:
            raise RuntimeError("uniform atoms requires a tokenizer")
        ordered = sorted(self.atoms, key=lambda a: a.atom_id)
        rng = random.Random(self.seed)
        shuffled = ordered[:]
        rng.shuffle(shuffled)
        chosen: list[Atom] = []
        spent = 0
        for atom in shuffled:
            cost = rendered_token_cost(atom, self.tokenizer)
            if spent + cost <= token_budget:
                chosen.append(atom)
                spent += cost
        message = render_message(chosen)
        while chosen and self.tokenizer.count(message) > token_budget:
            chosen.pop()
            message = render_message(chosen)
        return message, ()


@dataclass(slots=True)
class VanillaRelay(BaseCompressor):
    """A fixed-budget LLM relay under the frozen global downstream task.

    The relay never receives focal-specific instructions: it sees exactly the
    same task text as every other query-aware method.
    """

    name: str = "vanilla_relay"
    revision: str = "control-v1"
    status: AdapterStatus = AdapterStatus.READY
    role: BenchmarkRole = BenchmarkRole.CONTROL
    provider: Any = None

    def _compress(self, source_text, downstream_task, token_budget, config):
        if self.provider is None:
            raise RuntimeError(
                "vanilla_relay requires a provider. Use the mock provider for dry runs; "
                "a real provider must be pinned in the preregistration first."
            )
        if downstream_task.strip() != GLOBAL_DOWNSTREAM_TASK.strip():
            raise AssertionError(
                "vanilla_relay received a task other than the frozen global downstream task"
            )
        prompt = (
            f"{downstream_task}\n\n"
            f"Token budget: {token_budget}.\n\n"
            f"--- SOURCE ---\n{source_text}\n--- END SOURCE ---\n\nHandoff note:"
        )
        text = self.provider.generate(prompt, max_tokens=token_budget)
        warnings: tuple[str, ...] = ()
        if self.tokenizer and self.tokenizer.count(text) > token_budget:
            text, _ = self.tokenizer.truncate(text, token_budget)
            warnings = ("hard-truncated to budget",)
        return text.rstrip(), warnings
