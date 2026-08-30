from __future__ import annotations

from .base import GenerationRequest, GenerationResult, Provider


class OpenAIProvider(Provider):
    """Optional OpenAI Responses API adapter.

    Exact model/version belongs in the preregistration; this class intentionally
    has no default production model.
    """

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install with pip install -e '.[openai]'") from exc
        client = OpenAI()
        response = client.responses.create(
            model=request.model,
            instructions=request.system,
            input=request.prompt,
            max_output_tokens=request.max_tokens,
        )
        return GenerationResult(
            text=response.output_text,
            provider="openai",
            model=request.model,
            metadata={"response_id": str(response.id)},
        )
