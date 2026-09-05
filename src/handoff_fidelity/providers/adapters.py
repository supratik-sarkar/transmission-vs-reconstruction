"""Concrete provider adapters.

Each is a distinct class even where the wire protocol overlaps. DeepSeek exposes
an OpenAI-compatible surface, but treating them as one adapter would erase the
per-provider metadata the ledger needs and would let an OpenAI-specific
assumption silently govern a DeepSeek run.

No adapter performs a request during this build: ``allow_network`` defaults to
False and ``_preflight`` refuses before any client is constructed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .protocol import (
    BaseProviderAdapter,
    GenerationRequest,
    GenerationResponse,
)


@dataclass(slots=True)
class OpenAIAdapter(BaseProviderAdapter):
    name: str = "openai"
    key_env: str = "OPENAI_API_KEY"
    sdk_module: str = "openai"

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        # Integration point. A compliant implementation constructs the client
        # from the environment, uses the Responses API, and records the RETURNED
        # model identifier alongside the requested one -- they differ whenever a
        # provider resolves an alias to a snapshot, and only the returned value
        # is reproducible.
        raise NotImplementedError(
            "OpenAI execution is an explicit integration point, enabled in the "
            "provider-validation phase. It must record: returned model, request id, "
            "usage, latency and finish reason; and must never log the key."
        )


@dataclass(slots=True)
class DeepSeekAdapter(BaseProviderAdapter):
    name: str = "deepseek"
    key_env: str = "DEEPSEEK_API_KEY"
    sdk_module: str = "openai"  # OpenAI-compatible client
    base_url: str = ""  # from configuration; never hard-coded

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError(
            "DeepSeek execution is an explicit integration point. Although the HTTP "
            "surface is OpenAI-compatible, its metadata is recorded separately: the "
            "providers are not interchangeable for provenance purposes."
        )

    def status_dict(self) -> dict[str, Any]:
        # Explicit unbound call, not zero-argument super(): @dataclass(slots=True)
        # rebuilds the class, which leaves the implicit __class__ cell pointing at
        # the pre-rebuild type and makes super() raise at runtime.
        d = BaseProviderAdapter.status_dict(self)
        d["openai_compatible_transport"] = True
        d["base_url_configured"] = bool(self.base_url)
        return d


@dataclass(slots=True)
class AnthropicAdapter(BaseProviderAdapter):
    name: str = "anthropic"
    key_env: str = "ANTHROPIC_API_KEY"
    sdk_module: str = "anthropic"

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError("Anthropic execution is an explicit integration point.")


@dataclass(slots=True)
class GeminiAdapter(BaseProviderAdapter):
    name: str = "gemini"
    key_env: str = "GEMINI_API_KEY"
    sdk_module: str = "google.genai"

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError("Gemini execution is an explicit integration point.")


@dataclass(slots=True)
class MockAdapter(BaseProviderAdapter):
    """Deterministic scripted provider.

    Not a language-model simulator. Its outputs exist to exercise wiring and have
    ZERO evidentiary value; anything produced with it is labelled MOCK end to end.
    """

    name: str = "mock"
    key_env: str = "HANDOFF_MOCK_KEY"
    sdk_module: str = "handoff_fidelity"
    model: str = "mock-deterministic-v1"
    script: dict[str, str] | None = None
    #: A callable script takes the prompt and returns the reply. Used by the
    #: receiver mock, which must DERIVE its answer from the note plus a declared
    #: prior-knowledge set rather than look it up -- otherwise the demo cannot
    #: exhibit reconstruction at all.
    script_fn: Any = None
    fail_on: tuple[str, ...] = ()
    latency_s: float = 0.0

    def has_key(self) -> bool:
        return True  # no credential exists or is needed

    def state(self):
        from .protocol import ProviderState

        return ProviderState.DISABLED if not self.enabled else ProviderState.CONFIGURED

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        # Bypasses the network guard by design: it never touches a network.
        if not self.enabled:
            from .protocol import ProviderNotConfigured

            raise ProviderNotConfigured("mock: adapter disabled")
        return self._generate(request)

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        from .protocol import NetworkDisabled

        started = time.perf_counter()
        for trigger in self.fail_on:
            if trigger and trigger in request.prompt:
                raise NetworkDisabled(f"mock scripted failure on trigger {trigger!r}")
        if self.latency_s:
            time.sleep(min(self.latency_s, 0.05))

        text = ""
        if self.script_fn is not None:
            text = self.script_fn(request.prompt)
        elif self.script:
            # Longest key first, so a specific script entry beats a general one.
            for key in sorted(self.script, key=len, reverse=True):
                if key and key in request.prompt:
                    text = self.script[key]
                    break
        elapsed = time.perf_counter() - started
        return GenerationResponse(
            text=text,
            provider=self.name,
            requested_model=request.model or self.model,
            returned_model=self.model,
            provider_request_id=f"mock-{abs(hash(request.prompt)) % 10**10:010d}",
            input_tokens=len(request.prompt.split()),
            output_tokens=len(text.split()),
            latency_s=elapsed,
            finish_reason="stop",
        )


ADAPTERS = {
    "openai": OpenAIAdapter,
    "deepseek": DeepSeekAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "mock": MockAdapter,
}
PROVIDER_ORDER: tuple[str, ...] = ("openai", "deepseek", "anthropic", "gemini", "mock")


def build_adapter(provider: str, **kwargs: Any) -> BaseProviderAdapter:
    key = provider.strip().lower()
    if key not in ADAPTERS:
        from .protocol import ProviderNotConfigured

        raise ProviderNotConfigured(
            f"unknown provider {provider!r}; known: {', '.join(PROVIDER_ORDER)}"
        )
    return ADAPTERS[key](**kwargs)


def provider_status_table() -> list[dict[str, Any]]:
    """Status for every provider. This is what the UI renders."""
    return [build_adapter(p).status_dict() for p in PROVIDER_ORDER]
