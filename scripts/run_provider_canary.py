#!/usr/bin/env python3
"""G2 Synthetic Provider Canary Runner.

Executes the frozen 11-call synthetic canary matrix across candidate models:
  - 1 identity probe
  - 2 relay_shape probes (budget B=300, synthetic enterprise description)
  - 8 receiver_variability probes (byte-identical request, slot schema)

Tracks latency, fingerprints, token usage, reasoning tokens, byte-identical
repeat rates, and canonical slot agreement rates while enforcing spend ceilings.
Zero real SEC or study corpus data is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from handoff_fidelity.providers.adapters import DeepSeekAdapter, OpenAIAdapter
from handoff_fidelity.providers.protocol import GenerationRequest

# Pricing per million tokens (input / output)
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-6-astra": (2.50, 10.00),
    "gpt-5.6-sol": (1.50, 6.00),
    "gpt-5.6-terra": (0.50, 2.00),
    "deepseek-v4-pro": (0.27, 1.10),
}

CANARY_TOTAL_SPEND_LIMIT_USD = 10.00
PER_FAMILY_STOP_LOSS_USD = 3.00

SYNTHETIC_RELAY_SOURCE = """
Global Logistics Technologies Inc. (GLT) operates automated supply chain management software,
freight routing algorithms, and multi-modal fulfillment centers across 14 European and North
American freight corridors. In fiscal year 2024, GLT processed 48.6 million parcel transactions,
representing a 16.4% year-over-year increase compared to 41.7 million in fiscal 2023. Total
consolidated revenues were $1,842.5 million, up from $1,610.2 million in the prior year.

Operating expenses expanded by 11.2% to $1,420.8 million, primarily driven by investments in
cloud infrastructure, autonomous sorting robotics in the Frankfurt and Chicago hubs, and elevated
fleet electrification capital expenditures totaling $135.4 million. Consolidated adjusted EBITDA
stood at $421.7 million, yielding an EBITDA margin of 22.9%, expanding 180 basis points over 2023.

Free cash flow generation reached $288.3 million for the full fiscal year. Net debt decreased
to $310.5 million, providing a net leverage ratio of 0.74x EBITDA. Operating activities generated
$394.8 million in cash flow, supported by positive working capital developments and improved DSO
(days sales outstanding) decreasing from 48 days to 43 days.

In European road freight, market share expanded to 8.2%, up 60 basis points. North American freight
brokerage operations achieved gross margins of 14.1%. Capital allocation priorities for fiscal 2025
include $150 million dedicated to autonomous vehicle pilot integration, $80 million in share
repurchases under the existing board authorization, and ongoing quarterly dividend distributions
of $0.22 per common share. Headcount at year-end was 6,420 full-time equivalents.
"""

SYNTHETIC_RECEIVER_PROMPT = """You are an information extraction system. Extract the factual financial metrics from the message below into strict JSON format with exactly the keys: "company", "quarter", "revenue_millions", "net_margin_pct", "operating_cash_flow_millions".

Message:
Nexus Semiconductor Corporation reported financial results for Q2 2025. Total revenue was $850.4 million, reflecting 14.5% year-over-year growth. Net profit margin reached 22.8%, and operating cash flow totaled $215.0 million.

Respond with valid JSON only, without markdown formatting or code fences."""


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


def calculate_cost(model: str, in_tok: int, out_tok: int) -> float:
    rates = PRICING_PER_MTOK.get(model, (2.0, 8.0))
    in_cost = (max(0, in_tok) / 1_000_000.0) * rates[0]
    out_cost = (max(0, out_tok) / 1_000_000.0) * rates[1]
    return in_cost + out_cost


def run_canary_for_model(
    provider_name: str,
    model_name: str,
    runs_dir: Path,
    cumulative_spend: float,
) -> dict[str, Any]:
    print("\n==========================================")
    print(f"Running G2 Canary for: {model_name} ({provider_name})")
    print("==========================================")

    if provider_name == "openai":
        adapter = OpenAIAdapter(model=model_name, allow_network=True)
    elif provider_name == "deepseek":
        adapter = DeepSeekAdapter(model=model_name, allow_network=True)
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

    traces: list[dict[str, Any]] = []
    family_spend = 0.0

    # Probe 1: Identity (1 call)
    print("Executing Probe 1: identity (1 call)...")
    req = GenerationRequest(
        prompt="You are an automated identity test. Output exactly: OK",
        max_output_tokens=10,
        model=model_name,
        temperature=0.0,
        seed=0,
    )
    t0 = time.perf_counter()
    resp = adapter.generate(req)
    t_elapsed = time.perf_counter() - t0

    cost = calculate_cost(model_name, resp.input_tokens, resp.output_tokens)
    family_spend += cost
    cumulative_spend += cost

    trace_ident = {
        "probe": "identity",
        "call_index": 1,
        "model": model_name,
        "returned_model": resp.returned_model,
        "system_fingerprint": resp.system_fingerprint,
        "provider_request_id": resp.provider_request_id,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "reasoning_tokens": resp.reasoning_tokens,
        "latency_s": resp.latency_s or t_elapsed,
        "finish_reason": resp.finish_reason,
        "text": resp.text,
        "cost_usd": cost,
    }
    traces.append(trace_ident)
    print(
        f"  -> Returned: {resp.returned_model}, latency: {trace_ident['latency_s']:.2f}s, tokens: in={resp.input_tokens}/out={resp.output_tokens}/reasoning={resp.reasoning_tokens}"
    )

    # Probe 2: Relay Shape (2 calls)
    print("Executing Probe 2: relay_shape (2 calls, B=300)...")
    relay_prompt = (
        "You are an information relay. Condense the following company overview to under 300 tokens, "
        f"preserving key quantitative and operational facts:\n\n{SYNTHETIC_RELAY_SOURCE}"
    )
    for c_idx in range(1, 3):
        if family_spend > PER_FAMILY_STOP_LOSS_USD:
            raise RuntimeError(
                f"Family spend limit exceeded: ${family_spend:.4f} > ${PER_FAMILY_STOP_LOSS_USD}"
            )
        if cumulative_spend > CANARY_TOTAL_SPEND_LIMIT_USD:
            raise RuntimeError(
                f"Total canary spend limit exceeded: ${cumulative_spend:.4f} > ${CANARY_TOTAL_SPEND_LIMIT_USD}"
            )

        req = GenerationRequest(
            prompt=relay_prompt,
            max_output_tokens=300,
            model=model_name,
            temperature=0.0,
            seed=c_idx,
        )
        t0 = time.perf_counter()
        resp = adapter.generate(req)
        t_elapsed = time.perf_counter() - t0

        cost = calculate_cost(model_name, resp.input_tokens, resp.output_tokens)
        family_spend += cost
        cumulative_spend += cost

        trace_relay = {
            "probe": "relay_shape",
            "call_index": c_idx,
            "model": model_name,
            "returned_model": resp.returned_model,
            "system_fingerprint": resp.system_fingerprint,
            "provider_request_id": resp.provider_request_id,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "reasoning_tokens": resp.reasoning_tokens,
            "latency_s": resp.latency_s or t_elapsed,
            "finish_reason": resp.finish_reason,
            "text": resp.text,
            "text_sha256": hashlib.sha256(resp.text.encode("utf-8")).hexdigest(),
            "cost_usd": cost,
        }
        traces.append(trace_relay)
        print(
            f"  Call {c_idx}: tokens: in={resp.input_tokens}/out={resp.output_tokens}/reasoning={resp.reasoning_tokens}, latency: {trace_relay['latency_s']:.2f}s, cost: ${cost:.4f}"
        )

    # Probe 3: Receiver Variability (8 calls)
    print("Executing Probe 3: receiver_variability (8 calls, byte-identical requests)...")
    receiver_traces: list[dict[str, Any]] = []
    receiver_outputs: list[str] = []
    receiver_hashes: list[str] = []
    parsed_slots_list: list[dict[str, Any]] = []

    for c_idx in range(1, 9):
        if family_spend > PER_FAMILY_STOP_LOSS_USD:
            raise RuntimeError(
                f"Family spend limit exceeded: ${family_spend:.4f} > ${PER_FAMILY_STOP_LOSS_USD}"
            )
        if cumulative_spend > CANARY_TOTAL_SPEND_LIMIT_USD:
            raise RuntimeError(
                f"Total canary spend limit exceeded: ${cumulative_spend:.4f} > ${CANARY_TOTAL_SPEND_LIMIT_USD}"
            )

        req = GenerationRequest(
            prompt=SYNTHETIC_RECEIVER_PROMPT,
            max_output_tokens=150,
            model=model_name,
            temperature=0.0,
            seed=0,
        )
        t0 = time.perf_counter()
        resp = adapter.generate(req)
        t_elapsed = time.perf_counter() - t0

        cost = calculate_cost(model_name, resp.input_tokens, resp.output_tokens)
        family_spend += cost
        cumulative_spend += cost

        text = resp.text.strip()
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        receiver_outputs.append(text)
        receiver_hashes.append(h)

        # Parse slots
        parsed = {}
        try:
            parsed = json.loads(text)
        except Exception:
            # Fallback json extraction if wrapped in code block
            cleaned = text.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = {"raw": text}
        parsed_slots_list.append(parsed)

        trace_rec = {
            "probe": "receiver_variability",
            "call_index": c_idx,
            "model": model_name,
            "returned_model": resp.returned_model,
            "system_fingerprint": resp.system_fingerprint,
            "provider_request_id": resp.provider_request_id,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "reasoning_tokens": resp.reasoning_tokens,
            "latency_s": resp.latency_s or t_elapsed,
            "finish_reason": resp.finish_reason,
            "text": text,
            "text_sha256": h,
            "parsed_slots": parsed,
            "cost_usd": cost,
        }
        receiver_traces.append(trace_rec)
        traces.append(trace_rec)
        print(
            f"  Repeat {c_idx}: hash={h[:8]}..., tokens: in={resp.input_tokens}/out={resp.output_tokens}, latency: {trace_rec['latency_s']:.2f}s"
        )

    # Analyze receiver stability
    # 1. Byte-identical repeat rate
    first_hash = receiver_hashes[0]
    byte_identical_count = sum(1 for h in receiver_hashes if h == first_hash)
    byte_identical_rate = byte_identical_count / len(receiver_hashes)

    # 2. Canonical slot agreement rate (normalized JSON equality)
    # Convert each parsed dict to canonical json string
    canonical_strs = [json.dumps(p, sort_keys=True) for p in parsed_slots_list]
    from collections import Counter

    mode_str, mode_count = Counter(canonical_strs).most_common(1)[0]
    canonical_agreement_rate = mode_count / len(canonical_strs)

    # Latency and token stats
    rec_latencies = [t["latency_s"] for t in receiver_traces]
    avg_rec_latency = sum(rec_latencies) / len(rec_latencies)

    relay_traces = [t for t in traces if t["probe"] == "relay_shape"]
    avg_relay_cost = (
        sum(t["cost_usd"] for t in relay_traces) / len(relay_traces) if relay_traces else 0.0
    )

    summary = {
        "provider": provider_name,
        "model": model_name,
        "total_calls": len(traces),
        "total_spend_usd": family_spend,
        "returned_model": traces[0]["returned_model"],
        "system_fingerprints": sorted(
            {t["system_fingerprint"] for t in traces if t["system_fingerprint"]}
        ),
        "byte_identical_repeat_rate": byte_identical_rate,
        "canonical_agreement_rate": canonical_agreement_rate,
        "mean_receiver_latency_s": avg_rec_latency,
        "avg_relay_cost_usd": avg_relay_cost,
        "traces": traces,
    }

    # Save to json
    model_safe_name = model_name.replace("/", "_")
    out_file = runs_dir / f"{model_safe_name}_canary.json"
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Model {model_name} Canary Complete. Spend: ${family_spend:.4f}. Saved: {out_file}")
    print(
        f"Canonical Agreement: {canonical_agreement_rate * 100:.1f}%, Byte-identical: {byte_identical_rate * 100:.1f}%\n"
    )

    return summary


def main() -> int:
    load_env_safe()

    runs_dir = Path("runs/canary")
    runs_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        ("openai", "gpt-6-astra"),
        ("openai", "gpt-5.6-sol"),
        ("openai", "gpt-5.6-terra"),
        ("deepseek", "deepseek-v4-pro"),
    ]

    all_summaries: list[dict[str, Any]] = []
    total_spend = 0.0

    for provider, model in candidates:
        summary = run_canary_for_model(provider, model, runs_dir, total_spend)
        total_spend += summary["total_spend_usd"]
        all_summaries.append(summary)

    # Save grand summary
    summary_file = runs_dir / "summary.json"
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates_count": len(candidates),
        "total_calls": sum(s["total_calls"] for s in all_summaries),
        "total_spend_usd": total_spend,
        "spend_limit_usd": CANARY_TOTAL_SPEND_LIMIT_USD,
        "results": [
            {
                "provider": s["provider"],
                "model": s["model"],
                "returned_model": s["returned_model"],
                "fingerprints": s["system_fingerprints"],
                "canonical_agreement_rate": s["canonical_agreement_rate"],
                "byte_identical_repeat_rate": s["byte_identical_repeat_rate"],
                "mean_receiver_latency_s": s["mean_receiver_latency_s"],
                "avg_relay_cost_usd": s["avg_relay_cost_usd"],
                "spend_usd": s["total_spend_usd"],
            }
            for s in all_summaries
        ],
    }
    summary_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print("\n=======================================================")
    print("CANARY COMPLETE: 44 calls across 4 models.")
    print(f"Total Spend: ${total_spend:.4f} (Limit: ${CANARY_TOTAL_SPEND_LIMIT_USD})")
    print(f"Summary written to: {summary_file}")
    print("=======================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
