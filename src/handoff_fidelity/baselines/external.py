"""External comparator adapters.

Every adapter here ships as ``NOT_READY``. That is a deliberate, load-bearing
choice: a speculative reimplementation labelled with a published method's name
would misrepresent the benchmark, and the reproduction gate exists precisely to
prevent that. Calling ``compress`` on a NOT_READY adapter raises.

To bring one online:

  1. clone the OFFICIAL repository into the private workspace under
     ``third_party/<method>/`` (never vendored into this repository unless the
     licence explicitly permits it and vendoring is necessary);
  2. pin the exact commit and checkpoint revision in ``configs/baselines.yaml``;
  3. create an isolated environment if its dependencies conflict with the
     coordinating environment -- degrade the isolated env, never the main one;
  4. implement ``_compress`` to call the official entry point;
  5. pass the reproduction gate on a public/native task.

Only then may ``status`` be set to READY, and only in the private registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import AdapterNotReady, AdapterStatus, BaseCompressor, BenchmarkRole


@dataclass(slots=True)
class ExternalAdapter(BaseCompressor):
    """Base class for a pinned external method."""

    name: str = "external"
    revision: str = "UNPINNED"
    status: AdapterStatus = AdapterStatus.NOT_READY
    role: BenchmarkRole = BenchmarkRole.PRIMARY_CAUSAL
    official_repository: str = ""
    entry_point: str = ""
    integration_notes: str = ""
    third_party_root: Any = None

    def _compress(self, source_text, downstream_task, token_budget, config):
        raise AdapterNotReady(
            f"{self.name}: no official implementation is bound. "
            f"Expected upstream: {self.official_repository or 'unresolved'}. "
            f"{self.integration_notes}"
        )


def provence() -> ExternalAdapter:
    return ExternalAdapter(
        name="provence",
        official_repository="https://github.com/naver/bergen",
        entry_point="Provence context pruner (sequence-labelling); official checkpoint on the Hub",
        integration_notes=(
            "Provence prunes context by sentence-level labelling and emits TEXT, so "
            "atom presence is auditable by the same frozen matcher. Its native "
            "pruning threshold must be calibrated on development data to satisfy the "
            "common hard token budget."
        ),
        role=BenchmarkRole.PRIMARY_CAUSAL,
    )


def adaptive_queryselect() -> ExternalAdapter:
    """RETIRED PRE-OUTCOME on 2026-09-06. Kept so the amendment stays visible.

    No Adaptive QuerySelect checkpoint is published and the repository carries
    no LICENSE file. Running plain QuerySelect under this name would misreport
    what was benchmarked, and retraining is outside the compute plan. Replaced
    by DAC before any benchmark outcome existed.
    """
    return ExternalAdapter(
        name="adaptive_queryselect",
        official_repository="https://github.com/UTAustin-ITML/fundamental-limits",
        entry_point="RETIRED: no published Adaptive QuerySelect checkpoint exists",
        integration_notes=(
            "RETIRED_PRE_OUTCOME (2026-09-06), replaced by DAC. Retained only as an "
            "amendment record: deleting the row would erase the fact that this "
            "comparator was pre-registered and then replaced, which is the history a "
            "reader needs to check that the substitution was not results-driven."
        ),
        status=AdapterStatus.NOT_READY,
        role=BenchmarkRole.LEGACY_ANCHOR,
    )


def dac() -> ExternalAdapter:
    """Replaces Adaptive QuerySelect in the primary set (P-6, 2026-09-06)."""
    return ExternalAdapter(
        name="dac",
        official_repository="https://github.com/QQQ-yi/DAC",
        entry_point="DAC dynamic attention-aware task-agnostic prompt compression",
        integration_notes=(
            "Scores tokens from a frozen causal LM's attention and entropy and emits "
            "HARD TEXT, so atom presence T_z stays auditable by the same frozen "
            "matcher. It trains no compressor of its own; the artefact to pin is the "
            "base model. Its knob is a compression RATIO, not a token budget, so the "
            "adapter must search the ratio to hit the common budget and report the "
            "realised token count alongside the requested one."
        ),
        role=BenchmarkRole.PRIMARY_CAUSAL,
    )


def selective_context() -> ExternalAdapter:
    """CONTINGENCY ONLY. Not a fifth primary comparator.

    May be promoted to replace a primary only if that primary is declared
    unusable BEFORE any CausalRelay benchmark outcome exists, and only for a
    licence prohibition, a missing executable artefact, an irreproducible native
    implementation, or an irrecoverable technical incompatibility. Never because
    CausalRelay performs poorly against it.
    """
    return ExternalAdapter(
        name="selective_context",
        official_repository="https://github.com/liyucheng09/Selective_Context",
        entry_point="Selective Context self-information lexical-unit filtering",
        integration_notes=(
            "CONTINGENCY_CAUSAL. Emits hard text and is pinnable to a signed tag, but "
            "it does not enter the primary set or the superiority denominator while it "
            "holds this role. Its knob is a reduce ratio, so it needs the same budget "
            "adapter as DAC."
        ),
        role=BenchmarkRole.LEGACY_ANCHOR,
    )


def cpc() -> ExternalAdapter:
    return ExternalAdapter(
        name="cpc",
        official_repository="https://github.com/Workday/cpc",
        entry_point="Context-aware Prompt Compression, sentence-level",
        integration_notes=(
            "Sentence-level compression with a context-aware encoder; output is text. "
            "Its compression ratio is calibrated on development data to hit the "
            "common budget."
        ),
        role=BenchmarkRole.PRIMARY_CAUSAL,
    )


def llmlingua2() -> ExternalAdapter:
    return ExternalAdapter(
        name="llmlingua2",
        official_repository="https://github.com/microsoft/LLMLingua",
        entry_point="LLMLingua-2 task-agnostic token compression",
        integration_notes=(
            "Task-agnostic extractive token compression with a mature public "
            "implementation; exposes a target compression rate that maps onto the "
            "common token budget."
        ),
        role=BenchmarkRole.PRIMARY_CAUSAL,
    )


def recomp_extractive() -> ExternalAdapter:
    return ExternalAdapter(
        name="recomp_extractive",
        official_repository="https://github.com/carriex/recomp",
        entry_point="RECOMP extractive compressor",
        integration_notes=(
            "Accepted legacy anchor. Reported in the full benchmark table but NOT "
            "counted toward the three-SOTA superiority criterion."
        ),
        role=BenchmarkRole.LEGACY_ANCHOR,
    )


def parallelcomp() -> ExternalAdapter:
    return ExternalAdapter(
        name="parallelcomp",
        official_repository="",
        entry_point="long-context KV/token compression",
        integration_notes=(
            "ENDPOINT-ONLY. Its compressed state is a KV/cache representation, so "
            "literal atom presence T_z is undefined for it. No pseudo-T is "
            "manufactured for hidden states; it may populate endpoint and efficiency "
            "metrics only."
        ),
        status=AdapterStatus.ENDPOINT_ONLY,
        role=BenchmarkRole.ENDPOINT_ONLY,
    )


def comi() -> ExternalAdapter:
    return ExternalAdapter(
        name="comi",
        official_repository="",
        entry_point="merged latent memory units",
        integration_notes=(
            "ENDPOINT-ONLY, for the same reason as ParallelComp: the compressed state is latent."
        ),
        status=AdapterStatus.ENDPOINT_ONLY,
        role=BenchmarkRole.ENDPOINT_ONLY,
    )


def longllmlingua() -> ExternalAdapter:
    """Added 2026-09-09 by pre-outcome amendment P-9 (fallback third family)."""
    return ExternalAdapter(
        name="longllmlingua",
        official_repository="https://github.com/microsoft/LLMLingua",
        entry_point="LongLLMLingua question-aware causal LM perplexity compression",
        integration_notes=(
            "Causal LM perplexity-conditioned compression with target_token budget enforcement. "
            "Promoted under pre-outcome amendment P-9 fallback after Perception Compressor "
            "failed executable artifact requirements."
        ),
        role=BenchmarkRole.PRIMARY_CAUSAL,
    )


#: Amended 2026-09-06 (P-6): adaptive_queryselect out, dac in, pre-outcome.
#: Amended 2026-09-09 (P-9): longllmlingua added as third ready primary family.
PRIMARY_SOTA: tuple[str, ...] = ("provence", "cpc", "llmlingua2", "dac", "longllmlingua")
#: Retired pre-outcome. Not a comparator; retained as an amendment record.
RETIRED_PRE_OUTCOME: tuple[str, ...] = ("adaptive_queryselect",)
#: Predeclared contingency. Never counts toward the superiority headline.
CONTINGENCY_SOTA: tuple[str, ...] = ("selective_context",)
LEGACY_ANCHOR: tuple[str, ...] = ("recomp_extractive",)
ENDPOINT_ONLY: tuple[str, ...] = ("parallelcomp", "comi")

BUILDERS = {
    "provence": provence,
    "adaptive_queryselect": adaptive_queryselect,
    "dac": dac,
    "selective_context": selective_context,
    "cpc": cpc,
    "llmlingua2": llmlingua2,
    "longllmlingua": longllmlingua,
    "recomp_extractive": recomp_extractive,
    "parallelcomp": parallelcomp,
    "comi": comi,
}
