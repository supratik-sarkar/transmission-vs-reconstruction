#!/usr/bin/env python3
"""Stage 1 Execution Runner.

Executes the complete canonical scientific path on exactly the 100 frozen STAGE1 documents:
  - Source frame loading & deterministic atomization
  - Role-stratified focal sampling (k=3)
  - Natural relay execution (budget=200 tokens, gpt-5.6-terra)
  - Deterministic transmission matching (T_z in {0, 1})
  - Natural receiver execution (m*=2 independent stochastic draws)
  - Availability intervention construction (del / ins)
  - Counterfactual receiver execution (m*=2 independent stochastic draws)
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

STAGE1_INCREMENTAL_CEILING_USD = 18.0
MASTER2_TOTAL_PROVIDER_SPEND_CEILING_USD = 100.0
PINNED_MODEL = "gpt-5.6-terra"
M_STAR = 2
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


def calculate_cost(in_tok: int, out_tok: int) -> float:
    # gpt-5.6-terra pricing: $2/MTok in, $12/MTok out
    in_cost = (max(0, in_tok) / 1_000_000.0) * 2.0
    out_cost = (max(0, out_tok) / 1_000_000.0) * 12.0
    return in_cost + out_cost


class DiskCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict[str, Any] | None:
        p = self.cache_dir / f"{key}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def put(self, key: str, data: dict[str, Any]) -> None:
        p = self.cache_dir / f"{key}.json"
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-workers", type=int, default=15)
    args = parser.parse_args()

    load_env_safe()
    settings = load_settings()
    manifest_path = settings.path("source_manifests", "STAGE1.csv")

    if not manifest_path.exists():
        print(f"ERROR: STAGE1 manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest_hash = sha256_file(manifest_path)
    print(f"Loading Stage-1 manifest: {manifest_path} (sha256: {manifest_hash})")

    docs = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            docs.append(r)

    print(f"Loaded {len(docs)} Stage-1 documents.")
    assert len(docs) == 100, f"Expected 100 Stage-1 documents, found {len(docs)}"

    # Set up disk cache in private home
    cache_root = Path(settings.private_home) / "runs" / "stage1" / "cache"
    relay_cache = DiskCache(cache_root / "relay")
    receiver_cache = DiskCache(cache_root / "receiver")
    prior_cache = DiskCache(cache_root / "prior_probe")

    adapter = OpenAIAdapter(model=PINNED_MODEL, allow_network=True)
    run_id = f"stage1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    print(f"Initiating Stage 1 Run ID: {run_id}")

    total_spend = 0.0
    calls_executed = 0
    cache_hits = 0
    ledger: list[dict[str, Any]] = []

    def call_model_with_cache(
        *,
        cache: DiskCache,
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

        # Check budget before spending
        if total_spend >= STAGE1_INCREMENTAL_CEILING_USD:
            raise RuntimeError(
                f"COST_AUTHORIZATION_REQUIRED: Stage 1 spend ${total_spend:.4f} reached ceiling ${STAGE1_INCREMENTAL_CEILING_USD:.2f}"
            )

        req = GenerationRequest(
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            model=PINNED_MODEL,
            temperature=0.0,
            seed=seed,
            metadata=metadata,
        )

        last_err: Exception | None = None
        for attempt in range(5):
            try:
                resp = adapter.generate(req)
                raw_text = resp.text.strip()
                cost = calculate_cost(resp.input_tokens, resp.output_tokens)

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
                    "metadata": metadata,
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
    # STEP 1: Process Documents and Execute Relay Calls
    # =========================================================================
    print("\n--- Step 1: Document Atomization, Focal Sampling & Relay Messages ---")
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
        relay_seed = derive_seed(settings.master_seed, "stage1", "relay", doc_id)
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

    # Execute relay calls in parallel
    print(f"Executing 100 relay calls (max_workers={args.max_workers})...")
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

    print(f"Completed 100 relay calls in {time.time() - t0:.1f}s. Spend so far: ${total_spend:.4f}")

    # =========================================================================
    # STEP 2: Match Transmission & Construct Interventions
    # =========================================================================
    print("\n--- Step 2: Match Transmission & Construct Interventions ---")
    atom_records_meta = []
    failed_edits: dict[str, str] = {}

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

            # Build counterfactual message
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

    print(f"Total instrumented focal atoms: {len(atom_records_meta)}")
    print(
        f"Transmission rate among focal atoms: {statistics.mean(a['transmitted'] for a in atom_records_meta):.3f}"
    )
    print(f"Intervention construction failures: {len(failed_edits)} / {len(atom_records_meta)}")

    # =========================================================================
    # STEP 3: Execute Natural & Counterfactual Receiver Calls (m* = 2)
    # =========================================================================
    print(f"\n--- Step 3: Natural & Counterfactual Receiver Queries (m*={M_STAR}) ---")

    receiver_tasks = []
    for item in atom_records_meta:
        doc_id = item["doc_id"]
        atom = item["atom"]

        # Natural receiver tasks (2 replicates)
        nat_prompt = build_receiver_prompt(
            message=item["natural_message"],
            role=atom.role,
            subject=doc_id,
            attribute=f"the {atom.role.value} value",
        )
        for rep in (1, 2):
            key = hashlib.sha256(
                f"receiver_nat:{doc_id}:{atom.atom_id}:rep{rep}:{hashlib.sha256(nat_prompt.encode()).hexdigest()}".encode()
            ).hexdigest()
            seed = derive_seed(
                settings.master_seed,
                "stage1",
                "receiver_natural",
                doc_id,
                atom.atom_id,
                f"rep{rep}",
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

        # Counterfactual receiver tasks (2 replicates, only if edit is valid)
        if item["edit_valid"]:
            cf_prompt = build_receiver_prompt(
                message=item["counterfactual_message"],
                role=atom.role,
                subject=doc_id,
                attribute=f"the {atom.role.value} value",
            )
            for rep in (1, 2):
                key = hashlib.sha256(
                    f"receiver_cf:{doc_id}:{atom.atom_id}:rep{rep}:{hashlib.sha256(cf_prompt.encode()).hexdigest()}".encode()
                ).hexdigest()
                seed = derive_seed(
                    settings.master_seed, "stage1", "receiver_cf", doc_id, atom.atom_id, f"rep{rep}"
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

    # =========================================================================
    # STEP 4: Execute Prior Probes (m_prior = 10) on Eligible Classes
    # =========================================================================
    print(f"\n--- Step 4: Prior Probes (m_prior={M_PRIOR}) on Eligible Classes ---", flush=True)
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
                seed = derive_seed(
                    settings.master_seed, "stage1", "prior_probe", doc_id, atom.atom_id, f"rep{rep}"
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
            if done_count % 100 == 0 or done_count == len(prior_tasks):
                print(
                    f"  Prior probe progress: {done_count}/{len(prior_tasks)} completed (${total_spend:.4f}, {time.time() - t0:.1f}s)",
                    flush=True,
                )

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
    # STEP 5: Assemble AtomCausalRecords & Run Decomposition
    # =========================================================================
    print("\n--- Step 5: Assemble Causal Records & Run Decomposition ---")
    causal_records: list[AtomCausalRecord] = []

    for item in atom_records_meta:
        if not item["edit_valid"]:
            continue  # Excluded from paired availability contrast per protocol

        atom_id = item["atom"].atom_id
        doc_id = item["doc_id"]
        t_val = item["transmitted"]

        nat_reps = list(receiver_results[atom_id]["natural"].values())
        cf_reps = list(receiver_results[atom_id]["counterfactual"].values())

        if len(nat_reps) != M_STAR or len(cf_reps) != M_STAR:
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

    print("\nStage 1 Causal Decomposition:")
    print(f"  Endpoint Fidelity (A):           {decomp.endpoint_fidelity:.4f}")
    print(f"  Reconstruction (Rbar_0):         {decomp.r_bar_zero:.4f}")
    print(f"  Transmission Rate (Tbar):        {decomp.t_bar:.4f}")
    print(f"  Average Availability (Deltabar): {decomp.delta_bar:.4f}")
    print(f"  Volume (Tbar * Deltabar):        {decomp.volume:.4f}")
    print(f"  Alignment Cov(T, Delta):         {decomp.alignment:.4f}")
    print(f"  Communication Surplus (C_comm):  {decomp.c_comm:.4f}")
    print(f"  Reconstruction Share (C_recon):  {decomp.c_recon:.4f}")
    print(f"  Identity Residual:               {decomp.identity_residual:.6e}")

    # =========================================================================
    # STEP 6: Evaluate Stage-1 Mechanism Gate
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
    print(f"  Reason:  {gate.reason}")
    print(
        f"  Reconstruction Contribution: {gate.reconstruction_contribution:.4f} (gate: {gate.reconstruction_gate})"
    )
    print(f"  Prior Effects: {gate.prior_effects} (gate: {gate.prior_gate})")

    # =========================================================================
    # STEP 7: Persist All Private Artifacts
    # =========================================================================
    print("\n--- Step 7: Export Private Stage-1 Artifacts ---")
    private_home = Path(settings.private_home)
    runs_dir = private_home / "runs" / "stage1"
    audits_dir = private_home / "audits"
    runs_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    results_data = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "n_documents": len(docs),
        "n_instrumented_atoms": len(atom_records_meta),
        "n_valid_causal_records": len(causal_records),
        "failed_edits_count": len(failed_edits),
        "decomposition": decomp.to_dict(),
        "prior_effects": prior_effects,
        "gate_proceed": gate.proceed,
        "gate_reason": gate.reason,
        "spend_usd": round(total_spend, 4),
        "calls_executed": calls_executed,
        "cache_hits": cache_hits,
    }

    gate_data = {
        "event": "STAGE1_MECHANISM_GATE",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "reconstruction_contribution": decomp.r_bar_zero,
        "prior_effects": prior_effects,
        "reconstruction_gate": 0.10,
        "prior_gate": 0.10,
        "eligible_prior_classes": list(eligible_prior_classes),
        "proceed": gate.proceed,
        "verdict": "STAGE1_GATE_PASS" if gate.proceed else "STAGE1_GATE_FAIL",
        "reason": gate.reason,
    }

    cost_ledger_data = {
        "event": "STAGE1_COST_LEDGER",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "total_spend_usd": round(total_spend, 4),
        "ceiling_usd": STAGE1_INCREMENTAL_CEILING_USD,
        "ceiling_respected": total_spend <= STAGE1_INCREMENTAL_CEILING_USD,
        "calls_executed": calls_executed,
        "cache_hits": cache_hits,
        "calls_summary": {
            "relay": len(docs),
            "receiver_natural": len(atom_records_meta) * M_STAR,
            "receiver_counterfactual": len([a for a in atom_records_meta if a["edit_valid"]])
            * M_STAR,
            "prior_probe": len(prior_tasks),
        },
    }

    run_manifest_data = {
        "event": "STAGE1_RUN_MANIFEST",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "stage1_manifest_hash": manifest_hash,
        "model": PINNED_MODEL,
        "receiver_regime": "S_CONFIRMED",
        "m_star": M_STAR,
        "m_prior": M_PRIOR,
        "k_focal": K_FOCAL,
        "relay_budget_tokens": settings.relay_budget_tokens,
        "verdict": gate_data["verdict"],
    }

    # Save to runs/stage1 and audits
    for path, data in [
        (runs_dir / "STAGE1_RESULTS.json", results_data),
        (audits_dir / "STAGE1_GATE.json", gate_data),
        (runs_dir / "STAGE1_COST_LEDGER.json", cost_ledger_data),
        (runs_dir / "STAGE1_RUN_MANIFEST.json", run_manifest_data),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Saved: {path}")

    print("\n=======================================================")
    print(f"STAGE 1 COMPLETE: {gate_data['verdict']}")
    print(f"Total Provider Spend: ${total_spend:.4f} / ${STAGE1_INCREMENTAL_CEILING_USD:.2f}")
    print("=======================================================\n")
    return 0 if gate.proceed else 2


if __name__ == "__main__":
    sys.exit(main())
