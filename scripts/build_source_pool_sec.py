#!/usr/bin/env python3
"""Acquire 450 SEC Form 10-K MD&A frames and construct disjoint study manifests.

Connects to the official SEC EDGAR public archive to acquire 450 real Form 10-K
MD&A 2,000-token source frames across 450 distinct reporting issuers.

Enforces:
  - Domain: Item 7 (MD&A), >= 500 characters
  - Window: 2,000 tokens (cl100k_base hard truncation)
  - Atom inventory: >= 3 populated Tier-1 strata (k=3 focal sampling positivity)
  - Issuer disjointness: exactly 450 distinct CIK issuers across all splits
  - Splits:
      * CALIBRATION: 50 documents
      * STAGE1: 100 documents
      * STAGE2_DEV: 100 documents
      * STAGE2_TEST: 200 documents
  - Mechanical sealing of STAGE2_TEST (content-addressed manifest, zero content exposure)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from handoff_fidelity.atomizer.rules import atomize  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.corpus.frame import build_source_frame  # noqa: E402
from handoff_fidelity.corpus.html import html_to_text  # noqa: E402
from handoff_fidelity.corpus.sections import SectionNotFound, extract_mdna  # noqa: E402
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = "AcademicResearchProject user@example.com"
WINDOW_TOKENS = 2000
TOKENIZER_NAME = "cl100k_base"
MASTER_SEED = 20260907

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


def fetch_filing_worker(
    cik: int,
    _ticker: str,
    _title: str,
    cache_dir: Path,
    filings_cache_dir: Path,
) -> dict[str, Any] | None:
    """Worker to retrieve and process one 10-K filing for a given CIK."""
    headers = {"User-Agent": USER_AGENT}
    sub_cache = cache_dir / f"CIK{str(cik).zfill(10)}.json"

    try:
        if sub_cache.exists() and sub_cache.stat().st_size > 500:
            sub = json.loads(sub_cache.read_text(encoding="utf-8"))
        else:
            url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
            sub_cache.write_bytes(content)
            sub = json.loads(content.decode("utf-8"))

        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])

        # Find the latest Form 10-K
        target_idx = None
        for idx, f in enumerate(forms):
            if f == "10-K":
                target_idx = idx
                break

        if target_idx is None:
            return None

        acc = accessions[target_idx]
        doc_name = primary_docs[target_idx]
        fdate = filing_dates[target_idx] if target_idx < len(filing_dates) else ""
        fiscal_year = int(fdate[:4]) if (fdate and fdate[:4].isdigit()) else 2024

        acc_no_dash = acc.replace("-", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dash}/{doc_name}"

        # Fetch and cache raw HTML
        doc_cache = filings_cache_dir / f"{acc}_{doc_name}"
        if doc_cache.exists() and doc_cache.stat().st_size > 1000:
            raw_html = doc_cache.read_text(encoding="utf-8", errors="replace")
        else:
            req_doc = urllib.request.Request(doc_url, headers=headers)
            with urllib.request.urlopen(req_doc, timeout=25) as resp:
                raw_bytes = resp.read()
            doc_cache.write_bytes(raw_bytes)
            raw_html = raw_bytes.decode("utf-8", errors="replace")

        text = html_to_text(raw_html)
        start, end = extract_mdna(text)
        mdna_text = text[start:end]
        if len(mdna_text) < 500:
            return None

        doc_id = f"SEC-{acc}"
        frame = build_source_frame(
            document_id=doc_id,
            raw_text=text,
            window_tokens=WINDOW_TOKENS,
            tokenizer_name=TOKENIZER_NAME,
            section="mdna",
            require_section=True,
        )

        atoms = atomize(frame.document_id, frame.text)
        roles = {a.role.value for a in atoms}
        if len(roles) < 3:
            return None

        return {
            "document_id": doc_id,
            "issuer_id": f"CIK-{str(cik).zfill(10)}",
            "fiscal_year": fiscal_year,
            "section": "mdna",
            "tokenizer": TOKENIZER_NAME,
            "window_tokens": WINDOW_TOKENS,
            "frame_tokens": frame.token_count,
            "truncated": frame.truncated,
            "frame_sha256": frame.sha256,
            "frame_text": frame.text,
            "licence": "public-domain-us-government",
            "retrieved_utc": datetime.now(UTC).isoformat(),
            "source_url": doc_url,
            "atom_count": len(atoms),
            "populated_roles_count": len(roles),
        }

    except (SectionNotFound, urllib.error.URLError, TimeoutError, OSError):
        return None
    except Exception:
        return None


def write_manifest(manifest_path: Path, rows: Sequence[dict[str, Any]]) -> str:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            clean_row = {k: r[k] for k in COLUMNS}
            writer.writerow(clean_row)
    return sha256_file(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=450)
    parser.add_argument("--max-workers", type=int, default=6)
    args = parser.parse_args()

    settings = load_settings()
    cache_dir = settings.path("cache", "sec_submissions")
    cache_dir.mkdir(parents=True, exist_ok=True)
    filings_cache_dir = settings.path("data", "raw", "filings")
    filings_cache_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = settings.path("data", "source_pool", "frames")
    frames_dir.mkdir(parents=True, exist_ok=True)

    print(f"Target count: {args.target_count} unique issuer documents.")
    tickers_path = settings.path("cache", "sec_company_tickers.json")

    if tickers_path.exists() and tickers_path.stat().st_size > 1000:
        tickers = json.loads(tickers_path.read_text(encoding="utf-8"))
    else:
        req = urllib.request.Request(SEC_TICKERS_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
        tickers_path.write_bytes(content)
        tickers = json.loads(content.decode("utf-8"))

    total_candidates = len(tickers)
    print(f"Available SEC reporting issuers: {total_candidates}")

    # Build queue of candidates
    candidates = []
    for i in range(total_candidates):
        item = tickers[str(i)]
        candidates.append((item["cik_str"], item.get("ticker", ""), item.get("title", "")))

    acquired_documents: list[dict[str, Any]] = []
    seen_issuers: set[str] = set()

    print("Beginning concurrent acquisition and processing...")
    t0 = time.time()
    batch_size = 30
    cand_idx = 0

    while len(acquired_documents) < args.target_count and cand_idx < len(candidates):
        batch = candidates[cand_idx : cand_idx + batch_size]
        cand_idx += batch_size

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    fetch_filing_worker,
                    cik,
                    ticker,
                    title,
                    cache_dir,
                    filings_cache_dir,
                ): (cik, ticker)
                for cik, ticker, title in batch
            }

            for fut in as_completed(futures):
                res = fut.result()
                if res is not None:
                    issuer = res["issuer_id"]
                    if issuer not in seen_issuers and len(acquired_documents) < args.target_count:
                        seen_issuers.add(issuer)
                        frame_path = frames_dir / f"{res['document_id']}.txt"
                        frame_path.write_text(res["frame_text"], encoding="utf-8")
                        res["frame_path"] = str(frame_path)
                        acquired_documents.append(res)
                        if (
                            len(acquired_documents) % 25 == 0
                            or len(acquired_documents) == args.target_count
                        ):
                            elapsed = time.time() - t0
                            print(
                                f"  Progress: {len(acquired_documents)}/{args.target_count} "
                                f"documents acquired ({elapsed:.1f}s, scanned {cand_idx} issuers)"
                            )
                        if len(acquired_documents) >= args.target_count:
                            break

        time.sleep(0.2)  # courteous rate-limiting between batches

    if len(acquired_documents) < args.target_count:
        print(
            f"ERROR: Only acquired {len(acquired_documents)} documents (target {args.target_count})",
            file=sys.stderr,
        )
        return 1

    print(f"Acquisition completed in {time.time() - t0:.1f}s.")

    # Deterministic sorting before partition
    acquired_documents.sort(key=lambda d: d["document_id"])

    # Shuffle with preregistered master seed for unbiased issuer allocation
    rng = random.Random(MASTER_SEED)
    shuffled = list(acquired_documents)
    rng.shuffle(shuffled)

    # 450-document partition per Amendment P-8
    # CALIBRATION: 50, STAGE1: 100, STAGE2_DEV: 100, STAGE2_TEST: 200
    cal_docs = shuffled[0:50]
    stage1_docs = shuffled[50:150]
    stage2_dev_docs = shuffled[150:250]
    stage2_test_docs = shuffled[250:450]

    # Verify disjointness assertions
    all_sets = [
        {d["issuer_id"] for d in cal_docs},
        {d["issuer_id"] for d in stage1_docs},
        {d["issuer_id"] for d in stage2_dev_docs},
        {d["issuer_id"] for d in stage2_test_docs},
    ]
    assert len(cal_docs) == 50
    assert len(stage1_docs) == 100
    assert len(stage2_dev_docs) == 100
    assert len(stage2_test_docs) == 200
    assert len(seen_issuers) == 450

    for i in range(len(all_sets)):
        for j in range(i + 1, len(all_sets)):
            overlap = all_sets[i].intersection(all_sets[j])
            assert not overlap, f"Issuer overlap detected between sets {i} and {j}: {overlap}"

    print("Disjointness verified: 450 unique issuers across all 4 splits.")

    # Write manifests
    # 1. Full source pool
    sp_hash_1 = write_manifest(settings.path("data", "source_pool", "SOURCE_POOL.csv"), shuffled)
    write_manifest(settings.path("source_manifests", "SOURCE_POOL.csv"), shuffled)

    # 2. CALIBRATION (50)
    cal_hash = write_manifest(settings.path("source_manifests", "CALIBRATION.csv"), cal_docs)
    write_manifest(settings.path("data", "calibration", "CALIBRATION.csv"), cal_docs)

    # 3. STAGE1 (100)
    s1_hash = write_manifest(settings.path("source_manifests", "STAGE1.csv"), stage1_docs)
    write_manifest(settings.path("data", "stage1", "STAGE1.csv"), stage1_docs)

    # 4. STAGE2_DEV (100)
    s2dev_hash = write_manifest(
        settings.path("source_manifests", "STAGE2_DEV.csv"), stage2_dev_docs
    )
    write_manifest(settings.path("data", "stage2_dev", "STAGE2_DEV.csv"), stage2_dev_docs)

    # 5. STAGE2_TEST (200) - SEALED
    test_manifest_path = settings.path("source_manifests", "STAGE2_TEST.csv")
    s2test_hash = write_manifest(test_manifest_path, stage2_test_docs)
    write_manifest(settings.path("data", "stage2_test", "STAGE2_TEST.csv"), stage2_test_docs)

    print(f"Manifest SHA-256 (SOURCE_POOL.csv):   {sp_hash_1}")
    print(f"Manifest SHA-256 (CALIBRATION.csv):   {cal_hash}")
    print(f"Manifest SHA-256 (STAGE1.csv):        {s1_hash}")
    print(f"Manifest SHA-256 (STAGE2_DEV.csv):    {s2dev_hash}")
    print(f"Manifest SHA-256 (STAGE2_TEST.csv):   {s2test_hash} [SEALED]")

    # Record mechanical test seal event
    seal_time = datetime.now(UTC).isoformat()
    seal_audit = {
        "event": "STAGE2_TEST_MECHANICAL_SEAL",
        "timestamp_utc": seal_time,
        "master_seed": MASTER_SEED,
        "stage2_test_documents": len(stage2_test_docs),
        "manifest_path": str(test_manifest_path),
        "manifest_sha256": s2test_hash,
        "source_pool_sha256": sp_hash_1,
        "calibration_sha256": cal_hash,
        "stage1_sha256": s1_hash,
        "stage2_dev_sha256": s2dev_hash,
        "sealing_rules_enforced": [
            "content_addressed_manifest",
            "immutable_sha256_hash",
            "zero_human_readable_preview",
            "no_ui_browsing",
            "no_receiver_or_model_calls",
            "no_derived_outcome_computation",
            "no_test_driven_debugging",
        ],
        "document_ids": [d["document_id"] for d in stage2_test_docs],
        "document_hashes": [d["frame_sha256"] for d in stage2_test_docs],
    }

    audits_dir = settings.path("audits")
    audits_dir.mkdir(parents=True, exist_ok=True)
    test_freeze_dir = settings.path("test_freeze")
    test_freeze_dir.mkdir(parents=True, exist_ok=True)

    seal_json = audits_dir / "STAGE2_TEST_SEAL.json"
    seal_json.write_text(json.dumps(seal_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (test_freeze_dir / "STAGE2_TEST_SEAL.json").write_text(
        json.dumps(seal_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    seal_md = audits_dir / "STAGE2_TEST_SEAL.md"
    seal_md.write_text(
        f"""# Stage 2 Confirmatory Test Set Mechanical Seal

**Date:** {seal_time}
**Status:** MECHANICALLY SEALED — ZERO CONTENT EXPOSURE
**Seed:** {MASTER_SEED}
**Document Count:** {len(stage2_test_docs)} unique issuers
**Manifest:** `source_manifests/STAGE2_TEST.csv`
**Manifest SHA-256:** `{s2test_hash}`

---

## 1. Mechanical Seal Invariants

Per Master Prompt 1 Section 6 and Preregistration v1.2:
- **No human preview:** Document texts have not been displayed, browsed, or logged.
- **No model invocation:** Zero provider inference calls or comparator executions were run against test documents.
- **Zero outcome leakage:** No accuracy, loss, fidelity, or causal estimands have been evaluated.
- **Content-addressed immutability:** Document frame SHA-256 hashes and the manifest SHA-256 hash are recorded.

## 2. Partition Summary

| Split | Documents | Issuers | Manifest Hash (SHA-256) |
|---|---|---|---|
| `CALIBRATION` | 50 | 50 | `{cal_hash}` |
| `STAGE1` | 100 | 100 | `{s1_hash}` |
| `STAGE2_DEV` | 100 | 100 | `{s2dev_hash}` |
| `STAGE2_TEST` | 200 | 200 | `{s2test_hash}` |
| **TOTAL** | **450** | **450** | `{sp_hash_1}` |
""",
        encoding="utf-8",
    )

    print(f"Wrote mechanical seal audit: {seal_json}")
    print(f"Wrote mechanical seal documentation: {seal_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
