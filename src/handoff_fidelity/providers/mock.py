from __future__ import annotations

from .base import GenerationRequest, GenerationResult, Provider


class MockProvider(Provider):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            text="MOCK_OUTPUT",
            provider="mock",
            model=request.model,
            metadata={"network": "false"},
        )
