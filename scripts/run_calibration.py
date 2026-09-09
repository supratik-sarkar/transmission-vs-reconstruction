#!/usr/bin/env python3
"""Run calibration operations on the 50 CALIBRATION documents.

Resolves:
  1. budget.primary_output_tokens (B*) using primary relay tokenizer (o200k_base)
  2. experiment_c.eviction_tolerance_tokens
  3. experiment_c.subset_size

All rules are FROZEN in preregistration v1.2.
Calibration reads deterministic source and render properties only.
No receiver outcomes, estimands, or stage1/dev/test data are accessed.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from handoff_fidelity.atomizer.rules import atomize  # noqa: E402
from handoff_fidelity.calibration.selection import (  # noqa: E402
    EVICTION_GRID,
    EXPC_GRID,
    select_eviction_tolerance,
    select_experiment_c_subset,
    select_primary_budget,
)
from handoff_fidelity.causalrelay.renderer import render_message, rendered_token_cost  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.interventions.budget_neutral import candidate_set  # noqa: E402
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402
from handoff_fidelity.tokenization import get_tokenizer  # noqa: E402

PRIMARY_RELAY_TOKENIZER = "o200k_base"
TARGET_RHO = 2.0
DEV_RECEIVER_CALL_BUDGET = 10_000  # Planned development receiver call budget ceiling


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=None, help="Path to CALIBRATION.csv")
    args = parser.parse_args()

    settings = load_settings()
    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else settings.path("source_manifests", "CALIBRATION.csv")
    )

    if not manifest_path.exists():
        print(f"ERROR: Calibration manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest_hash = sha256_file(manifest_path)
    print(f"Loading calibration manifest: {manifest_path} (sha256: {manifest_hash})")

    rows = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)

    n_docs = len(rows)
    print(f"Loaded {n_docs} calibration documents.")
    if n_docs != 50:
        print(f"ERROR: expected exactly 50 calibration documents, found {n_docs}", file=sys.stderr)
        return 1

    tok = get_tokenizer(PRIMARY_RELAY_TOKENIZER)
    print(f"Using primary relay model tokenizer: {tok.name} ({PRIMARY_RELAY_TOKENIZER})")

    # 1. Measure full-inventory render cost F_i for each calibration document
    full_render_costs: list[int] = []
    atom_counts: list[int] = []
    retentions_by_tol: dict[int, list[float]] = {t: [] for t in EVICTION_GRID}
    candidate_counts_by_tol: dict[int, list[int]] = {t: [] for t in EVICTION_GRID}

    for _idx, row in enumerate(rows):
        frame_file = Path(row["frame_path"])
        if not frame_file.exists():
            # Try locating in data/source_pool/frames
            frame_file = settings.path("data", "source_pool", "frames", f"{row['document_id']}.txt")
        frame_text = frame_file.read_text(encoding="utf-8")

        atoms = atomize(row["document_id"], frame_text)
        atom_counts.append(len(atoms))

        # Full inventory render
        rendered = render_message(atoms)
        f_i = tok.count(rendered)
        full_render_costs.append(f_i)

        # Per-atom costs in primary relay tokenizer
        atom_costs = {a.atom_id: rendered_token_cost(a, tok) for a in atoms}

        for t in EVICTION_GRID:
            kept, _ = candidate_set(atoms, token_costs=atom_costs, tolerance=t)
            ret = len(kept) / len(atoms) if atoms else 0.0
            retentions_by_tol[t].append(ret)
            candidate_counts_by_tol[t].append(len(kept))

    # Solve B*
    budget_sel = select_primary_budget(full_render_costs, target_rho=TARGET_RHO)

    # Solve Eviction Tolerance
    mean_retention_by_tol = {t: float(statistics.mean(retentions_by_tol[t])) for t in EVICTION_GRID}
    eviction_sel = select_eviction_tolerance(mean_retention_by_tol)

    # Solve Experiment C Subset Size
    chosen_tol = eviction_sel.tolerance if eviction_sel.tolerance is not None else 2
    median_cands = round(statistics.median(candidate_counts_by_tol[chosen_tol]))
    matched_retention = mean_retention_by_tol[chosen_tol]

    expc_sel = select_experiment_c_subset(
        median_candidates_per_document=median_cands,
        development_receiver_call_budget=DEV_RECEIVER_CALL_BUDGET,
        matched_pair_retention=matched_retention,
    )

    now_utc = datetime.now(UTC).isoformat()
    l_tokens = int(rows[0].get("window_tokens", 2000))
    b_star_over_l = budget_sel.b_star / l_tokens

    report_payload: dict[str, Any] = {
        "timestamp_utc": now_utc,
        "calibration_manifest": str(manifest_path),
        "calibration_manifest_sha256": manifest_hash,
        "n_calibration_documents": n_docs,
        "tokenizer_used": tok.name,
        "full_render_costs": {
            "median": statistics.median(full_render_costs),
            "mean": statistics.mean(full_render_costs),
            "min": min(full_render_costs),
            "max": max(full_render_costs),
            "stdev": statistics.stdev(full_render_costs),
        },
        "atom_counts": {
            "median": statistics.median(atom_counts),
            "mean": statistics.mean(atom_counts),
            "min": min(atom_counts),
            "max": max(atom_counts),
        },
        "budget_calibration": {
            "b_star": budget_sel.b_star,
            "realized_rho": budget_sel.median_rho,
            "target_rho": TARGET_RHO,
            "b_star_over_l": b_star_over_l,
            "candidate_medians": budget_sel.per_candidate,
            "rule": budget_sel.rule,
        },
        "eviction_tolerance_calibration": {
            "chosen_tolerance": eviction_sel.tolerance,
            "retention_floor": eviction_sel.floor,
            "mean_retention_by_tolerance": mean_retention_by_tol,
            "candidate_grid": list(EVICTION_GRID),
        },
        "experiment_c_subset_calibration": {
            "chosen_subset_size": expc_sel.subset_size,
            "median_candidates_per_document": median_cands,
            "projected_calls_by_subset": expc_sel.projected_calls,
            "call_budget_ceiling": expc_sel.call_budget,
            "rejected_candidates": expc_sel.rejected,
            "candidate_grid": list(EXPC_GRID),
        },
    }

    # Write output reports
    audits_dir = settings.path("audits")
    audits_dir.mkdir(parents=True, exist_ok=True)
    cal_dir = settings.path("calibration")
    cal_dir.mkdir(parents=True, exist_ok=True)

    json_path = audits_dir / "CALIBRATION_SELECTION_REPORT.json"
    json_path.write_text(
        json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (cal_dir / "CALIBRATION_SELECTION_REPORT.json").write_text(
        json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    md_path = audits_dir / "CALIBRATION_SELECTION_REPORT.md"
    md_content = f"""# Calibration Parameter Selection Report

**Date:** {now_utc}
**Calibration Material:** 50 disjoint SEC MD&A documents
**Manifest Hash:** `{manifest_hash}`
**Tokenizer:** `{tok.name}` (primary relay model tokenizer)

---

## 1. Budget Selection ($B^\\star$)

- **Formula:** $B^\\star = \\arg\\min_{{B \\in [200, 250, 300, 350, 400, 500]}} |\\operatorname{{median}}_i(F_i / B) - 2|$
- **Median Full-Inventory Render Cost ($F_i$):** {statistics.median(full_render_costs):.1f} tokens
- **Candidate Medians ($\\rho = F / B$):**
"""
    for b in sorted(budget_sel.per_candidate):
        rho = budget_sel.per_candidate[b]
        marker = " **[SELECTED B*]**" if b == budget_sel.b_star else ""
        md_content += (
            f"  - $B = {b}$: $\\rho = {rho:.3f}$ (|$\\rho - 2| = {abs(rho - 2):.3f}$){marker}\n"
        )

    md_content += f"""
- **Selected $B^\\star$:** `{budget_sel.b_star}` tokens
- **Realized Allocation Pressure ($\\rho$):** `{budget_sel.median_rho:.3f}`
- **Budget Fraction ($B^\\star / L$):** `{b_star_over_l:.3f}` ({b_star_over_l * 100:.1f}%)

---

## 2. Experiment C Parameters

### Eviction Length Tolerance
- **Rule:** Smallest tolerance in $[0, 1, 2, 4, 8]$ tokens retaining $\\ge 80\\%$ of matched pairs.
- **Retention by Tolerance:**
"""
    for t in sorted(mean_retention_by_tol):
        ret = mean_retention_by_tol[t]
        marker = " **[SELECTED]**" if t == eviction_sel.tolerance else ""
        md_content += f"  - Tolerance `{t}` tokens: retention = `{ret * 100:.1f}%`{marker}\n"

    md_content += f"""
- **Selected Eviction Tolerance:** `{eviction_sel.tolerance}` tokens

### Subset Size ($n_C$)
- **Rule:** Largest candidate in $[20, 30, 50]$ with projected receiver calls $\\le 15\\%$ of development budget ({expc_sel.call_budget} calls) and retention $\\ge 80\\%$.
- **Median Eligible Candidates per Document:** {median_cands}
- **Projected Calls:**
"""
    for n in sorted(expc_sel.projected_calls):
        calls = expc_sel.projected_calls[n]
        status = (
            "fits budget" if n == expc_sel.subset_size else expc_sel.rejected.get(n, "evaluated")
        )
        marker = " **[SELECTED]**" if n == expc_sel.subset_size else ""
        md_content += f"  - $n = {n}$: {calls} calls ({status}){marker}\n"

    md_content += f"""
- **Selected Subset Size:** `{expc_sel.subset_size}` documents
"""
    md_path.write_text(md_content, encoding="utf-8")

    print("\nCalibration Parameter Selection Complete:")
    print(f"  B*: {budget_sel.b_star} tokens (realized rho = {budget_sel.median_rho:.3f})")
    print(f"  Eviction Tolerance: {eviction_sel.tolerance} tokens")
    print(f"  Exp-C Subset Size: {expc_sel.subset_size} documents")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
