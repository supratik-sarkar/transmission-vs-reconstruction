"""Deterministic mock provider.

Used for dry runs, smoke tests and CI. Its output is a pure function of the
prompt, so pipelines are exercised end to end with no network and no cost.

It is NOT a simulator of a language model and its outputs carry no scientific
meaning: anything produced with the mock is labelled as such and can never
populate a result table.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .base import BaseProvider

MOCK_MARKER = "MOCK-PROVIDER-OUTPUT"

_ANSWER_LINE = re.compile(r"Answer:\s*$")
_NOTE_BLOCK = re.compile(r"--- HANDOFF NOTE ---\n(.*?)\n--- END NOTE ---", re.DOTALL)
_SOURCE_BLOCK = re.compile(r"--- SOURCE ---\n(.*?)\n--- END SOURCE ---", re.DOTALL)


@dataclass(slots=True)
class MockProvider(BaseProvider):
    name: str = "mock"
    model: str = "mock-deterministic-v1"
    echo_first_line: bool = True

    def generate(self, prompt: str, *, max_tokens: int, **kwargs) -> str:
        note = _NOTE_BLOCK.search(prompt)
        if note and _ANSWER_LINE.search(prompt):
            # Receiver-style prompt: echo the first slot value found in the note,
            # which makes transmitted atoms recoverable and omitted atoms not --
            # exactly the behaviour a pipeline test needs.
            for line in note.group(1).splitlines():
                if ":" in line:
                    return line.split(":", 1)[1].strip()
            return ""
        source = _SOURCE_BLOCK.search(prompt)
        if source:
            body = source.group(1).strip()
            return " ".join(body.split()[: max(1, max_tokens // 2)])
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return f"{MOCK_MARKER}:{digest}"
