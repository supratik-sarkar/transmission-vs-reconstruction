from __future__ import annotations

from .base import Provider
from .mock import MockProvider


def get_provider(name: str) -> Provider:
    key = name.lower()
    if key == "mock":
        return MockProvider()
    if key == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    if key == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if key == "gemini":
        from .gemini_provider import GeminiProvider

        return GeminiProvider()
    if key in {"hf", "huggingface"}:
        from .hf_provider import HuggingFaceLocalProvider

        return HuggingFaceLocalProvider()
    raise ValueError(f"Unknown provider: {name}")


__all__ = ["Provider", "get_provider"]
