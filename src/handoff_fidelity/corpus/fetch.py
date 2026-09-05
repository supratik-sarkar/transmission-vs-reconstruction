"""Source retrieval interface.

Retrieval is an explicit integration point and is DISABLED by default. The
repository ships no cached filings and performs no network access during
construction, testing or CI. A real acquisition run must:

  1. set ``allow_network=True`` explicitly,
  2. supply a descriptive user agent as required by the data provider,
  3. write only into the private workspace.

``LocalFixtureSource`` is what the tests use, and what any dry run should use.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RawDocument:
    document_id: str
    issuer_id: str
    fiscal_year: int
    text: str
    retrieved_utc: str = ""
    source_url: str = ""
    licence: str = "public-domain-us-government"


class SourceBackend(Protocol):
    name: str

    def iter_documents(self) -> Iterator[RawDocument]: ...


class LocalFixtureSource:
    """Reads documents from a directory of JSON files. No network."""

    name = "local-fixture"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def iter_documents(self) -> Iterator[RawDocument]:
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            yield RawDocument(
                document_id=payload["document_id"],
                issuer_id=payload["issuer_id"],
                fiscal_year=int(payload["fiscal_year"]),
                text=payload["text"],
                retrieved_utc=payload.get("retrieved_utc", ""),
                source_url=payload.get("source_url", ""),
                licence=payload.get("licence", "public-domain-us-government"),
            )


class NetworkDisabledError(RuntimeError):
    pass


class EdgarSource:
    """EDGAR retrieval integration point.

    Intentionally NOT implemented against the live service in this repository.
    The method body documents exactly what a compliant implementation must do;
    calling it without ``allow_network`` raises.
    """

    name = "edgar"

    def __init__(
        self,
        *,
        accessions: Iterable[str],
        user_agent: str,
        allow_network: bool = False,
        cache_dir: Path | None = None,
    ) -> None:
        self.accessions = tuple(accessions)
        self.user_agent = user_agent
        self.allow_network = allow_network
        self.cache_dir = cache_dir

    def iter_documents(self) -> Iterator[RawDocument]:
        if not self.allow_network:
            raise NetworkDisabledError(
                "EDGAR retrieval is disabled. Set allow_network=True and supply a "
                "descriptive user agent to enable it, and write only into the "
                "private workspace. No retrieval occurs during repository "
                "construction, testing or CI."
            )
        raise NotImplementedError(
            "Live retrieval is an explicit integration point. A compliant "
            "implementation must: honour the provider's rate limit and user-agent "
            "policy; cache raw bytes under the private workspace; record "
            "accession, retrieval timestamp, URL and licence per document; and "
            "never write raw filings into the public repository."
        )
