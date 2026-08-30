from __future__ import annotations

from .base import GenerationRequest, GenerationResult, Provider


class GeminiProvider(Provider):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install with pip install -e '.[gemini]'") from exc
        client = genai.Client()
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        response = client.models.generate_content(
            model=request.model,
            contents=request.prompt,
            config=config,
        )
        return GenerationResult(
            text=response.text or "",
            provider="gemini",
            model=request.model,
            metadata={},
        )
