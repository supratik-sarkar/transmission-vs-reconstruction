"""The provider protocol.

The scientific core never imports a vendor SDK. It sees only this protocol, so
swapping a provider cannot change a measurement path, and a missing SDK degrades
to NOT_CONFIGURED instead of an import-time crash.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from .capabilities import ProviderCapabilities, capabilities_for


class ProviderState(StrEnum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SDK_MISSING = "SDK_MISSING"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Everything a provider needs. Deliberately carries no credential: the
    adapter reads that from the environment at call time."""

    prompt: str
    max_output_tokens: int
    model: str
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int | None = 0
    stop: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    text: str
    provider: str
    requested_model: str
    returned_model: str = ""
    provider_request_id: str = ""
    input_tokens: int = -1
    output_tokens: int = -1
    latency_s: float = 0.0
    finish_reason: str = ""
    raw_ref: str = ""  # pointer into private raw storage; never the payload
    system_fingerprint: str = ""
    reasoning_tokens: int = 0


@runtime_checkable
class Provider(Protocol):
    name: str

    def state(self) -> ProviderState: ...
    def capabilities(self) -> ProviderCapabilities: ...
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


class ProviderNotConfigured(RuntimeError):
    pass


class NetworkDisabled(RuntimeError):
    pass


@dataclass(slots=True)
class BaseProviderAdapter:
    """Shared behaviour. Subclasses implement ``_generate`` only.

    Every guard here fails CLOSED. In particular ``allow_network`` defaults to
    False, so an adapter cannot reach the internet by accident during a test.
    """

    name: str
    key_env: str
    sdk_module: str
    model: str = "UNFROZEN"
    base_url: str = ""
    allow_network: bool = False
    enabled: bool = True

    def __repr__(self) -> str:  # security-relevant: never render config secrets
        return f"{type(self).__name__}(name={self.name!r}, model={self.model!r})"

    # -- status ----------------------------------------------------------
    def has_key(self) -> bool:
        """Presence only. The value is never read into a variable that could be
        logged, formatted or returned."""
        return bool(os.environ.get(self.key_env, "").strip())

    def sdk_available(self) -> bool:
        from importlib.util import find_spec

        try:
            return find_spec(self.sdk_module) is not None
        except (ImportError, ValueError):
            return False

    def model_pinned(self) -> bool:
        return bool(self.model) and self.model != "UNFROZEN"

    def state(self) -> ProviderState:
        if not self.enabled:
            return ProviderState.DISABLED
        if not self.sdk_available():
            return ProviderState.SDK_MISSING
        if not self.has_key():
            return ProviderState.NOT_CONFIGURED
        return ProviderState.CONFIGURED

    def capabilities(self) -> ProviderCapabilities:
        return capabilities_for(self.name)

    def status_dict(self) -> dict[str, Any]:
        """The ONLY provider shape that reaches the API and the browser.
        No key, no prefix, no suffix, no length."""
        return {
            "provider": self.name,
            "state": self.state().value,
            "sdk_available": self.sdk_available(),
            "secret_configured": self.has_key(),
            "model_pinned": self.model_pinned(),
            "model": self.model if self.model_pinned() else None,
            "capabilities_resolved": self.capabilities().resolved,
        }

    # -- execution -------------------------------------------------------
    def _preflight(self, request: GenerationRequest) -> None:
        if not self.enabled:
            raise ProviderNotConfigured(f"{self.name}: adapter disabled")
        if not self.model_pinned():
            raise ProviderNotConfigured(
                f"{self.name}: model identifier is not pinned. A moving alias would "
                "make every measurement unreproducible."
            )
        if not self.sdk_available():
            raise ProviderNotConfigured(f"{self.name}: SDK {self.sdk_module!r} is not installed")
        if not self.has_key():
            raise ProviderNotConfigured(
                f"{self.name}: {self.key_env} is not set. Credentials are read from "
                "the environment only."
            )
        if not self.allow_network:
            raise NetworkDisabled(
                f"{self.name}: network access is disabled. No provider request is made "
                "during architecture builds, tests or CI."
            )
        if request.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._preflight(request)
        return self._generate(request)

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError
