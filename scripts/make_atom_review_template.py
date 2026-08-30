#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

COLUMNS = [
    "document_id",
    "atom_id",
    "role",
    "value",
    "source_text",
    "source_start",
    "source_end",
    "human_verified",
    "reviewer",
    "notes",
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--document-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=COLUMNS).to_csv(args.output, index=False)
    print(args.output)


if __name__ == "__main__":
    main()
