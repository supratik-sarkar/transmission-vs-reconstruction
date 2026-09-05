"""Provider abstraction.

Rules enforced across every provider:

  * API keys are read from the ENVIRONMENT only. They are never accepted as
    arguments, never written to disk, never placed in a log line and never
    included in a repr.
  * A provider refuses to run unless its model identifier has been pinned.
  * Determinism is a PROPERTY TO BE MEASURED, not a flag to be asserted. See
    ``determinism.audit``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderNotConfigured(RuntimeError):
    pass


class NetworkDisabled(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str, *, max_tokens: int, **kwargs: Any) -> str: ...


@dataclass(slots=True)
class BaseProvider:
    model: str
    name: str = "base"
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int | None = 0
    max_retries: int = 0
    allow_network: bool = False
    _key_env: str = field(default="", repr=False)

    def __repr__(self) -> str:  # pragma: no cover - trivial but security relevant
        return f"{type(self).__name__}(model={self.model!r}, name={self.name!r})"

    def _require_key(self) -> str:
        value = os.environ.get(self._key_env, "").strip()
        if not value:
            raise ProviderNotConfigured(
                f"{self.name}: {self._key_env} is not set in the environment. "
                "Credentials are read from the environment only."
            )
        return value

    def _require_network(self) -> None:
        if not self.allow_network:
            raise NetworkDisabled(
                f"{self.name}: network access is disabled. No provider call is made "
                "during repository construction, testing or CI."
            )

    def _require_pinned(self) -> None:
        if not self.model or self.model == "UNFROZEN":
            raise ProviderNotConfigured(
                f"{self.name}: model identifier is not pinned. A moving alias would "
                "make the study unreproducible."
            )

    def decoding_config(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "model": self.model,
            "provider": self.name,
        }

    def generate(self, prompt: str, *, max_tokens: int, **kwargs: Any) -> str:
        raise NotImplementedError
