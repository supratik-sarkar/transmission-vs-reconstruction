"""Frozen tokenization.

The pre-registered tokenizer is ``cl100k_base`` via ``tiktoken``. A
deterministic stdlib fallback is provided so that budget logic, truncation and
the source-frame construction remain testable in environments without
``tiktoken``; the fallback is TEST-ONLY and must never be used for a real run.
Any component that silently accepted the fallback records a warning.
"""

from __future__ import annotations

import re
from typing import Protocol

FROZEN_TOKENIZER = "cl100k_base"
FALLBACK_TOKENIZER = "regex-word-punct-TESTONLY"

_FALLBACK_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class Tokenizer(Protocol):
    name: str

    def encode(self, text: str) -> list[int]: ...

    def count(self, text: str) -> int: ...

    def truncate(self, text: str, max_tokens: int) -> tuple[str, bool]: ...


class TiktokenTokenizer:
    def __init__(self, name: str = FROZEN_TOKENIZER) -> None:
        import tiktoken  # noqa: PLC0415 - optional dependency

        self.name = name
        self._enc = tiktoken.get_encoding(name)

    def encode(self, text: str) -> list[int]:
        return list(self._enc.encode(text))

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def truncate(self, text: str, max_tokens: int) -> tuple[str, bool]:
        ids = self._enc.encode(text)
        if len(ids) <= max_tokens:
            return text, False
        return self._enc.decode(ids[:max_tokens]), True


class FallbackTokenizer:
    """Deterministic word/punctuation tokenizer.

    Truncation reconstructs text by slicing at the character offset of the
    token boundary, so it is stable and reversible enough for tests.
    """

    name = FALLBACK_TOKENIZER

    def _spans(self, text: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in _FALLBACK_RE.finditer(text)]

    def encode(self, text: str) -> list[int]:
        return [hash(text[a:b]) & 0xFFFFFFFF for a, b in self._spans(text)]

    def count(self, text: str) -> int:
        return len(self._spans(text))

    def truncate(self, text: str, max_tokens: int) -> tuple[str, bool]:
        spans = self._spans(text)
        if len(spans) <= max_tokens:
            return text, False
        if max_tokens <= 0:
            return "", True
        return text[: spans[max_tokens - 1][1]], True


def get_tokenizer(name: str = FROZEN_TOKENIZER, *, allow_fallback: bool = False) -> Tokenizer:
    try:
        return TiktokenTokenizer(name)
    except Exception:
        if not allow_fallback:
            raise RuntimeError(
                "tiktoken is unavailable and allow_fallback=False. A real run must "
                f"use the frozen tokenizer {name!r}; the fallback is test-only."
            ) from None
        return FallbackTokenizer()
