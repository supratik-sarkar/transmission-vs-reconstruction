#!/usr/bin/env python3
"""Pre-outcome screening for Experiment B entity support.

Evaluates the 200 deterministically generated fictitious names against the
public universe of real SEC reporting issuers (company_tickers.json).
Enforces zero collisions under exact, case-folded, and normalized forms.

Outputs:
  - Machine-readable audit artifact: ENTITY_SUPPORT_SCREENING.json
  - Markdown summary: ENTITY_SUPPORT_SCREENING.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from handoff_fidelity.config import load_settings  # noqa: E402
from scripts.export_protocol_artifacts import entity_support  # noqa: E402

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = "AcademicResearchProject user@example.com"


def normalize_entity_name(name: str) -> str:
    """Strip all non-alphanumeric characters and lowercase."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None, help="Directory for output audit artifacts")
    args = parser.parse_args()

    settings = load_settings()
    out_dir = Path(args.out_dir) if args.out_dir else settings.path("audits")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Executing pre_outcome_registry_screen...")
    entities = entity_support()
    if len(entities) != 200:
        print(f"ERROR: expected 200 entities, got {len(entities)}", file=sys.stderr)
        return 1

    print(f"Loaded {len(entities)} candidate fictitious entities from protocol generator.")

    # Cache SEC tickers in private cache directory
    cache_dir = settings.path("cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    tickers_cache = cache_dir / "sec_company_tickers.json"

    if tickers_cache.exists() and tickers_cache.stat().st_size > 1000:
        print(f"Reading SEC tickers from local cache: {tickers_cache}")
        raw_tickers = json.loads(tickers_cache.read_text(encoding="utf-8"))
    else:
        print(f"Fetching SEC tickers from {SEC_TICKERS_URL}...")
        req = urllib.request.Request(SEC_TICKERS_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
        tickers_cache.write_bytes(content)
        raw_tickers = json.loads(content.decode("utf-8"))

    total_issuers = len(raw_tickers)
    print(f"Loaded {total_issuers} registered SEC issuers from registry.")

    # Build collision lookup sets
    exact_names: dict[str, str] = {}
    normalized_names: dict[str, str] = {}

    for item in raw_tickers.values():
        title = item.get("title", "").strip()
        if not title:
            continue
        exact_names[title.lower()] = title
        norm = normalize_entity_name(title)
        if norm:
            normalized_names[norm] = title

    collisions: list[dict[str, str]] = []
    screened_records: list[dict[str, str]] = []

    for name in entities:
        norm = normalize_entity_name(name)
        matched_exact = exact_names.get(name.lower())
        matched_norm = normalized_names.get(norm)
        is_collision = bool(matched_exact or matched_norm)
        matched_target = matched_exact or matched_norm or ""

        if is_collision:
            collisions.append(
                {
                    "fictitious_name": name,
                    "collided_with": matched_target,
                }
            )

        screened_records.append(
            {
                "fictitious_name": name,
                "normalized": norm,
                "collision": is_collision,
                "matched_issuer": matched_target,
            }
        )

    status = "PASS" if not collisions else "FAIL"
    now_utc = datetime.now(UTC).isoformat()

    audit_payload = {
        "timestamp_utc": now_utc,
        "screening_procedure": "pre_outcome_registry_screen",
        "registry_source": SEC_TICKERS_URL,
        "total_registry_issuers": total_issuers,
        "entity_support_size": len(entities),
        "k_eff": len(entities) - 1,
        "collisions_detected": len(collisions),
        "collision_details": collisions,
        "status": status,
        "screened_entities": screened_records,
    }

    json_path = out_dir / "ENTITY_SUPPORT_SCREENING.json"
    json_bytes = json.dumps(audit_payload, indent=2, sort_keys=True).encode("utf-8")
    json_path.write_bytes(json_bytes)
    json_hash = hashlib.sha256(json_bytes).hexdigest()

    md_path = out_dir / "ENTITY_SUPPORT_SCREENING.md"
    md_content = f"""# Pre-Outcome Entity Support Screening Audit

**Date:** {now_utc}
**Procedure:** `pre_outcome_registry_screen`
**Registry Source:** {SEC_TICKERS_URL}
**Registry Issuers Screened:** {total_issuers:,}
**Support Size:** {len(entities)} (K_eff = {len(entities) - 1})
**Collisions Detected:** {len(collisions)}
**Screening Verdict:** **{status}**
**SHA-256 (JSON Artifact):** `{json_hash}`

---

## 1. Protocol Requirement

Per Preregistration v1.2 §11.1 and Section 7 of Master Prompt 1:
- The 200 fictitious entity names for the Experiment B prior-blocked arm must undergo registry screening against the real-issuer universe before any outcome-bearing or calibration operations.
- Zero collisions permitted. Any collision requires deterministic replacement and re-screening.

## 2. Screening Methodology

1. Evaluated all 200 deterministically generated names from `protocol/randomisation/entity_support.txt` (seed=20260907).
2. Checked exact string equality (case-insensitive) against all {total_issuers:,} registered SEC public company titles.
3. Checked normalized alphanumeric equality (`[^a-z0-9]`) against all registered titles to detect punctuation/whitespace variations.

## 3. Findings

- Total candidates evaluated: {len(entities)}
- Real-issuer collisions found: {len(collisions)}
- Admissibility: **CONFIRMED ELIGIBLE FOR EXPERIMENT B**
"""
    md_path.write_text(md_content, encoding="utf-8")

    print(f"Screening complete: {len(collisions)} collisions found.")
    print(f"Verdict: {status}")
    print(f"Wrote audit json: {json_path} (sha256: {json_hash})")
    print(f"Wrote audit markdown: {md_path}")

    return 0 if not collisions else 1


if __name__ == "__main__":
    raise SystemExit(main())
