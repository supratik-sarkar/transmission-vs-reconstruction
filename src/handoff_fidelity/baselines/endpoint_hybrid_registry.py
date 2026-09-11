"""Endpoint and hybrid representation adapter registry (V3.5).

Enforces:
1. Representation-aware metric applicability: discrete atom-level metrics
   (Tbar, C_comm, C_recon, Delta_budget) are strictly NOT_APPLICABLE to latent/hybrid methods.
2. Hard prohibition against numerical results without genuine execution lineage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class EndpointRepresentation(StrEnum):
    LATENT = "LATENT"
    HYBRID = "HYBRID"


class InapplicableMetricError(ValueError):
    """Raised when an atom-level causal metric is improperly computed for latent/hybrid representations."""


class MissingLineageError(ValueError):
    """Raised when an empirical result row lacks verifiable raw cell execution lineage."""


@dataclass(frozen=True, slots=True)
class EndpointHybridEntry:
    family: str
    system_name: str
    paper_title: str
    paper_citation_key: str
    official_repository: str
    representation: EndpointRepresentation
    applicable_metrics: tuple[str, ...]
    inapplicable_metrics: tuple[str, ...]
    status: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["representation"] = self.representation.value
        return d


APPLICABLE_COMMON_METRICS: tuple[str, ...] = ("A", "realized_tokens", "latency_ms")
INAPPLICABLE_ATOM_METRICS: tuple[str, ...] = ("Tbar", "C_comm", "C_recon", "Delta_budget")

ENDPOINT_HYBRID_REGISTRY: dict[str, EndpointHybridEntry] = {
    "COMI": EndpointHybridEntry(
        family="COMI",
        system_name="COMI",
        paper_title="COMI: Context Compression via Marginal Information Gain",
        paper_citation_key="comi2026iclr",
        official_repository="https://github.com/Twilightaaa/COMI",
        representation=EndpointRepresentation.LATENT,
        applicable_metrics=APPLICABLE_COMMON_METRICS,
        inapplicable_metrics=INAPPLICABLE_ATOM_METRICS,
        status="IMPLEMENTATION_READY",
        notes="Latent merged memory representation. Discrete atom transmission and surplus are mathematically undefined.",
    ),
    "RAM": EndpointHybridEntry(
        family="RAM",
        system_name="RAM",
        paper_title="Read As HuMan: Hybrid Text and Semantic Vector Context Compression",
        paper_citation_key="ram2026acl",
        official_repository="https://github.com/Twilightaaa/RAM",
        representation=EndpointRepresentation.HYBRID,
        applicable_metrics=APPLICABLE_COMMON_METRICS,
        inapplicable_metrics=INAPPLICABLE_ATOM_METRICS,
        status="IMPLEMENTATION_READY",
        notes="Hybrid text and compact summary vectors. Discrete atom transmission and surplus are mathematically undefined.",
    ),
    "GMSA": EndpointHybridEntry(
        family="GMSA",
        system_name="GMSA",
        paper_title="GMSA: Generative Memory with Soft Attention for Long-Context LLMs",
        paper_citation_key="gmsa2026acl",
        official_repository="https://github.com/Twilightaaa/GMSA",
        representation=EndpointRepresentation.LATENT,
        applicable_metrics=APPLICABLE_COMMON_METRICS,
        inapplicable_metrics=INAPPLICABLE_ATOM_METRICS,
        status="IMPLEMENTATION_READY",
        notes="Soft token encoder-decoder compression. Discrete atom transmission and surplus are mathematically undefined.",
    ),
    "SARA": EndpointHybridEntry(
        family="SARA",
        system_name="SARA",
        paper_title="SARA: Semantic Augmented Retrieval Aggregation",
        paper_citation_key="sara2026acl",
        official_repository="https://aclanthology.org/2026.acl-long.661/",
        representation=EndpointRepresentation.HYBRID,
        applicable_metrics=APPLICABLE_COMMON_METRICS,
        inapplicable_metrics=INAPPLICABLE_ATOM_METRICS,
        status="IMPLEMENTATION_READY",
        notes="Hybrid RAG with retained text plus semantic vectors. Discrete atom transmission and surplus are mathematically undefined.",
    ),
}


def get_endpoint_hybrid_registry() -> dict[str, EndpointHybridEntry]:
    """Return the frozen endpoint/hybrid adapter registry."""
    return dict(ENDPOINT_HYBRID_REGISTRY)


def validate_endpoint_metric_applicability(family: str, metric_name: str) -> None:
    """Validate that the requested metric is scientifically defined for this representation."""
    entry = ENDPOINT_HYBRID_REGISTRY.get(family)
    if entry is None:
        return
    if metric_name in entry.inapplicable_metrics:
        raise InapplicableMetricError(
            f"Metric '{metric_name}' is NOT_APPLICABLE to {entry.representation.value} method {family}. "
            f"Discrete atom transmission quantities cannot be fabricated for continuous/latent representations."
        )


def verify_empirical_lineage_required(result_row: dict[str, Any]) -> None:
    """Prohibit numerical results that lack verifiable raw execution lineage."""
    estimate = result_row.get("estimate")
    status = result_row.get("status", "")
    family = result_row.get("family") or result_row.get("system_id", "")

    # If an estimate is provided as COMPLETE, require verifiable execution lineage
    if estimate is not None and status == "COMPLETE":
        raw_sha = result_row.get("raw_response_sha256") or result_row.get("source_artifact_sha256")
        cell_id = result_row.get("cell_id") or result_row.get("logical_evaluation_id")
        if not raw_sha or not cell_id:
            raise MissingLineageError(
                f"Result row for {family} has estimate {estimate} but lacks raw execution lineage "
                f"(raw_response_sha256 or cell_id). Numerical values without cell execution lineage are strictly prohibited."
            )
