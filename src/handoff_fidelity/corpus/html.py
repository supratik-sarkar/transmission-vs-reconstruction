"""HTML to text.

Preserved from the earlier source-pool implementation. Filings are frequently
HTML, and the conversion must be deterministic because the resulting text is
what gets hashed into the source frame.
"""

from __future__ import annotations


def html_to_text(raw_html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("beautifulsoup4 is required to convert HTML sources to text") from exc
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def looks_like_html(raw: str) -> bool:
    head = raw[:4096].lower()
    return "<html" in head or "<!doctype html" in head or "<body" in head
