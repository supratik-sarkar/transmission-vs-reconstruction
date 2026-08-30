from __future__ import annotations

from .base import GenerationRequest, GenerationResult, Provider


class AnthropicProvider(Provider):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install with pip install -e '.[anthropic]'") from exc
        client = Anthropic()
        message = client.messages.create(
            model=request.model,
            system=request.system,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": request.prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        return GenerationResult(
            text=text,
            provider="anthropic",
            model=request.model,
            metadata={"response_id": str(message.id)},
        )
