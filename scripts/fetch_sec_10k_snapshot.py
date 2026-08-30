#!/usr/bin/env python3
"""Fetch one 10-K per requested CIK into the PRIVATE workspace.

This script is intentionally not run during repository generation. SEC access
requires a real researcher user-agent and network access. Review SEC fair-access
requirements before use.
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from pathlib import Path

import httpx

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_compact}/{primary_doc}"


def normalize_cik(value: str) -> str:
    return value.strip().zfill(10)


def choose_10k(payload: dict, cutoff: str) -> dict[str, str] | None:
    recent = payload.get("filings", {}).get("recent", {})
    keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
    if not all(k in recent for k in keys):
        return None
    rows = [
        dict(zip(keys, vals, strict=True)) for vals in zip(*(recent[k] for k in keys), strict=True)
    ]
    candidates = [r for r in rows if r["form"] == "10-K" and r["reportDate"] <= cutoff]
    return max(candidates, key=lambda r: r["filingDate"]) if candidates else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ciks", type=Path, required=True, help="One CIK per line")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--cutoff", default="2023-12-31")
    p.add_argument("--sleep", type=float, default=0.12)
    args = p.parse_args()

    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent or "example.com" in user_agent:
        raise SystemExit(
            "Set a real SEC_USER_AGENT in the PRIVATE .env/environment before retrieval."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw_filings"
    raw_dir.mkdir(exist_ok=True)
    rows: list[dict[str, str]] = []
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}

    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        for line in args.ciks.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cik = normalize_cik(line)
            payload = client.get(SUBMISSIONS.format(cik=cik)).json()
            selected = choose_10k(payload, args.cutoff)
            if selected is None:
                continue
            accession_compact = selected["accessionNumber"].replace("-", "")
            url = ARCHIVES.format(
                cik_int=int(cik),
                accession_compact=accession_compact,
                primary_doc=selected["primaryDocument"],
            )
            response = client.get(url)
            response.raise_for_status()
            doc_id = selected["accessionNumber"]
            raw_path = raw_dir / f"{doc_id}.html"
            raw_path.write_bytes(response.content)
            rows.append(
                {
                    "document_id": doc_id,
                    "cik": cik,
                    "issuer": str(payload.get("name", "")),
                    "accession_number": selected["accessionNumber"],
                    "filing_date": selected["filingDate"],
                    "period_end": selected["reportDate"],
                    "raw_path": str(raw_path),
                    "source_url": url,
                }
            )
            time.sleep(args.sleep)

    manifest = args.output_dir / "RAW_SNAPSHOT.csv"
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys() if rows else ["document_id", "cik"])
        writer.writeheader()
        writer.writerows(rows)
    print(manifest)


if __name__ == "__main__":
    main()
