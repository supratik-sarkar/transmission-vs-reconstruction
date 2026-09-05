"""Provider capability registry.

Every field defaults to UNKNOWN. Capabilities are resolved from official
provider documentation during the model-pinning phase, not guessed here -- a
wrong `seed_support` would silently change what decoder regime we believe we are
in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class Support(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    text_generation: Support = Support.UNKNOWN
    structured_output: Support = Support.UNKNOWN
    temperature_support: Support = Support.UNKNOWN
    seed_support: Support = Support.UNKNOWN
    streaming: Support = Support.UNKNOWN
    usage_reporting: Support = Support.UNKNOWN
    request_id: Support = Support.UNKNOWN
    pinned_model_snapshots: Support = Support.UNKNOWN
    max_context_tokens: int | None = None
    documentation_url: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Support):
                d[k] = v.value
        return d

    @property
    def unresolved_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in self.to_dict().items() if value == Support.UNKNOWN.value
        )


#: Shipped UNRESOLVED on purpose. Populating these from memory would be a guess
#: presented as a fact.
REGISTRY: dict[str, ProviderCapabilities] = {
    "openai": ProviderCapabilities(provider="openai"),
    "deepseek": ProviderCapabilities(provider="deepseek"),
    "anthropic": ProviderCapabilities(provider="anthropic"),
    "gemini": ProviderCapabilities(provider="gemini"),
    "mock": ProviderCapabilities(
        provider="mock",
        text_generation=Support.YES,
        structured_output=Support.YES,
        temperature_support=Support.NO,
        seed_support=Support.YES,
        streaming=Support.NO,
        usage_reporting=Support.YES,
        request_id=Support.YES,
        pinned_model_snapshots=Support.YES,
        max_context_tokens=1_000_000,
        resolved=True,
        documentation_url="in-repo deterministic stub",
    ),
}


def capabilities_for(provider: str) -> ProviderCapabilities:
    return REGISTRY.get(provider.lower(), ProviderCapabilities(provider=provider))
