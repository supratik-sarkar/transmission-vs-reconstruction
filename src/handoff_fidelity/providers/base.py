from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationRequest:
    model: str
    system: str
    prompt: str
    max_tokens: int
    temperature: float | None = None
    seed: int | None = None


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    metadata: dict[str, str]


class Provider(ABC):
    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise NotImplementedError
