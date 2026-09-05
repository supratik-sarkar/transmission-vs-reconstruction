"""Provider construction.

Real providers are declared but NOT activated: constructing one requires an
explicit ``allow_network=True`` and a pinned model, and every call path is
guarded. The default everywhere in this repository is the mock.
"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider, ProviderNotConfigured
from .mock import MockProvider

KNOWN_PROVIDERS: tuple[str, ...] = ("mock", "openai", "anthropic", "gemini", "huggingface")

_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "huggingface": "HF_TOKEN",
}


class RemoteProvider(BaseProvider):
    """Placeholder for an OpenAI-compatible / Anthropic / Gemini endpoint.

    The call itself is intentionally unimplemented in this repository. Wiring it
    requires the optional client extra, a pinned model recorded in the freeze
    record, and ``allow_network=True``.
    """

    def generate(self, prompt: str, *, max_tokens: int, **kwargs: Any) -> str:
        self._require_pinned()
        self._require_key()
        self._require_network()
        raise NotImplementedError(
            f"{self.name}: the live call is an explicit integration point. Implement it "
            "against the pinned client version, log the request id but never the key, "
            "and record the exact model revision in the freeze record."
        )


class LocalHFProvider(BaseProvider):
    """Local open-weight inference. Optional; requires the 'hf' extra and a
    device from ``compute.router``."""

    def generate(self, prompt: str, *, max_tokens: int, **kwargs: Any) -> str:
        self._require_pinned()
        raise NotImplementedError(
            "local Hugging Face inference is an explicit integration point; select a "
            "device with compute.router.detect() and pin the checkpoint revision."
        )


def build_provider(
    kind: str, model: str, *, allow_network: bool = False, **kwargs: Any
) -> BaseProvider:
    kind = kind.strip().lower()
    if kind not in KNOWN_PROVIDERS:
        raise ProviderNotConfigured(f"unknown provider {kind!r}; known: {KNOWN_PROVIDERS}")
    if kind == "mock":
        return MockProvider(model=model or "mock-deterministic-v1", allow_network=False, **kwargs)
    if kind == "huggingface":
        return LocalHFProvider(model=model, name=kind, allow_network=allow_network, **kwargs)
    provider = RemoteProvider(model=model, name=kind, allow_network=allow_network, **kwargs)
    provider._key_env = _KEY_ENV[kind]
    return provider
