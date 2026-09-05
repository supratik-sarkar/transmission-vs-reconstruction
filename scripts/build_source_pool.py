#!/usr/bin/env python3
"""Build the source pool and its manifest.

NO NETWORK ACCESS OCCURS unless --allow-network is passed explicitly, and even
then the retrieval backend is an unimplemented integration point. The default
backend reads local fixtures.

Output goes to the PRIVATE workspace only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.corpus.fetch import LocalFixtureSource  # noqa: E402
from handoff_fidelity.corpus.frame import build_source_frame  # noqa: E402
from handoff_fidelity.corpus.html import html_to_text, looks_like_html  # noqa: E402
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402
from handoff_fidelity.tokenization import get_tokenizer  # noqa: E402

COLUMNS = (
    "document_id",
    "issuer_id",
    "fiscal_year",
    "section",
    "tokenizer",
    "window_tokens",
    "frame_tokens",
    "truncated",
    "frame_sha256",
    "frame_path",
    "licence",
    "retrieved_utc",
    "source_url",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", default=None, help="directory of local JSON documents")
    ap.add_argument("--out", default=None, help="output CSV (defaults to the private workspace)")
    ap.add_argument("--window-tokens", type=int, default=None)
    ap.add_argument("--section", default="mdna", choices=["mdna", "full"])
    ap.add_argument("--allow-network", action="store_true")
    ap.add_argument(
        "--allow-tokenizer-fallback",
        action="store_true",
        help="TEST ONLY. A real run must use the frozen tokenizer.",
    )
    args = ap.parse_args()

    settings = load_settings()
    window = args.window_tokens or settings.source_window_tokens
    out = Path(args.out) if args.out else settings.path("data", "source_pool", "SOURCE_POOL.csv")
    frames_dir = out.parent / "frames"

    if args.allow_network:
        print(
            "Live retrieval is an explicit integration point and is not implemented here.\n"
            "Implement it against the provider's terms, cache raw bytes in the private\n"
            "workspace, and record accession, timestamp, URL and licence per document.",
            file=sys.stderr,
        )
        return 2

    tokenizer = get_tokenizer(
        settings.tokenizer_name,
        allow_fallback=args.allow_tokenizer_fallback or settings.allow_tokenizer_fallback,
    )
    if tokenizer.name != settings.tokenizer_name:
        print(
            f"WARNING: using the fallback tokenizer {tokenizer.name!r}. TEST ONLY.", file=sys.stderr
        )

    rows: list[dict[str, object]] = []
    if args.fixtures:
        frames_dir.mkdir(parents=True, exist_ok=True)
        for doc in LocalFixtureSource(Path(args.fixtures)).iter_documents():
            raw = html_to_text(doc.text) if looks_like_html(doc.text) else doc.text
            frame = build_source_frame(
                document_id=doc.document_id,
                raw_text=raw,
                window_tokens=window,
                tokenizer=tokenizer,
                section=args.section,
                require_section=False,
            )
            frame_path = frames_dir / f"{doc.document_id}.txt"
            frame_path.write_text(frame.text, encoding="utf-8")
            rows.append(
                {
                    "document_id": frame.document_id,
                    "issuer_id": doc.issuer_id,
                    "fiscal_year": doc.fiscal_year,
                    "section": frame.section,
                    "tokenizer": frame.tokenizer,
                    "window_tokens": frame.window_tokens,
                    "frame_tokens": frame.token_count,
                    "truncated": frame.truncated,
                    "frame_sha256": frame.sha256,
                    "frame_path": str(frame_path),
                    "licence": doc.licence,
                    "retrieved_utc": doc.retrieved_utc,
                    "source_url": doc.source_url,
                }
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} document(s) to {out}")
    print(f"sha256({out.name}) = {sha256_file(out)}")
    if not rows:
        print(
            "The pool is header-only: no corpus has been acquired. That is the "
            "current true state, and it is recorded rather than simulated."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
