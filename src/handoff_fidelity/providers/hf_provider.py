from __future__ import annotations

from .base import GenerationRequest, GenerationResult, Provider


class HuggingFaceLocalProvider(Provider):
    """Simple local causal-LM adapter for MPS/CUDA experiments.

    This is intentionally conservative. Large-model production runs should pin
    revision hashes and decoding settings in the preregistration.
    """

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install with pip install -e '.[hf]'") from exc

        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        tokenizer = AutoTokenizer.from_pretrained(request.model)
        model = AutoModelForCausalLM.from_pretrained(request.model).to(device)
        prompt = f"{request.system}\n\n{request.prompt}".strip()
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        kwargs: dict[str, object] = {
            "max_new_tokens": request.max_tokens,
            "do_sample": bool(request.temperature and request.temperature > 0),
        }
        if kwargs["do_sample"]:
            kwargs["temperature"] = request.temperature
        with torch.no_grad():
            output = model.generate(**inputs, **kwargs)
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        return GenerationResult(
            text=text, provider="hf", model=request.model, metadata={"device": device}
        )
