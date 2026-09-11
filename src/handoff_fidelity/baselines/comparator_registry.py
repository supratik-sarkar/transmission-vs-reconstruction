"""Primary causal-textual comparator registry and adapters (V3.5).

Implements the 6 primary candidate families, explicit readiness statuses,
and genuine LongLLMLingua identity under isolated execution environments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ComparatorReadinessStatus(StrEnum):
    BENCHMARK_READY = "BENCHMARK_READY"
    BLOCKED_BY_LICENSE = "BLOCKED_BY_LICENSE"
    BLOCKED_BY_MISSING_ARTIFACT = "BLOCKED_BY_MISSING_ARTIFACT"
    BLOCKED_BY_REPRODUCTION_FAILURE = "BLOCKED_BY_REPRODUCTION_FAILURE"
    BLOCKED_BY_IMPLEMENTATION_DEPENDENCY = "BLOCKED_BY_IMPLEMENTATION_DEPENDENCY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class PrimaryComparatorEntry:
    family: str
    system_name: str
    paper_title: str
    paper_citation_key: str
    official_repository: str
    commit: str
    checkpoint: str
    licence: str
    ranking_mode: str
    requires_isolated_env: bool
    status: ComparatorReadinessStatus
    budget_neutral_adapter: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# Authoritative V3.5 Primary Comparator Registry
PRIMARY_COMPARATOR_REGISTRY: dict[str, PrimaryComparatorEntry] = {
    "LLMLingua-2": PrimaryComparatorEntry(
        family="LLMLingua-2",
        system_name="LLMLingua2",
        paper_title="LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression",
        paper_citation_key="pan2024llmlingua2",
        official_repository="https://github.com/microsoft/LLMLingua",
        commit="7f8d625",
        checkpoint="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        licence="MIT",
        ranking_mode="token_classification",
        requires_isolated_env=False,
        status=ComparatorReadinessStatus.BENCHMARK_READY,
        budget_neutral_adapter="HandoffFidelityBudgetNeutralTokenPruner",
        notes="Verified textual token classification pruner.",
    ),
    "DAC": PrimaryComparatorEntry(
        family="DAC",
        system_name="DAC",
        paper_title="Dynamic Attention-based Context Compression for LLMs",
        paper_citation_key="dac2024dynamic",
        official_repository="https://github.com/microsoft/LLMLingua",
        commit="4a1d89e",
        checkpoint="microsoft/dac-attention-entropy",
        licence="MIT",
        ranking_mode="attention_entropy",
        requires_isolated_env=False,
        status=ComparatorReadinessStatus.BENCHMARK_READY,
        budget_neutral_adapter="HandoffFidelityBudgetNeutralTokenPruner",
        notes="Verified attention-entropy token selector.",
    ),
    "LongLLMLingua": PrimaryComparatorEntry(
        family="LongLLMLingua",
        system_name="LongLLMLingua",
        paper_title="LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression",
        paper_citation_key="jiang2024longllmlingua",
        official_repository="https://github.com/microsoft/LLMLingua",
        commit="b29ef10",
        checkpoint="meta-llama/Llama-2-7b-hf",
        licence="MIT",
        ranking_mode="longllmlingua",
        requires_isolated_env=True,
        status=ComparatorReadinessStatus.BLOCKED_BY_IMPLEMENTATION_DEPENDENCY,
        budget_neutral_adapter="IsolatedLongLLMLinguaAdapter",
        notes="Genuine official LongLLMLingua ranking path (strictly disjoint from Selective Context). Blocked by transitive dependencies on macOS ARM64 pending containerized isolation.",
    ),
    "Perception Compressor": PrimaryComparatorEntry(
        family="Perception Compressor",
        system_name="PerceptionCompressor",
        paper_title="Perception Compressor: Hierarchical Context Compression for LLMs",
        paper_citation_key="perception2025hierarchical",
        official_repository="https://github.com/Twilightaaa/PerceptionCompressor",
        commit="UNRESOLVED_UPSTREAM",
        checkpoint="UNRESOLVED_CHECKPOINT",
        licence="Apache-2.0",
        ranking_mode="hierarchical_query_aware",
        requires_isolated_env=True,
        status=ComparatorReadinessStatus.BLOCKED_BY_MISSING_ARTIFACT,
        budget_neutral_adapter="PerceptionCompressorAdapter",
        notes="Official code published, awaiting verified runnable environment weights.",
    ),
    "TACO-RL": PrimaryComparatorEntry(
        family="TACO-RL",
        system_name="TACO-RL",
        paper_title="TACO-RL: Task-Aware Prompt Compression Optimization with Reinforcement Learning",
        paper_citation_key="tacorl2025findings",
        official_repository="https://www.microsoft.com/en-us/research/publication/taco-rl",
        commit="UNRESOLVED_UPSTREAM",
        checkpoint="UNRESOLVED_CHECKPOINT",
        licence="Research Only / Gated",
        ranking_mode="task_reward_token_policy",
        requires_isolated_env=True,
        status=ComparatorReadinessStatus.BLOCKED_BY_MISSING_ARTIFACT,
        budget_neutral_adapter="TacoRlAdapter",
        notes="Authoritative pre-trained policy checkpoints pending open artifact release.",
    ),
    "Provence": PrimaryComparatorEntry(
        family="Provence",
        system_name="Provence",
        paper_title="Provence: Cross-Encoder Context Pruning for Retrieval-Augmented Generation",
        paper_citation_key="provence2025cross",
        official_repository="https://github.com/naver/provence",
        commit="c108f92",
        checkpoint="naver/provence-reranker",
        licence="Restricted Research Use Only",
        ranking_mode="cross_encoder_context_pruning",
        requires_isolated_env=True,
        status=ComparatorReadinessStatus.BLOCKED_BY_LICENSE,
        budget_neutral_adapter="ProvenceAdapter",
        notes="Blocked by restricted non-commercial redistribution license.",
    ),
}


def get_comparator_registry() -> dict[str, PrimaryComparatorEntry]:
    """Return the frozen primary comparator registry."""
    return dict(PRIMARY_COMPARATOR_REGISTRY)


def get_ready_primary_families() -> list[PrimaryComparatorEntry]:
    """Return all currently BENCHMARK_READY primary textual families."""
    return [
        entry
        for entry in PRIMARY_COMPARATOR_REGISTRY.values()
        if entry.status == ComparatorReadinessStatus.BENCHMARK_READY
    ]


def count_ready_primary_families() -> int:
    """Return the number of genuinely ready primary textual families."""
    return len(get_ready_primary_families())


def is_headline_sota_eligible() -> bool:
    """Broad textual headline SOTA is eligible iff >= 4 families are ready."""
    return count_ready_primary_families() >= 4
