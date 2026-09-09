#!/usr/bin/env python3
"""Gate G4 — Finalist Receiver 100x10 Operational Reproducibility Audit.

Executes 100 representative receiver requests across 5 frozen atom strata
(entity, scope, period, numeric, provenance; 20 per stratum) drawn from
dedicated CALIBRATION material only.

Repeats each input 10 times under byte-identical request content and fixed
pinned configuration: openai/gpt-5.6-terra.

Enforces:
  - Strict (D) rule: D_CONFIRMED iff all 100 inputs have unanimous canonical
    receiver outcomes across all 10 repeats.
  - Any canonical disagreement => S_CONFIRMED.
  - Byte-identical repeat rate reported as an operational diagnostic only.
  - If S_CONFIRMED: calibrates m* on the [1, 2, 3, 5] grid at ratio <= 0.10.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from handoff_fidelity.atomizer.rules import atomize  # noqa: E402
from handoff_fidelity.causalrelay.renderer import render_message  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.matcher.canonical import canonicalize  # noqa: E402
from handoff_fidelity.models import AtomRole  # noqa: E402
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402
from handoff_fidelity.providers.adapters import OpenAIAdapter  # noqa: E402
from handoff_fidelity.providers.protocol import GenerationRequest  # noqa: E402
from handoff_fidelity.receiver.prompt import build_receiver_prompt  # noqa: E402

PINNED_MODEL = "gpt-5.6-terra"
REPEATS = 10
INPUTS_PER_STRATUM = 20
STRATA = [
    AtomRole.ENTITY,
    AtomRole.SCOPE,
    AtomRole.PERIOD,
    AtomRole.NUMERIC,
    AtomRole.PROVENANCE,
]
TOTAL_INPUTS = len(STRATA) * INPUTS_PER_STRATUM  # 100
MAX_SPEND_LIMIT_USD = 15.0


def load_env_safe() -> None:
    raw_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    env_path = Path(raw_home) / ".env" if raw_home else Path.cwd() / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v


def calculate_cost(in_tok: int, out_tok: int) -> float:
    # gpt-5.6-terra pricing: $2/MTok input, $12/MTok output
    in_cost = (max(0, in_tok) / 1_000_000.0) * 2.0
    out_cost = (max(0, out_tok) / 1_000_000.0) * 12.0
    return in_cost + out_cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-workers", type=int, default=10)
    args = parser.parse_args()

    load_env_safe()
    settings = load_settings()
    manifest_path = settings.path("source_manifests", "CALIBRATION.csv")

    if not manifest_path.exists():
        print(f"ERROR: Calibration manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest_hash = sha256_file(manifest_path)
    print(f"Loading calibration documents from {manifest_path} (sha256: {manifest_hash})...")

    cal_docs = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            cal_docs.append(r)

    print(f"Loaded {len(cal_docs)} calibration documents.")

    # Collect atoms by role across calibration documents
    atoms_by_role: dict[AtomRole, list[tuple[dict[str, Any], Any, str]]] = defaultdict(list)

    for doc in cal_docs:
        frame_file = Path(doc["frame_path"])
        if not frame_file.exists():
            frame_file = settings.path("data", "source_pool", "frames", f"{doc['document_id']}.txt")
        frame_text = frame_file.read_text(encoding="utf-8")
        doc_atoms = atomize(doc["document_id"], frame_text)
        note_message = render_message(doc_atoms)

        for a in doc_atoms:
            atoms_by_role[a.role].append((doc, a, note_message))

    # Sample 20 representative inputs per stratum
    rng = random.Random(20260907)
    sampled_inputs: list[dict[str, Any]] = []

    for role in STRATA:
        candidates = atoms_by_role[role]
        if len(candidates) < INPUTS_PER_STRATUM:
            print(
                f"ERROR: not enough atoms for role {role.value}: {len(candidates)}", file=sys.stderr
            )
            return 1
        selected = rng.sample(candidates, INPUTS_PER_STRATUM)
        for doc, a, msg in selected:
            prompt = build_receiver_prompt(
                message=msg,
                role=role,
                subject=f"the issuer ({doc['issuer_id']})",
                attribute=f"the {role.value} statement",
            )
            sampled_inputs.append(
                {
                    "input_id": f"{doc['document_id']}:{a.atom_id}",
                    "document_id": doc["document_id"],
                    "issuer_id": doc["issuer_id"],
                    "role": role.value,
                    "target_canonical": a.canonical_value,
                    "prompt": prompt,
                }
            )

    assert len(sampled_inputs) == TOTAL_INPUTS
    print(f"Constructed {len(sampled_inputs)} representative receiver inputs spanning 5 strata.")

    adapter = OpenAIAdapter(model=PINNED_MODEL, allow_network=True)
    print(f"Executing G4 Audit on {PINNED_MODEL}: 100 inputs x 10 repeats = 1,000 calls...")

    t0 = time.time()
    total_spend = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    # Execute calls
    # Key: input_id -> list of repeat results
    results_by_input: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # Flatten the work items: (input_info, repeat_idx)
    work_items = [(inp, rep) for inp in sampled_inputs for rep in range(REPEATS)]
    random.Random(1337).shuffle(work_items)

    def execute_call(item: tuple[dict[str, Any], int]) -> dict[str, Any]:
        inp, rep = item
        req = GenerationRequest(
            prompt=inp["prompt"],
            max_output_tokens=512,
            model=PINNED_MODEL,
            temperature=0.0,
            metadata={"input_id": inp["input_id"], "repeat": rep},
        )
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = adapter.generate(req)
                raw_text = resp.text.strip()
                canon = canonicalize(raw_text, inp["role"])
                cost = calculate_cost(resp.input_tokens, resp.output_tokens)
                b_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

                return {
                    "input_id": inp["input_id"],
                    "repeat": rep,
                    "role": inp["role"],
                    "target": inp["target_canonical"],
                    "raw_text": raw_text,
                    "canonical": canon,
                    "byte_hash": b_hash,
                    "returned_model": resp.returned_model,
                    "fingerprint": resp.system_fingerprint,
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "latency_s": resp.latency_s,
                    "cost_usd": cost,
                }
            except Exception as e:
                last_err = e
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(
            f"Failed call for {inp['input_id']} repeat {rep} after 4 attempts: {last_err}"
        )

    completed_count = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(execute_call, item) for item in work_items]
        for fut in as_completed(futures):
            res = fut.result()
            results_by_input[res["input_id"]].append(res)
            total_spend += res["cost_usd"]
            total_input_tokens += res["input_tokens"]
            total_output_tokens += res["output_tokens"]
            completed_count += 1
            if completed_count % 100 == 0:
                print(
                    f"  Progress: {completed_count}/1000 calls completed (${total_spend:.4f}, {time.time() - t0:.1f}s)",
                    flush=True,
                )

    print(
        f"\nAll 1,000 audit calls completed in {time.time() - t0:.1f}s. Total spend: ${total_spend:.4f}"
    )

    # Evaluate determinism
    unanimous_inputs = 0
    byte_identical_repeats = 0
    total_evaluated_repeats = 0

    per_input_summary = []
    decode_variances = []
    doc_agreements: dict[str, list[float]] = defaultdict(list)

    for inp in sampled_inputs:
        iid = inp["input_id"]
        reps = sorted(results_by_input[iid], key=lambda r: r["repeat"])
        canons = [r["canonical"] for r in reps]
        byte_hashes = [r["byte_hash"] for r in reps]

        unique_canons = set(canons)
        is_unanimous = len(unique_canons) == 1
        if is_unanimous:
            unanimous_inputs += 1

        ref_hash = byte_hashes[0]
        matching_bytes = sum(1 for h in byte_hashes if h == ref_hash)
        byte_identical_repeats += matching_bytes
        total_evaluated_repeats += len(byte_hashes)

        # Variance of agreement with target
        target = inp["target_canonical"]
        binary_acc = [1.0 if c == target else 0.0 for c in canons]
        if len(binary_acc) > 1:
            var_dec = statistics.pvariance(binary_acc)
            decode_variances.append(var_dec)
        doc_agreements[inp["document_id"]].append(statistics.mean(binary_acc))

        per_input_summary.append(
            {
                "input_id": iid,
                "role": inp["role"],
                "target": target,
                "unanimous_canonical": is_unanimous,
                "unique_canonical_count": len(unique_canons),
                "canonical_outcomes": canons,
                "byte_identical_rate": matching_bytes / len(byte_hashes),
            }
        )

    canonical_agreement_rate = unanimous_inputs / float(TOTAL_INPUTS)
    byte_identical_rate = byte_identical_repeats / float(total_evaluated_repeats)
    mean_sigma2_decode = statistics.mean(decode_variances) if decode_variances else 0.0

    # Document variance
    doc_means = [statistics.mean(accs) for accs in doc_agreements.values() if accs]
    sigma2_document = statistics.variance(doc_means) if len(doc_means) > 1 else 0.01

    # Strict (D) classification rule
    if unanimous_inputs == TOTAL_INPUTS:
        regime = "D_CONFIRMED"
        m_star = 1
        m_star_reason = "Unanimous canonical agreement on 100/100 audited inputs under repetition"
    else:
        regime = "S_CONFIRMED"
        # Solve m* on [1, 2, 3, 5] grid
        # m* = min { m in [1,2,3,5] : sigma_decode^2 / m <= 0.10 * sigma_document^2 }
        target_var = 0.10 * sigma2_document
        m_star = 5
        m_star_reason = "Fallback m*=5 (hierarchical bootstrap)"
        for m_cand in [1, 2, 3, 5]:
            if (mean_sigma2_decode / m_cand) <= target_var:
                m_star = m_cand
                m_star_reason = f"m*={m_cand} satisfies decode variance ratio <= 0.10"
                break

    print("\n================ AUDIT VERDICT ================")
    print(f"Regime: {regime}")
    print(
        f"Unanimous Canonical Inputs: {unanimous_inputs}/{TOTAL_INPUTS} ({canonical_agreement_rate * 100:.1f}%)"
    )
    print(f"Byte-Identical Repeat Rate: {byte_identical_rate * 100:.1f}%")
    print(f"Decode Variance (sigma2_dec): {mean_sigma2_decode:.6f}")
    print(f"Document Variance (sigma2_doc): {sigma2_document:.6f}")
    print(f"Selected m*: {m_star} ({m_star_reason})")
    print("================================================")

    now_utc = datetime.now(UTC).isoformat()
    report = {
        "timestamp_utc": now_utc,
        "model": PINNED_MODEL,
        "total_inputs": TOTAL_INPUTS,
        "repeats_per_input": REPEATS,
        "total_calls": len(work_items),
        "total_spend_usd": total_spend,
        "unanimous_canonical_inputs": unanimous_inputs,
        "canonical_agreement_rate": canonical_agreement_rate,
        "byte_identical_repeat_rate": byte_identical_rate,
        "regime_classification": regime,
        "sigma2_decode": mean_sigma2_decode,
        "sigma2_document": sigma2_document,
        "m_star": m_star,
        "m_star_reason": m_star_reason,
        "per_input_summary": per_input_summary,
    }

    audits_dir = settings.path("audits")
    audits_dir.mkdir(parents=True, exist_ok=True)
    json_path = audits_dir / "AUDIT_RECEIVER_REGIME.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = audits_dir / "AUDIT_RECEIVER_REGIME.md"
    md_content = f"""# Finalist Receiver 100x10 Operational Reproducibility Audit

**Date:** {now_utc}
**Model Configuration:** `{PINNED_MODEL}` (OpenAI, pinned snapshot)
**Total Calls:** 1,000 ({TOTAL_INPUTS} inputs x {REPEATS} repeats)
**Total Spend:** ${total_spend:.4f} USD
**Unanimous Canonical Outcomes:** {unanimous_inputs} / {TOTAL_INPUTS} ({canonical_agreement_rate * 100:.1f}%)
**Byte-Identical Repeat Rate:** {byte_identical_rate * 100:.1f}% (diagnostic)
**Regime Verdict:** **{regime}**
**Selected $m^\\star$:** `{m_star}` ({m_star_reason})

---

## 1. Regulatory Audit Rule

Per Preregistration v1.2 §6 and Master Prompt 1 Section 10:
- **`D_CONFIRMED`** only if EVERY ONE of the 100 representative receiver inputs achieves unanimous canonical agreement across all 10 repeats.
- Any canonical disagreement forces **`S_CONFIRMED`**.
- No majority voting is permitted.
- Canonical matcher outcome is the primary scientific object; raw byte identity is reported strictly as an operational diagnostic.

## 2. Statistical Findings

- **Mean Decode Variance ($\\widehat\\sigma^2_{{\\mathrm{{decode}}}}$):** `{mean_sigma2_decode:.6f}`
- **Document Variance ($\\widehat\\sigma^2_{{\\mathrm{{document}}}}$):** `{sigma2_document:.6f}`
- **Variance Ratio:** `{mean_sigma2_decode / max(1e-6, sigma2_document):.6f}`
- **Replication $m^\\star$:** `{m_star}`

## 3. Operational Conclusion

The configuration is classified as **`{regime}`**.
"""
    md_path.write_text(md_content, encoding="utf-8")

    print(f"\nWrote audit json: {json_path}")
    print(f"Wrote audit markdown: {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
