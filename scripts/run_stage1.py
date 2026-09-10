#!/usr/bin/env python3
"""Stage 1 Execution Runner — Clean Restart under Low-Cost Primary Model (gpt-5.1-2025-11-13).

Executes the complete canonical scientific path on exactly the 100 frozen STAGE1 documents:
  - Source frame loading & deterministic atomization
  - Role-stratified focal sampling (k=3)
  - Natural relay execution (budget=200 tokens, gpt-5.1-2025-11-13, reasoning_effort=none)
  - Deterministic transmission matching (T_z in {0, 1})
  - Availability intervention construction (del / ins)
  - Intervention failure caps verification (Wave A stop-check)
  - Natural receiver execution (m* independent stochastic draws)
  - Counterfactual receiver execution (m* independent stochastic draws)
  - Deterministic potential outcome matching (D+, R^-, Delta_av)
  - Matched prior-access probing (m_prior=10 on eligible classes: scope, period, numeric)
  - Causal decomposition (A = Rbar_0 + Tbar * Deltabar + Cov(T, Delta_av))
  - Stage-1 Mechanism Gate evaluation (Rbar_0 >= 0.10 or prior_effect >= 0.10)
  - Full cost reconciliation and artifact export
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
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
from handoff_fidelity.atomizer.verify import filter_eligible  # noqa: E402
from handoff_fidelity.causal.estimands import decompose  # noqa: E402
from handoff_fidelity.causal.gates import evaluate_stage1_gate  # noqa: E402
from handoff_fidelity.causalrelay.renderer import render_atom  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.editing.editor import InvalidEdit, build_counterfactual  # noqa: E402
from handoff_fidelity.matcher.match import is_transmitted, recovered  # noqa: E402
from handoff_fidelity.models import AtomCausalRecord  # noqa: E402
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402
from handoff_fidelity.providers.adapters import OpenAIAdapter  # noqa: E402
from handoff_fidelity.providers.protocol import GenerationRequest  # noqa: E402
from handoff_fidelity.receiver.prompt import (  # noqa: E402
    build_prior_probe_prompt,
    build_receiver_prompt,
)
from handoff_fidelity.relay.task import GLOBAL_DOWNSTREAM_TASK  # noqa: E402
from handoff_fidelity.sampling.design import all_inclusion_probabilities, select_focal  # noqa: E402
from handoff_fidelity.seeds import derive_seed, rng_for  # noqa: E402

PINNED_MODEL = "gpt-5.1-2025-11-13"
RESTARTED_STAGE1_INCREMENTAL_CEILING_USD = 8.50
TOTAL_NEW_PROVIDER_SPEND_CEILING_USD = 12.50
M_PRIOR = 10
K_FOCAL = 3


def load_env_safe() -> None:
    raw_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    if not raw_home:
        candidate = Path.home() / ".handoff-fidelity"
        if candidate.exists() and (candidate / ".env").exists():
            raw_home = str(candidate)
            os.environ["HANDOFF_PRIVATE_HOME"] = raw_home
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


def calculate_cost_gpt51(in_tok: int, out_tok: int) -> float:
    # gpt-5.1-2025-11-13 pricing: $1.25/MTok in, $10.00/MTok out
    in_cost = (max(0, in_tok) / 1_000_000.0) * 1.25
    out_cost = (max(0, out_tok) / 1_000_000.0) * 10.00
    return in_cost + out_cost


class FailClosedRestartDiskCache:
    """Isolated disk cache for restarted stage 1 with fail-closed assertions."""

    def __init__(self, cache_dir: Path, expected_model: str) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.expected_model = expected_model
        # Verify cache_dir does not overlap with quarantined Terra cache
        assert "stage1/cache" not in str(cache_dir), (
            f"MIXED_MODEL_CACHE_VIOLATION: attempted to use Terra cache dir {cache_dir}"
        )

    def get(self, key: str) -> dict[str, Any] | None:
        p = self.cache_dir / f"{key}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                returned_model = data.get("returned_model", "")
                if self.expected_model not in returned_model:
                    raise RuntimeError(
                        f"MIXED_MODEL_CACHE_VIOLATION: Cached entry {key} has model {returned_model!r}, expected {self.expected_model!r}"
                    )
                return data
            except Exception as exc:
                if "MIXED_MODEL_CACHE_VIOLATION" in str(exc):
                    raise
                return None
        return None

    def put(self, key: str, data: dict[str, Any]) -> None:
        returned_model = data.get("returned_model", "")
        if self.expected_model not in returned_model:
            raise RuntimeError(
                f"MIXED_MODEL_CACHE_VIOLATION: Attempting to put record with model {returned_model!r}, expected {self.expected_model!r}"
            )
        p = self.cache_dir / f"{key}.json"
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-workers", type=int, default=15)
    parser.add_argument(
        "--m-star", type=int, default=2, help="Receiver replication count derived from audit"
    )
    args = parser.parse_args()

    m_star = args.m_star
    assert m_star in (1, 2, 3, 5), f"Invalid m_star {m_star}"

    load_env_safe()
    settings = load_settings()
    manifest_path = settings.path("source_manifests", "STAGE1.csv")

    if not manifest_path.exists():
        print(f"ERROR: STAGE1 manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest_hash = sha256_file(manifest_path)
    expected_manifest_hash = "4ed951bec7fd4ac96838e9d2fa8faf6cdee614d8c279299399cff8725fdbcbf8"  # pragma: allowlist secret
    assert manifest_hash == expected_manifest_hash, (
        f"Stage-1 manifest hash mismatch: {manifest_hash} != {expected_manifest_hash}"
    )
    print(f"Loading Stage-1 manifest: {manifest_path} (sha256: {manifest_hash})")

    docs = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            docs.append(r)

    print(f"Loaded {len(docs)} Stage-1 documents.")
    assert len(docs) == 100, f"Expected 100 Stage-1 documents, found {len(docs)}"

    # Isolated restart cache namespace in private home
    cache_root = Path(settings.private_home) / "runs" / "stage1_restart_gpt51" / "cache"
    relay_cache = FailClosedRestartDiskCache(cache_root / "relay", PINNED_MODEL)
    receiver_cache = FailClosedRestartDiskCache(cache_root / "receiver", PINNED_MODEL)
    prior_cache = FailClosedRestartDiskCache(cache_root / "prior_probe", PINNED_MODEL)

    adapter = OpenAIAdapter(model=PINNED_MODEL, allow_network=True)
    run_id = f"stage1_restart_gpt51-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    print(f"Initiating Clean Stage-1 Restart Run ID: {run_id}")
    print(f"Configuration: model={PINNED_MODEL}, m*={m_star}, m_prior={M_PRIOR}, k_focal={K_FOCAL}")

    total_spend = 0.0
    calls_executed = 0
    cache_hits = 0
    ledger: list[dict[str, Any]] = []

    def call_model_with_cache(
        *,
        cache: FailClosedRestartDiskCache,
        cache_key: str,
        prompt: str,
        max_output_tokens: int,
        seed: int,
        stage_label: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        nonlocal total_spend, calls_executed, cache_hits

        cached = cache.get(cache_key)
        if cached is not None:
            cache_hits += 1
            return cached

        if total_spend >= RESTARTED_STAGE1_INCREMENTAL_CEILING_USD:
            raise RuntimeError(
                f"COST_AUTHORIZATION_REQUIRED: Restarted Stage 1 spend ${total_spend:.4f} reached ceiling ${RESTARTED_STAGE1_INCREMENTAL_CEILING_USD:.2f}"
            )

        req_meta = dict(metadata)
        req_meta["reasoning_effort"] = "none"

        req = GenerationRequest(
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            model=PINNED_MODEL,
            temperature=0.0,
            seed=seed,
            metadata=req_meta,
        )

        last_err: Exception | None = None
        for attempt in range(5):
            try:
                resp = adapter.generate(req)
                raw_text = resp.text.strip()
                cost = calculate_cost_gpt51(resp.input_tokens, resp.output_tokens)

                record = {
                    "cache_key": cache_key,
                    "stage": stage_label,
                    "prompt": prompt,
                    "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "raw_text": raw_text,
                    "returned_model": resp.returned_model,
                    "provider_request_id": resp.provider_request_id,
                    "system_fingerprint": resp.system_fingerprint,
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "reasoning_tokens": resp.reasoning_tokens,
                    "latency_s": resp.latency_s,
                    "cost_usd": cost,
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "metadata": req_meta,
                }
                cache.put(cache_key, record)
                total_spend += cost
                calls_executed += 1
                ledger.append(record)
                return record
            except Exception as e:
                last_err = e
                time.sleep(1.0 * (attempt + 1))

        raise RuntimeError(f"Model call failed for {cache_key} after 5 attempts: {last_err}")

    # =========================================================================
    # STEP 1: Process Documents and Execute Wave A (Relay Calls)
    # =========================================================================
    print("\n--- Step 1 / Wave A: Document Atomization, Focal Sampling & Relay Messages ---")
    doc_data = []

    for row in docs:
        doc_id = row["document_id"]
        frame_file = Path(row["frame_path"])
        if not frame_file.exists():
            frame_file = settings.path("data", "source_pool", "frames", f"{doc_id}.txt")
        frame_text = frame_file.read_text(encoding="utf-8")
        atoms = atomize(doc_id, frame_text)
        rep = filter_eligible(atoms, frame_text, require_human_verification=False)
        assert len(rep.eligible) > 0, f"No eligible atoms for {doc_id}"

        rng = rng_for(settings.master_seed, "stage1", doc_id)
        focals = select_focal(rep.eligible, rng=rng, k=K_FOCAL)
        pis = all_inclusion_probabilities(rep.eligible, k=K_FOCAL)

        relay_prompt = (
            f"{GLOBAL_DOWNSTREAM_TASK}\n\nToken budget: {settings.relay_budget_tokens}.\n\n"
            f"--- SOURCE ---\n{frame_text}\n--- END SOURCE ---\n\nHandoff note:"
        )
        relay_seed = (
            derive_seed(settings.master_seed, "stage1_restart", "relay", doc_id)
            % 9223372036854775807
        )
        relay_prompt_hash = hashlib.sha256(relay_prompt.encode("utf-8")).hexdigest()
        relay_cache_key = hashlib.sha256(f"relay:{doc_id}:{relay_prompt_hash}".encode()).hexdigest()

        doc_data.append(
            {
                "doc_id": doc_id,
                "frame_text": frame_text,
                "eligible_atoms": rep.eligible,
                "focals": focals,
                "pis": pis,
                "relay_prompt": relay_prompt,
                "relay_seed": relay_seed,
                "relay_cache_key": relay_cache_key,
            }
        )

    print(
        f"Executing Wave A: 100 relay calls under {PINNED_MODEL} (max_workers={args.max_workers})..."
    )
    t0 = time.time()

    def do_relay(d: dict[str, Any]) -> tuple[str, str]:
        rec = call_model_with_cache(
            cache=relay_cache,
            cache_key=d["relay_cache_key"],
            prompt=d["relay_prompt"],
            max_output_tokens=512,
            seed=d["relay_seed"],
            stage_label="relay",
            metadata={"doc_id": d["doc_id"]},
        )
        return d["doc_id"], rec["raw_text"]

    relay_messages: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futs = [executor.submit(do_relay, d) for d in doc_data]
        for fut in as_completed(futs):
            did, msg = fut.result()
            relay_messages[did] = msg

    wave_a_spend = total_spend
    print(
        f"Completed 100 relay calls in {time.time() - t0:.1f}s. Wave A spend: ${wave_a_spend:.4f}"
    )

    # =========================================================================
    # STEP 2: Match Transmission & Construct Interventions (Wave A Validation)
    # =========================================================================
    print("\n--- Step 2: Match Transmission & Construct Interventions ---")
    atom_records_meta = []
    failed_edits: dict[str, str] = {}
    t1_count = 0
    t0_count = 0
    t1_failures = 0
    t0_failures = 0

    for d in doc_data:
        doc_id = d["doc_id"]
        relay_msg = relay_messages[doc_id]
        by_id = {a.atom_id: a for a in d["eligible_atoms"]}

        for focal in d["focals"]:
            atom = by_id[focal.atom_id]
            t_val = int(
                is_transmitted(
                    relay_msg, canonical_value=atom.canonical_value, role=atom.role.value
                )
            )
            if t_val == 1:
                t1_count += 1
            else:
                t0_count += 1

            try:
                edit_res = build_counterfactual(
                    relay_msg,
                    document_id=doc_id,
                    atom_id=atom.atom_id,
                    canonical_value=atom.canonical_value,
                    role=atom.role.value,
                    transmitted=t_val,
                    rendered=render_atom(atom),
                    budget=settings.relay_budget_tokens,
                )
                cf_msg = edit_res.text
                mech = edit_res.log.mechanism
                edit_valid = True
            except InvalidEdit as exc:
                failed_edits[atom.atom_id] = str(exc)
                cf_msg = ""
                mech = "failed"
                edit_valid = False
                if t_val == 1:
                    t1_failures += 1
                else:
                    t0_failures += 1

            atom_records_meta.append(
                {
                    "doc_id": doc_id,
                    "atom": atom,
                    "focal": focal,
                    "transmitted": t_val,
                    "natural_message": relay_msg,
                    "counterfactual_message": cf_msg,
                    "edit_mechanism": mech,
                    "edit_valid": edit_valid,
                }
            )

    total_focals = len(atom_records_meta)
    overall_failure_rate = len(failed_edits) / float(total_focals)
    p_fail_t1 = t1_failures / float(t1_count) if t1_count > 0 else 0.0
    p_fail_t0 = t0_failures / float(t0_count) if t0_count > 0 else 0.0
    differential_failure_rate = abs(p_fail_t1 - p_fail_t0)

    print(f"Total instrumented focal atoms: {total_focals}")
    print(
        f"Transmission rate among focal atoms: {statistics.mean(a['transmitted'] for a in atom_records_meta):.3f} (T=1: {t1_count}, T=0: {t0_count})"
    )
    print(
        f"Overall intervention failure rate: {len(failed_edits)}/{total_focals} = {overall_failure_rate * 100:.2f}% (Cap: 15.0%)"
    )
    print(
        f"Differential failure rate: |{p_fail_t1 * 100:.2f}% - {p_fail_t0 * 100:.2f}%| = {differential_failure_rate * 100:.2f}% (Cap: 5.0%)"
    )

    assert overall_failure_rate <= 0.15, (
        f"STOP_AND_REPAIR: Overall intervention failure {overall_failure_rate:.3f} > 0.15"
    )
    assert differential_failure_rate <= 0.05, (
        f"STOP_AND_REPAIR: Differential failure {differential_failure_rate:.3f} > 0.05"
    )
    print("Wave A Intervention Validity Gate: PASSED!")

    # =========================================================================
    # STEP 3: Execute Wave B (Receiver Calls m*)
    # =========================================================================
    print(f"\n--- Step 3 / Wave B: Natural & Counterfactual Receiver Queries (m*={m_star}) ---")
    receiver_tasks = []
    for item in atom_records_meta:
        doc_id = item["doc_id"]
        atom = item["atom"]

        nat_prompt = build_receiver_prompt(
            message=item["natural_message"],
            role=atom.role,
            subject=doc_id,
            attribute=f"the {atom.role.value} value",
        )
        for rep in range(1, m_star + 1):
            key = hashlib.sha256(
                f"receiver_nat:{doc_id}:{atom.atom_id}:rep{rep}:{hashlib.sha256(nat_prompt.encode()).hexdigest()}".encode()
            ).hexdigest()
            seed = (
                derive_seed(
                    settings.master_seed,
                    "stage1_restart",
                    "receiver_natural",
                    doc_id,
                    atom.atom_id,
                    f"rep{rep}",
                )
                % 9223372036854775807
            )
            receiver_tasks.append(
                {
                    "type": "natural",
                    "doc_id": doc_id,
                    "atom_id": atom.atom_id,
                    "role": atom.role.value,
                    "target_canonical": atom.canonical_value,
                    "rep": rep,
                    "prompt": nat_prompt,
                    "seed": seed,
                    "cache_key": key,
                }
            )

        if item["edit_valid"]:
            cf_prompt = build_receiver_prompt(
                message=item["counterfactual_message"],
                role=atom.role,
                subject=doc_id,
                attribute=f"the {atom.role.value} value",
            )
            for rep in range(1, m_star + 1):
                key = hashlib.sha256(
                    f"receiver_cf:{doc_id}:{atom.atom_id}:rep{rep}:{hashlib.sha256(cf_prompt.encode()).hexdigest()}".encode()
                ).hexdigest()
                seed = (
                    derive_seed(
                        settings.master_seed,
                        "stage1_restart",
                        "receiver_cf",
                        doc_id,
                        atom.atom_id,
                        f"rep{rep}",
                    )
                    % 9223372036854775807
                )
                receiver_tasks.append(
                    {
                        "type": "counterfactual",
                        "doc_id": doc_id,
                        "atom_id": atom.atom_id,
                        "role": atom.role.value,
                        "target_canonical": atom.canonical_value,
                        "rep": rep,
                        "prompt": cf_prompt,
                        "seed": seed,
                        "cache_key": key,
                    }
                )

    print(f"Total receiver tasks to execute: {len(receiver_tasks)}")
    t0 = time.time()

    def do_receiver(task: dict[str, Any]) -> dict[str, Any]:
        rec = call_model_with_cache(
            cache=receiver_cache,
            cache_key=task["cache_key"],
            prompt=task["prompt"],
            max_output_tokens=512,
            seed=task["seed"],
            stage_label=f"receiver_{task['type']}",
            metadata={"doc_id": task["doc_id"], "atom_id": task["atom_id"], "rep": task["rep"]},
        )
        is_rec = int(
            recovered(rec["raw_text"], canonical_value=task["target_canonical"], role=task["role"])
        )
        return {
            "type": task["type"],
            "atom_id": task["atom_id"],
            "rep": task["rep"],
            "recovered": is_rec,
            "raw_text": rec["raw_text"],
        }

    receiver_results: dict[str, dict[str, dict[int, int]]] = defaultdict(
        lambda: {"natural": {}, "counterfactual": {}}
    )
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futs = [executor.submit(do_receiver, t) for t in receiver_tasks]
        for done_count, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            receiver_results[res["atom_id"]][res["type"]][res["rep"]] = res["recovered"]
            if done_count % 200 == 0 or done_count == len(receiver_tasks):
                print(
                    f"  Receiver progress: {done_count}/{len(receiver_tasks)} completed (${total_spend:.4f}, {time.time() - t0:.1f}s)",
                    flush=True,
                )

    receiver_spend = total_spend - wave_a_spend

    # =========================================================================
    # STEP 4: Execute Prior Probes (m_prior = 10) on Eligible Classes
    # =========================================================================
    print(
        f"\n--- Step 4 / Wave B: Prior Probes (m_prior={M_PRIOR}) on Eligible Classes ---",
        flush=True,
    )
    prior_tasks = []
    eligible_prior_classes = ("scope", "period", "numeric")

    for item in atom_records_meta:
        atom = item["atom"]
        if atom.role.value in eligible_prior_classes:
            doc_id = item["doc_id"]
            p_prompt = build_prior_probe_prompt(
                role=atom.role,
                subject=doc_id,
                attribute=f"the {atom.role.value} value",
            )
            for rep in range(1, M_PRIOR + 1):
                key = hashlib.sha256(
                    f"prior:{doc_id}:{atom.atom_id}:rep{rep}:{hashlib.sha256(p_prompt.encode()).hexdigest()}".encode()
                ).hexdigest()
                seed = (
                    derive_seed(
                        settings.master_seed,
                        "stage1_restart",
                        "prior_probe",
                        doc_id,
                        atom.atom_id,
                        f"rep{rep}",
                    )
                    % 9223372036854775807
                )
                prior_tasks.append(
                    {
                        "doc_id": doc_id,
                        "atom_id": atom.atom_id,
                        "role": atom.role.value,
                        "target_canonical": atom.canonical_value,
                        "rep": rep,
                        "prompt": p_prompt,
                        "seed": seed,
                        "cache_key": key,
                    }
                )

    print(
        f"Total prior probe queries: {len(prior_tasks)} across {len(prior_tasks) // M_PRIOR} atoms",
        flush=True,
    )
    t0 = time.time()

    def do_prior(task: dict[str, Any]) -> dict[str, Any]:
        rec = call_model_with_cache(
            cache=prior_cache,
            cache_key=task["cache_key"],
            prompt=task["prompt"],
            max_output_tokens=512,
            seed=task["seed"],
            stage_label="prior_probe",
            metadata={"doc_id": task["doc_id"], "atom_id": task["atom_id"], "rep": task["rep"]},
        )
        is_rec = int(
            recovered(rec["raw_text"], canonical_value=task["target_canonical"], role=task["role"])
        )
        return {
            "atom_id": task["atom_id"],
            "role": task["role"],
            "rep": task["rep"],
            "recovered": is_rec,
        }

    prior_results_by_atom: dict[str, list[int]] = defaultdict(list)
    prior_role_by_atom: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futs = [executor.submit(do_prior, t) for t in prior_tasks]
        for done_count, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            prior_results_by_atom[res["atom_id"]].append(res["recovered"])
            prior_role_by_atom[res["atom_id"]] = res["role"]
            if done_count % 200 == 0 or done_count == len(prior_tasks):
                print(
                    f"  Prior probe progress: {done_count}/{len(prior_tasks)} completed (${total_spend:.4f}, {time.time() - t0:.1f}s)",
                    flush=True,
                )

    prior_spend = total_spend - wave_a_spend - receiver_spend

    # Calculate prior effect per eligible class
    prior_effects: dict[str, float] = {}
    for role_name in eligible_prior_classes:
        atoms_of_role = [aid for aid, r in prior_role_by_atom.items() if r == role_name]
        if atoms_of_role:
            accs = [statistics.mean(prior_results_by_atom[aid]) for aid in atoms_of_role]
            prior_effects[role_name] = round(statistics.mean(accs), 4)
        else:
            prior_effects[role_name] = 0.0

    print("\nMatched Prior-Access Effects by Class:")
    for role_name, eff in prior_effects.items():
        print(f"  {role_name}: {eff:.4f}")

    # =========================================================================
    # STEP 5: Assemble Causal Records & Run Canonical Decomposition
    # =========================================================================
    print("\n--- Step 5: Assemble Causal Records & Run Decomposition ---")
    causal_records: list[AtomCausalRecord] = []

    for item in atom_records_meta:
        if not item["edit_valid"]:
            continue

        atom_id = item["atom"].atom_id
        doc_id = item["doc_id"]
        t_val = item["transmitted"]

        nat_reps = list(receiver_results[atom_id]["natural"].values())
        cf_reps = list(receiver_results[atom_id]["counterfactual"].values())

        if len(nat_reps) != m_star or len(cf_reps) != m_star:
            continue

        y_nat_bar = statistics.mean(nat_reps)
        y_cf_bar = statistics.mean(cf_reps)

        if t_val == 1:
            d_plus = y_nat_bar
            r_minus = y_cf_bar
        else:
            d_plus = y_cf_bar
            r_minus = y_nat_bar

        rec = AtomCausalRecord(
            document_id=doc_id,
            atom_id=atom_id,
            role=item["atom"].role,
            pi=item["focal"].pi,
            transmitted=t_val,
            r_minus=r_minus,
            d_plus=d_plus,
            edit_mechanism=item["edit_mechanism"],
        )
        causal_records.append(rec)

    print(f"Total valid paired causal records: {len(causal_records)}")
    decomp = decompose(causal_records)

    print("\nStage 1 Causal Decomposition (Low-Cost Primary Restart):")
    print(f"  Endpoint Fidelity (A):           {decomp.endpoint_fidelity:.4f}")
    print(f"  Reconstruction (Rbar_0):         {decomp.r_bar_zero:.4f}")
    print(f"  Transmission Rate (Tbar):        {decomp.t_bar:.4f}")
    print(f"  Average Availability (Deltabar): {decomp.delta_bar:.4f}")
    print(f"  Volume (Tbar * Deltabar):        {decomp.volume:.4f}")
    print(f"  Alignment Cov(T, Delta):         {decomp.alignment:.4f}")
    print(f"  Communication Surplus (C_comm):  {decomp.c_comm:.4f}")
    print(f"  Reconstruction Share (C_recon):  {decomp.c_recon:.4f}")
    print(f"  Identity Residual:               {decomp.identity_residual:.6e}")

    # Verify numerical identity
    assert abs(decomp.identity_residual) < 1e-6, (
        f"Decomposition identity violated: residual={decomp.identity_residual}"
    )

    # =========================================================================
    # STEP 6: Evaluate Frozen Stage-1 Mechanism Gate Exactly Once
    # =========================================================================
    print("\n--- Step 6: Evaluate Stage-1 Mechanism Gate ---")
    gate = evaluate_stage1_gate(
        reconstruction_contribution=decomp.r_bar_zero,
        prior_effects=prior_effects,
        eligible_prior_classes=eligible_prior_classes,
        reconstruction_gate=0.10,
        prior_gate=0.10,
    )
    print("Stage-1 Gate Result:")
    print(f"  Proceed: {gate.proceed}")
    print(f"  Verdict: {'STAGE1_GATE_PASS' if gate.proceed else 'STAGE1_GATE_FAIL'}")
    print(f"  Reason:  {gate.reason}")
    print(
        f"  Reconstruction Contribution: {gate.reconstruction_contribution:.4f} (clears 0.10: {gate.reconstruction_contribution >= 0.10})"
    )
    print(
        f"  Prior Effects: {gate.prior_effects} (clears 0.10: {any(v >= 0.10 for v in gate.prior_effects.values())})"
    )

    # =========================================================================
    # STEP 7: Persist All Canonical Low-Cost Primary Stage-1 Artifacts
    # =========================================================================
    print("\n--- Step 7: Export Canonical Restart Artifacts ---")
    private_home = Path(settings.private_home)
    runs_dir = private_home / "runs" / "stage1_restart_gpt51"
    audits_dir = private_home / "audits"
    runs_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    results_data = {
        "event": "STAGE1_RESULTS_LOW_COST_PRIMARY",
        "run_id": run_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": PINNED_MODEL,
        "receiver_regime": "S_CONFIRMED",
        "m_star": m_star,
        "m_prior": M_PRIOR,
        "k_focal": K_FOCAL,
        "n_documents": len(docs),
        "n_instrumented_atoms": len(atom_records_meta),
        "n_valid_causal_records": len(causal_records),
        "failed_edits_count": len(failed_edits),
        "overall_intervention_failure_rate": round(overall_failure_rate, 4),
        "differential_intervention_failure_rate": round(differential_failure_rate, 4),
        "decomposition": decomp.to_dict(),
        "prior_effects": prior_effects,
        "gate_proceed": gate.proceed,
        "gate_verdict": "STAGE1_GATE_PASS" if gate.proceed else "STAGE1_GATE_FAIL",
        "gate_reason": gate.reason,
        "spend_breakdown_usd": {
            "wave_a_relay": round(wave_a_spend, 4),
            "wave_b_receiver": round(receiver_spend, 4),
            "wave_b_prior": round(prior_spend, 4),
            "total_stage1_spend": round(total_spend, 4),
        },
        "calls_executed": calls_executed,
        "cache_hits": cache_hits,
    }

    gate_data = {
        "event": "STAGE1_GATE_LOW_COST_PRIMARY",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "model": PINNED_MODEL,
        "reconstruction_contribution": decomp.r_bar_zero,
        "reconstruction_clears_threshold": decomp.r_bar_zero >= 0.10,
        "prior_effects": prior_effects,
        "prior_clears_threshold": any(v >= 0.10 for v in prior_effects.values()),
        "reconstruction_gate": 0.10,
        "prior_gate": 0.10,
        "eligible_prior_classes": list(eligible_prior_classes),
        "proceed": gate.proceed,
        "verdict": "STAGE1_GATE_PASS" if gate.proceed else "STAGE1_GATE_FAIL",
        "reason": gate.reason,
    }

    cost_ledger_data = {
        "event": "STAGE1_COST_LEDGER_LOW_COST_PRIMARY",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "model": PINNED_MODEL,
        "total_spend_usd": round(total_spend, 4),
        "ceiling_usd": RESTARTED_STAGE1_INCREMENTAL_CEILING_USD,
        "ceiling_respected": total_spend <= RESTARTED_STAGE1_INCREMENTAL_CEILING_USD,
        "calls_executed": calls_executed,
        "cache_hits": cache_hits,
        "calls_summary": {
            "relay": len(docs),
            "receiver_natural": len(atom_records_meta) * m_star,
            "receiver_counterfactual": len([a for a in atom_records_meta if a["edit_valid"]])
            * m_star,
            "prior_probe": len(prior_tasks),
        },
        "spend_breakdown_usd": {
            "wave_a_relay": round(wave_a_spend, 4),
            "wave_b_receiver": round(receiver_spend, 4),
            "wave_b_prior": round(prior_spend, 4),
            "total_restarted_stage1": round(total_spend, 4),
        },
    }

    run_manifest_data = {
        "event": "STAGE1_RUN_MANIFEST_LOW_COST_PRIMARY",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "stage1_manifest_hash": manifest_hash,
        "model": PINNED_MODEL,
        "transport": "synchronous",
        "reasoning_effort": "none",
        "receiver_regime": "S_CONFIRMED",
        "m_star": m_star,
        "m_prior": M_PRIOR,
        "k_focal": K_FOCAL,
        "relay_budget_tokens": settings.relay_budget_tokens,
        "verdict": gate_data["verdict"],
        "cache_namespace": "runs/stage1_restart_gpt51/cache/",
    }

    # Save to runs and audits
    for path, data in [
        (runs_dir / "STAGE1_RESULTS_LOW_COST_PRIMARY.json", results_data),
        (audits_dir / "STAGE1_RESULTS_LOW_COST_PRIMARY.json", results_data),
        (runs_dir / "STAGE1_GATE_LOW_COST_PRIMARY.json", gate_data),
        (audits_dir / "STAGE1_GATE_LOW_COST_PRIMARY.json", gate_data),
        (runs_dir / "STAGE1_COST_LEDGER_LOW_COST_PRIMARY.json", cost_ledger_data),
        (audits_dir / "STAGE1_COST_LEDGER_LOW_COST_PRIMARY.json", cost_ledger_data),
        (runs_dir / "STAGE1_RUN_MANIFEST_LOW_COST_PRIMARY.json", run_manifest_data),
        (audits_dir / "STAGE1_RUN_MANIFEST_LOW_COST_PRIMARY.json", run_manifest_data),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Saved: {path}")

    print("\n=======================================================")
    print(f"RESTARTED STAGE 1 COMPLETE: {gate_data['verdict']}")
    print(
        f"Total Provider Spend: ${total_spend:.4f} / ${RESTARTED_STAGE1_INCREMENTAL_CEILING_USD:.2f}"
    )
    print("=======================================================\n")
    return 0 if gate.proceed else 2


if __name__ == "__main__":
    sys.exit(main())
