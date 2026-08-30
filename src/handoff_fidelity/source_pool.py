from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from .integrity import sha256_file
from .tokenization import truncate_tokens


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    cik: str
    issuer: str
    accession_number: str
    filing_date: str
    period_end: str
    raw_path: Path


def html_to_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def extract_item7(text: str) -> str:
    """Heuristic Item 7 extraction from normalized 10-K text.

    This must be human-audited before experimental use. The function intentionally
    fails closed when boundaries are ambiguous.
    """
    start = list(re.finditer(r"(?im)^\s*item\s+7\.?\s+management['’]?s discussion", text))
    end = list(re.finditer(r"(?im)^\s*item\s+7a\.?\s+", text))
    if not start or not end:
        raise ValueError("Could not locate Item 7 / 7A boundaries")
    s = start[-1].start()
    ends = [m.start() for m in end if m.start() > s]
    if not ends:
        raise ValueError("Could not locate Item 7A after Item 7")
    return text[s : min(ends)]


def build_source_frame(
    rows: list[SourceDocument], output: Path, *, source_tokens: int = 2000
) -> None:
    data: list[dict[str, str | int]] = []
    seen_cik: set[str] = set()
    for row in sorted(rows, key=lambda r: (r.cik, r.filing_date), reverse=True):
        if row.cik in seen_cik:
            continue
        seen_cik.add(row.cik)
        raw = row.raw_path.read_text(encoding="utf-8", errors="replace")
        normalized = html_to_text(raw) if "<html" in raw.lower() else raw
        item7 = extract_item7(normalized)
        relay_source = truncate_tokens(item7, source_tokens)
        source_path = output.parent / "relay_sources" / f"{row.document_id}.txt"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(relay_source, encoding="utf-8")
        data.append(
            {
                "document_id": row.document_id,
                "cik": row.cik,
                "issuer": row.issuer,
                "accession_number": row.accession_number,
                "filing_date": row.filing_date,
                "period_end": row.period_end,
                "relay_source_path": str(source_path),
                "relay_source_sha256": sha256_file(source_path),
                "relay_source_tokens": source_tokens,
            }
        )
    pd.DataFrame(data).to_csv(output, index=False)
