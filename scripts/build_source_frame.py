#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from handoff_fidelity.source_pool import SourceDocument, build_source_frame


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-tokens", type=int, default=2000)
    args = p.parse_args()
    df = pd.read_csv(args.snapshot, dtype=str)
    rows = [
        SourceDocument(
            document_id=r["document_id"],
            cik=r["cik"],
            issuer=r["issuer"],
            accession_number=r["accession_number"],
            filing_date=r["filing_date"],
            period_end=r["period_end"],
            raw_path=Path(r["raw_path"]),
        )
        for r in df.to_dict(orient="records")
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_source_frame(rows, args.output, source_tokens=args.source_tokens)
    print(args.output)


if __name__ == "__main__":
    main()
