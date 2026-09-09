#!/usr/bin/env python3
"""Experiment B Execution Runner — Matched Prior-Access Contrast on Stage 1.

Executes the frozen matched-skeleton contrast H_{-z} under low-cost primary model
gpt-5.1-2025-11-13 (reasoning_effort=none, m*=2) across all candidate tuples in the 100 STAGE1 documents:
  - Matched skeleton construction: identical slots present/absent, focal slot <<OMITTED>> in both arms
  - Non-focal value mapping: natural vs frozen randomized supports (screened entity names, scope, period, numeric)
  - Strict mechanical assertion of matching (slot structure, omission, content difference)
  - Receiver execution under m*=2 independent stochastic draws
  - Exact recovery scoring via normalized exact match
  - Matched prior-access effect estimation: Delta_R_prior_matched = E[Y(H_nat) - Y(H_blk)]
  - Document-clustered bootstrap uncertainty (10,000 replicates)
  - Hard spend ceiling enforcement ($2.00 USD)
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

import numpy as np

root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from handoff_fidelity.atomizer.rules import atomize  # noqa: E402
from handoff_fidelity.atomizer.verify import filter_eligible  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.interventions.skeleton import (  # noqa: E402
    MIN_POPULATED_ROLES,
    OMITTED,
    assert_matched,
    build_candidate_tuples,
    natural_mapping,
    render_skeleton,
    slot_structure,
)
from handoff_fidelity.matcher.match import recovered  # noqa: E402
from handoff_fidelity.models import AtomRole  # noqa: E402
from handoff_fidelity.providers.adapters import OpenAIAdapter  # noqa: E402
from handoff_fidelity.providers.protocol import GenerationRequest  # noqa: E402
from handoff_fidelity.receiver.prompt import build_receiver_prompt  # noqa: E402
from handoff_fidelity.sampling.design import all_inclusion_probabilities, select_focal  # noqa: E402
from handoff_fidelity.seeds import derive_seed, rng_for  # noqa: E402

PINNED_MODEL = "gpt-5.1-2025-11-13"
EXPERIMENT_B_CEILING_USD = 2.00
M_STAR = 2

PRICING_GPT51 = {
    "input_per_million": 1.25,
    "output_per_million": 10.00,
}


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


def calculate_cost_gpt51(input_tokens: int, output_tokens: int) -> float:
    cost_in = (input_tokens / 1_000_000.0) * PRICING_GPT51["input_per_million"]
    cost_out = (output_tokens / 1_000_000.0) * PRICING_GPT51["output_per_million"]
    return cost_in + cost_out


class DiskCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def put(self, key: str, record: dict[str, Any]) -> None:
        path = self.cache_dir / f"{key}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)


def main() -> int:
    load_env_safe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-workers", type=int, default=15)
    args = parser.parse_args()

    settings = load_settings()
    manifest_path = settings.path("source_manifests", "STAGE1.csv")
    assert manifest_path.exists(), f"STAGE1 manifest not found at {manifest_path}"

    docs = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        docs.extend(reader)
    print(f"Loaded {len(docs)} Stage-1 documents.")

    raw_private_home = os.environ.get("HANDOFF_PRIVATE_HOME")
    if not raw_private_home:
        candidate = Path.home() / ".handoff-fidelity"
        raw_private_home = str(candidate) if candidate.exists() else str(Path.cwd())
    private_home = Path(raw_private_home)
    entity_support_path = private_home / "audits" / "ENTITY_SUPPORT_SCREENING.json"
    with open(entity_support_path, encoding="utf-8") as f:
        ent_data = json.load(f)
    entity_support = [item["fictitious_name"] for item in ent_data["screened_entities"]]
    print(f"Loaded {len(entity_support)} screened fictitious entities.")

    scope_support_path = root_dir / "protocol" / "randomisation" / "scope_support.txt"
    scope_support = [
        line.strip()
        for line in scope_support_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    period_annual_path = root_dir / "protocol" / "randomisation" / "period_annual_support.txt"
    period_annual_support = [
        line.strip()
        for line in period_annual_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    period_quarter_path = root_dir / "protocol" / "randomisation" / "period_quarter_support.txt"
    period_quarter_support = [
        line.strip()
        for line in period_quarter_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    # Cache directory
    cache_dir = private_home / "runs" / "stage1_restart_gpt51" / "cache" / "experiment_b"
    cache = DiskCache(cache_dir)

    adapter = OpenAIAdapter(model=PINNED_MODEL, allow_network=True)

    # Collect all candidate tuples across documents
    all_tuples = []
    eligible_classes = ("scope", "period", "numeric")
    work_tasks = []

    for row in docs:
        doc_id = row["document_id"]
        frame_file = settings.path("data", "source_pool", "frames", f"{doc_id}.txt")
        frame_text = frame_file.read_text(encoding="utf-8")
        atoms = atomize(doc_id, frame_text)
        tuples = build_candidate_tuples(atoms, min_roles=MIN_POPULATED_ROLES)

        rep = filter_eligible(atoms, frame_text, require_human_verification=False)
        rng = rng_for(settings.master_seed, "stage1", doc_id)
        focals = select_focal(rep.eligible, rng=rng, k=3)
        focal_ids = {f.atom_id for f in focals}
        pis = all_inclusion_probabilities(rep.eligible, k=3)

        for tup in tuples:
            all_tuples.append((doc_id, tup, focal_ids))
            for focal_role in tup.populated_roles:
                focal_atom = tup.slots[focal_role]
                is_focal_sampled = focal_atom.atom_id in focal_ids
                pi = pis.get(focal_atom.atom_id, 0.0)
                numeric_subtype = (
                    ("pct" if "%" in focal_atom.canonical_value else "currency_or_other")
                    if focal_role == AtomRole.NUMERIC
                    else None
                )
                is_frozen_numeric_compliant = (
                    focal_role != AtomRole.NUMERIC or "%" in focal_atom.canonical_value
                )

                # Deterministic RNG for this slot intervention
                seed_gen = rng_for(
                    settings.master_seed, "experiment_b", doc_id, tup.slot_id, focal_role.value
                )

                # Natural render
                nat_map = natural_mapping(tup)
                nat_render = render_skeleton(tup, focal_role, nat_map)

                # Blocked render
                blk_map = dict(nat_map)
                for r in tup.populated_roles:
                    if r == focal_role:
                        continue
                    nat_val = nat_map[r]
                    if r == AtomRole.ENTITY:
                        cands = [e for e in entity_support if e != nat_val]
                        blk_map[r] = seed_gen.choice(cands)
                    elif r == AtomRole.SCOPE:
                        cands = [s for s in scope_support if s != nat_val]
                        blk_map[r] = seed_gen.choice(cands)
                    elif r == AtomRole.PERIOD:
                        supp = period_quarter_support if "Q" in nat_val else period_annual_support
                        cands = [p for p in supp if p != nat_val]
                        blk_map[r] = seed_gen.choice(cands)
                    elif r == AtomRole.NUMERIC:
                        if "%" in nat_val:
                            val = round(seed_gen.uniform(5.0, 95.0), 2)
                            blk_map[r] = f"{val}%"
                        else:
                            unit = nat_val.split("|")[-1] if "|" in nat_val else ""
                            num = seed_gen.randint(10, 500)
                            blk_map[r] = f"${num}|{unit}" if unit else f"${num}"
                    elif r == AtomRole.PROVENANCE:
                        cands = [f"Note {i}" for i in range(1, 25)] + [
                            "Item 1",
                            "Item 7",
                            "Exhibit 10.1",
                        ]
                        cands = [c for c in cands if c != nat_val]
                        blk_map[r] = seed_gen.choice(cands)

                blk_render = render_skeleton(tup, focal_role, blk_map)

                # Mechanical assertions of matching
                assert_matched(nat_render, blk_render)
                assert slot_structure(nat_render) == slot_structure(blk_render)
                assert nat_render != blk_render
                assert nat_render.count(OMITTED) == 1 and blk_render.count(OMITTED) == 1

                nat_hash = hashlib.sha256(nat_render.encode()).hexdigest()
                blk_hash = hashlib.sha256(blk_render.encode()).hexdigest()

                for arm, render, render_hash in (
                    ("natural", nat_render, nat_hash),
                    ("blocked", blk_render, blk_hash),
                ):
                    prompt = build_receiver_prompt(
                        message=render,
                        role=focal_role,
                        subject=doc_id,
                        attribute=f"the {focal_role.value} value",
                    )
                    for rep in range(1, M_STAR + 1):
                        task_key = hashlib.sha256(
                            f"exp_b:{doc_id}:{tup.slot_id}:{focal_role.value}:{arm}:rep{rep}:{render_hash}".encode()
                        ).hexdigest()
                        seed = (
                            derive_seed(
                                settings.master_seed,
                                "experiment_b",
                                doc_id,
                                tup.slot_id,
                                focal_role.value,
                                arm,
                                f"rep{rep}",
                            )
                            % 9223372036854775807
                        )
                        work_tasks.append(
                            {
                                "task_key": task_key,
                                "doc_id": doc_id,
                                "slot_id": tup.slot_id,
                                "atom_id": focal_atom.atom_id,
                                "role": focal_role.value,
                                "is_eligible_class": focal_role.value in eligible_classes,
                                "is_focal_sampled": is_focal_sampled,
                                "canonical_value": focal_atom.canonical_value,
                                "pi": pi,
                                "numeric_subtype": numeric_subtype,
                                "is_frozen_numeric_compliant": is_frozen_numeric_compliant,
                                "arm": arm,
                                "rep": rep,
                                "seed": seed,
                                "prompt": prompt,
                                "render_hash": render_hash,
                            }
                        )

    print(f"Total candidate tuples: {len(all_tuples)}")
    print(f"Total Experiment-B tasks to execute: {len(work_tasks)} across all roles")
    eligible_tasks = [t for t in work_tasks if t["is_eligible_class"]]
    print(f"Eligible-class tasks (scope, period, numeric): {len(eligible_tasks)}")

    # Execute calls
    total_spend = 0.0
    calls_executed = 0
    cache_hits = 0
    t0 = time.time()

    def execute_task(task: dict[str, Any]) -> dict[str, Any]:
        nonlocal total_spend, calls_executed, cache_hits
        cached = cache.get(task["task_key"])
        if cached is not None:
            cache_hits += 1
            raw_text = cached["raw_text"]
            is_rec = int(
                recovered(raw_text, canonical_value=task["canonical_value"], role=task["role"])
            )
            return {
                **task,
                "raw_text": raw_text,
                "recovered": is_rec,
                "cost_usd": 0.0,
                "cached": True,
            }

        req = GenerationRequest(
            prompt=task["prompt"],
            model=PINNED_MODEL,
            max_output_tokens=512,
            temperature=0.0,
            top_p=1.0,
            seed=task["seed"],
            metadata={"reasoning_effort": "none"},
        )
        resp = adapter.generate(req)
        cost = calculate_cost_gpt51(resp.input_tokens, resp.output_tokens)
        raw_text = resp.text.strip()
        is_rec = int(
            recovered(raw_text, canonical_value=task["canonical_value"], role=task["role"])
        )

        rec = {
            "task_key": task["task_key"],
            "doc_id": task["doc_id"],
            "slot_id": task["slot_id"],
            "atom_id": task["atom_id"],
            "role": task["role"],
            "arm": task["arm"],
            "rep": task["rep"],
            "raw_text": raw_text,
            "canonical_value": task["canonical_value"],
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cost_usd": cost,
            "returned_model": PINNED_MODEL,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }
        cache.put(task["task_key"], rec)
        total_spend += cost
        calls_executed += 1
        if total_spend > EXPERIMENT_B_CEILING_USD:
            raise RuntimeError(
                f"STAGE1_EXPERIMENT_B_COMPLETION_CEILING_USD exceeded: ${total_spend:.4f} > ${EXPERIMENT_B_CEILING_USD}"
            )
        return {
            **task,
            "raw_text": raw_text,
            "recovered": is_rec,
            "cost_usd": cost,
            "cached": False,
        }

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futs = [executor.submit(execute_task, t) for t in work_tasks]
        for done_count, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            results.append(res)
            if done_count % 20 == 0 or done_count == len(work_tasks):
                print(
                    f"  Progress: {done_count}/{len(work_tasks)} calls completed (${total_spend:.4f}, {time.time() - t0:.1f}s)",
                    flush=True,
                )

    print(f"\nExperiment B executed successfully in {time.time() - t0:.1f}s!")
    print(
        f"Calls executed: {calls_executed}, Cache hits: {cache_hits}, Total spend: ${total_spend:.4f} USD (Ceiling: ${EXPERIMENT_B_CEILING_USD:.2f} USD)"
    )

    # Aggregate by slot_id and role
    # Each slot has natural (rep 1, 2) and blocked (rep 1, 2)
    slot_records: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "natural_reps": [],
            "blocked_reps": [],
            "doc_id": "",
            "atom_id": "",
            "is_focal_sampled": False,
            "canonical_value": "",
        }
    )

    for r in results:
        key = (r["slot_id"], r["role"])
        rec = slot_records[key]
        rec["doc_id"] = r["doc_id"]
        rec["atom_id"] = r["atom_id"]
        rec["is_focal_sampled"] = r["is_focal_sampled"]
        rec["canonical_value"] = r["canonical_value"]
        rec["pi"] = r.get("pi", 0.0)
        rec["numeric_subtype"] = r.get("numeric_subtype")
        rec["is_frozen_numeric_compliant"] = r.get("is_frozen_numeric_compliant", True)
        if r["arm"] == "natural":
            rec["natural_reps"].append(r["recovered"])
        else:
            rec["blocked_reps"].append(r["recovered"])

    # Compute matched contrast per slot
    # Delta_R_slot = mean(natural_reps) - mean(blocked_reps)
    paired_slots = []
    for (slot_id, role), data in slot_records.items():
        y_nat = statistics.mean(data["natural_reps"])
        y_blk = statistics.mean(data["blocked_reps"])
        diff = y_nat - y_blk
        paired_slots.append(
            {
                "doc_id": data["doc_id"],
                "slot_id": slot_id,
                "atom_id": data["atom_id"],
                "role": role,
                "is_focal_sampled": data["is_focal_sampled"],
                "canonical_value": data["canonical_value"],
                "pi": data["pi"],
                "numeric_subtype": data["numeric_subtype"],
                "is_frozen_numeric_compliant": data["is_frozen_numeric_compliant"],
                "y_nat": y_nat,
                "y_blk": y_blk,
                "paired_diff": diff,
            }
        )

    rng_boot = np.random.default_rng(20260904)

    # 1. Canonical Estimation (Frozen Stage-1 Focal Atoms, Frozen Support Compliant)
    canonical_by_role_summary: dict[str, Any] = {}
    for role_name in ("scope", "period", "numeric"):
        focal_slots_role = [
            s
            for s in paired_slots
            if s["role"] == role_name and s["is_focal_sampled"] and s["is_frozen_numeric_compliant"]
        ]
        if not focal_slots_role:
            canonical_by_role_summary[role_name] = {
                "status": "NOT_ESTIMABLE_NO_ELIGIBLE_MATCHED_UNITS",
                "n_slots": 0,
                "n_docs": 0,
                "r_minus_nat": None,
                "r_minus_blk": None,
                "hajek_estimate": None,
                "unweighted_diagnostic_mean": None,
                "delta_r_prior_matched": None,
                "ci_95": None,
                "clears_threshold": False,
            }
            continue

        n_slots = len(focal_slots_role)
        docs_role = sorted({s["doc_id"] for s in focal_slots_role})
        n_docs = len(docs_role)

        r_nat = statistics.mean(s["y_nat"] for s in focal_slots_role)
        r_blk = statistics.mean(s["y_blk"] for s in focal_slots_role)

        # Hájek weighted estimator
        weights = [1.0 / s["pi"] for s in focal_slots_role]
        w_sum = sum(weights)
        hajek_est = (
            sum(w * s["paired_diff"] for w, s in zip(weights, focal_slots_role, strict=True))
            / w_sum
        )
        unweighted_mean = statistics.mean(s["paired_diff"] for s in focal_slots_role)

        # Document-clustered bootstrap (10,000 resamples)
        boot_diffs = []
        doc_map = defaultdict(list)
        for s in focal_slots_role:
            doc_map[s["doc_id"]].append(s)

        doc_keys = list(doc_map.keys())
        for _ in range(10000):
            sampled_docs = rng_boot.choice(doc_keys, size=len(doc_keys), replace=True)
            resampled_slots = []
            for d in sampled_docs:
                resampled_slots.extend(doc_map[d])
            w_boot = [1.0 / s["pi"] for s in resampled_slots]
            boot_diffs.append(
                sum(w * s["paired_diff"] for w, s in zip(w_boot, resampled_slots, strict=True))
                / sum(w_boot)
            )

        ci_low = float(np.percentile(boot_diffs, 2.5))
        ci_high = float(np.percentile(boot_diffs, 97.5))

        canonical_by_role_summary[role_name] = {
            "status": "ESTIMABLE",
            "n_slots": n_slots,
            "n_docs": n_docs,
            "r_minus_nat": round(r_nat, 4),
            "r_minus_blk": round(r_blk, 4),
            "delta_r_prior_matched": round(hajek_est, 4),
            "unweighted_diagnostic_mean": round(unweighted_mean, 4),
            "ci_95": [round(ci_low, 4), round(ci_high, 4)],
            "clears_threshold": hajek_est >= 0.10,
        }

    # 2. Exploratory full-tuple sensitivity (all 27 slots)
    exploratory_full_tuple_sensitivity = {}
    for role_name in ("scope", "period", "numeric", "entity", "provenance"):
        slots_role = [s for s in paired_slots if s["role"] == role_name]
        if not slots_role:
            exploratory_full_tuple_sensitivity[role_name] = {
                "n_slots": 0,
                "n_docs": 0,
                "r_minus_nat": None,
                "r_minus_blk": None,
                "delta_r_prior_matched": None,
                "ci_95": None,
            }
            continue
        n_slots = len(slots_role)
        docs_role = sorted({s["doc_id"] for s in slots_role})
        r_nat = statistics.mean(s["y_nat"] for s in slots_role)
        r_blk = statistics.mean(s["y_blk"] for s in slots_role)
        delta = r_nat - r_blk
        doc_map_all = defaultdict(list)
        for s in slots_role:
            doc_map_all[s["doc_id"]].append(s["paired_diff"])
        doc_keys_all = list(doc_map_all.keys())
        boot_diffs_all = []
        for _ in range(10000):
            sampled_docs = rng_boot.choice(doc_keys_all, size=len(doc_keys_all), replace=True)
            resampled_vals = []
            for d in sampled_docs:
                resampled_vals.extend(doc_map_all[d])
            boot_diffs_all.append(statistics.mean(resampled_vals))
        ci_low = float(np.percentile(boot_diffs_all, 2.5))
        ci_high = float(np.percentile(boot_diffs_all, 97.5))
        exploratory_full_tuple_sensitivity[role_name] = {
            "n_slots": n_slots,
            "n_docs": len(docs_role),
            "r_minus_nat": round(r_nat, 4),
            "r_minus_blk": round(r_blk, 4),
            "delta_r_prior_matched": round(delta, 4),
            "ci_95": [round(ci_low, 4), round(ci_high, 4)],
        }

    print("\n================ CANONICAL EXPERIMENT B RESULTS ================")
    for r, sm in sorted(canonical_by_role_summary.items()):
        print(
            f"Role: {r:12s} | Status={sm['status']} | N_slots={sm['n_slots']} | Delta_matched={sm['delta_r_prior_matched']} | 95% CI={sm['ci_95']} | Clears 0.10: {sm['clears_threshold']}"
        )
    print("================================================================\n")

    # Persist outputs
    effective_spend = total_spend
    if effective_spend == 0.0:
        effective_spend = sum(
            json.loads(f.read_text(encoding="utf-8")).get("cost_usd", 0.0)
            for f in cache_dir.glob("*.json")
        )

    out_data = {
        "event": "EXPERIMENT_B_RESULTS",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": PINNED_MODEL,
        "m_star": M_STAR,
        "total_calls": len(work_tasks),
        "total_spend_usd": round(effective_spend, 4),
        "ceiling_usd": EXPERIMENT_B_CEILING_USD,
        "ceiling_respected": effective_spend <= EXPERIMENT_B_CEILING_USD,
        "manipulation_check": {
            "quantity": "Tbar_nat - Tbar_blk",
            "status": "NOT_EXECUTED",
            "note": "Relay manipulation check not executed; no randomized-twin relay calls run in Stage 1.",
        },
        "canonical_by_role_summary": canonical_by_role_summary,
        "by_role_summary": canonical_by_role_summary,
        "exploratory_full_tuple_sensitivity": exploratory_full_tuple_sensitivity,
        "slots_detail": paired_slots,
    }

    runs_dir = private_home / "runs" / "stage1_restart_gpt51"
    audits_dir = private_home / "audits"

    for p in (runs_dir / "EXPERIMENT_B_RESULTS.json", audits_dir / "EXPERIMENT_B_RESULTS.json"):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        print(f"Saved: {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
