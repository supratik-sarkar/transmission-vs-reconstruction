"""Secret redaction.

Applied to every log line, error payload, telemetry attribute and API response.
It is defence in depth: the primary control is that secrets are never placed in
those objects at all. Both are needed, because "never placed" is a property of
every future code path, and this one is a property of a single function.
"""

from __future__ import annotations

import os
import re
from typing import Any

REDACTED = "[REDACTED]"

#: Environment variables whose VALUES must never appear anywhere.
SECRET_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "HF_TOKEN",
    "LANGSMITH_API_KEY",
)

#: Shape-based patterns, for credentials that never passed through our config.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\b(authorization|x-api-key)\b\s*[:=]\s*\S+"),
)

#: Keys whose value is redacted regardless of shape.
_SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|credential)")


def _live_secret_values() -> list[str]:
    out: list[str] = []
    for key in SECRET_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        # Short values are not credentials and matching them would redact
        # ordinary text.
        if len(value) >= 8:
            out.append(value)
    return out


def redact_text(text: str) -> str:
    """Redact live secret values first, then credential shapes."""
    if not text:
        return text
    for value in _live_secret_values():
        text = text.replace(value, REDACTED)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(obj: Any, *, _depth: int = 0) -> Any:
    """Recursively redact a JSON-like structure.

    Depth-limited so a cyclic or pathological structure cannot hang the logger
    on the error path -- the moment redaction matters most.
    """
    if _depth > 12:
        return REDACTED
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                out[key] = REDACTED
            else:
                out[key] = redact(value, _depth=_depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        seq = [redact(v, _depth=_depth + 1) for v in obj]
        return type(obj)(seq) if isinstance(obj, tuple) else seq
    return obj


def assert_no_secret(payload: Any, *, context: str = "") -> None:
    """Fail loudly if a secret survived into ``payload``. Used in tests and on
    egress boundaries."""
    import json as _json

    try:
        text = payload if isinstance(payload, str) else _json.dumps(payload, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    for value in _live_secret_values():
        if value in text:
            raise AssertionError(f"secret value leaked{' in ' + context if context else ''}")
    for pattern in _PATTERNS:
        if pattern.search(text):
            raise AssertionError(
                f"credential-shaped content leaked{' in ' + context if context else ''}: "
                f"{pattern.pattern}"
            )
