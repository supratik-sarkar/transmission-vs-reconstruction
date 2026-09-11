"""Authentic document-level outcome schema and persistence module (V3.5).

Enforces strict provenance, authentic per-document lineage, and structural
rejection of aggregate-to-document broadcasting.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VALID_SPLITS = frozenset({"model_selection"})
VALID_EVIDENCE_STRATA = frozenset({"model_selection_adaptive"})
VALID_STATUSES = frozenset(
    {
        "COMPLETE",
        "SCIENTIFIC_FAILURE",
        "PROVIDER_FAILURE",
        "NOT_ESTIMABLE",
        "NOT_APPLICABLE",
        "BLOCKED_BY_LICENSE",
        "BLOCKED_BY_MISSING_ARTIFACT",
        "RESUMABLE_FREE_QUOTA_EXHAUSTED",
    }
)
HEX64_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class OutcomeLineageError(ValueError):
    """Raised when an outcome record violates lineage or schema invariants."""


class AggregateBroadcastError(OutcomeLineageError):
    """Raised when aggregate summary statistics are broadcast across document rows."""


@dataclass(frozen=True, slots=True)
class DocumentOutcomeRecord:
    document_id_hash: str
    split: str
    policy_id: str
    receiver_id: str
    receiver_config_hash: str
    logical_evaluation_id: str
    raw_response_sha256: str
    metric_name: str
    metric_value: float | None
    evaluable_status: str
    realized_tokens: int | None
    evidence_stratum: str
    outer_fold: int | None = None
    decoder_replicate_ids: list[str] = field(default_factory=list)
    source_feature_hash: str | None = None
    policy_artifact_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_document_outcome(record: DocumentOutcomeRecord | dict[str, Any]) -> dict[str, Any]:
    """Validate a single document-level outcome record against V3.5 schema."""
    data = record.to_dict() if isinstance(record, DocumentOutcomeRecord) else dict(record)

    doc_hash = str(data.get("document_id_hash", ""))
    if len(doc_hash) < 16:
        raise OutcomeLineageError(f"document_id_hash must be >= 16 chars: {doc_hash}")

    split = str(data.get("split", ""))
    if split not in VALID_SPLITS:
        raise OutcomeLineageError(f"split must be one of {sorted(VALID_SPLITS)}: {split}")

    stratum = str(data.get("evidence_stratum", ""))
    if stratum not in VALID_EVIDENCE_STRATA:
        raise OutcomeLineageError(
            f"evidence_stratum must be one of {sorted(VALID_EVIDENCE_STRATA)}: {stratum}"
        )

    status = str(data.get("evaluable_status", ""))
    if status not in VALID_STATUSES:
        raise OutcomeLineageError(f"evaluable_status invalid: {status}")

    rec_hash = str(data.get("receiver_config_hash", ""))
    if len(rec_hash) < 16:
        raise OutcomeLineageError(f"receiver_config_hash must be >= 16 chars: {rec_hash}")

    log_eval_id = str(data.get("logical_evaluation_id", "")).strip()
    if not log_eval_id:
        raise OutcomeLineageError("logical_evaluation_id must be non-empty")

    raw_sha = str(data.get("raw_response_sha256", "")).strip().lower()
    if not HEX64_PATTERN.match(raw_sha):
        raise OutcomeLineageError(f"raw_response_sha256 must be 64-char hex: {raw_sha}")

    metric_name = str(data.get("metric_name", "")).strip()
    if not metric_name:
        raise OutcomeLineageError("metric_name must be non-empty")

    val = data.get("metric_value")
    if val is not None:
        try:
            data["metric_value"] = float(val)
        except (TypeError, ValueError) as err:
            raise OutcomeLineageError(f"metric_value must be float or None: {val}") from err

    toks = data.get("realized_tokens")
    if toks is not None and (not isinstance(toks, int) or toks < 0):
        raise OutcomeLineageError(f"realized_tokens must be non-negative integer: {toks}")

    fold = data.get("outer_fold")
    if fold is not None and (not isinstance(fold, int) or fold < 0):
        raise OutcomeLineageError(f"outer_fold must be non-negative integer: {fold}")

    return data


def validate_document_outcome_batch(
    records: Sequence[DocumentOutcomeRecord | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate a batch of document outcomes, enforcing genuine per-document lineage.

    Detects and rejects:
    1. Duplicated document rows within the same (policy, metric).
    2. Shared evaluation IDs or response hashes across distinct documents.
    3. Degenerate identical metric values where distinct independent document observations
       are required but are missing authentic execution evidence.
    """
    if not records:
        raise OutcomeLineageError("Cannot validate empty outcome batch")

    validated: list[dict[str, Any]] = []
    by_policy_metric: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for item in records:
        row = validate_document_outcome(item)
        validated.append(row)
        k = (row["policy_id"], row["metric_name"])
        by_policy_metric.setdefault(k, []).append(row)

    for (p_id, m_name), rows in by_policy_metric.items():
        doc_ids = [r["document_id_hash"] for r in rows]
        if len(doc_ids) != len(set(doc_ids)):
            raise OutcomeLineageError(
                f"Duplicate document_id_hash found for policy {p_id}, metric {m_name}"
            )

        eval_ids = [r["logical_evaluation_id"] for r in rows]
        raw_shas = [r["raw_response_sha256"] for r in rows]

        # Lineage uniqueness check across different documents
        if len(rows) > 1:
            if len(set(eval_ids)) < len(rows):
                raise AggregateBroadcastError(
                    f"Aggregate lineage detected: multiple documents share the same logical_evaluation_id "
                    f"for policy {p_id}, metric {m_name}."
                )
            if len(set(raw_shas)) < len(rows):
                raise AggregateBroadcastError(
                    f"Aggregate lineage detected: multiple documents share the same raw_response_sha256 "
                    f"for policy {p_id}, metric {m_name}."
                )

        # Invariant document vector detection: if >= 10 rows and all numerical values are exactly identical,
        # require explicit verified non-synthetic provenance flags.
        numeric_vals = [r["metric_value"] for r in rows if r["metric_value"] is not None]
        if len(numeric_vals) >= 10 and len(set(numeric_vals)) == 1:
            raise AggregateBroadcastError(
                f"Suspicious invariant document vector detected for {p_id} ({m_name}): "
                f"all {len(numeric_vals)} documents have identical value {numeric_vals[0]} "
                f"without empirical variance."
            )

    return validated


def write_document_outcomes_jsonl(
    records: Sequence[DocumentOutcomeRecord | dict[str, Any]],
    output_path: Path,
) -> str:
    """Validate and write outcomes to a JSON Lines file, returning its SHA-256 hash."""
    validated = validate_document_outcome_batch(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content_lines = [json.dumps(row, sort_keys=True) for row in validated]
    text = "\n".join(content_lines) + "\n"
    output_path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_document_outcomes_csv(
    records: Sequence[DocumentOutcomeRecord | dict[str, Any]],
    output_path: Path,
) -> str:
    """Validate and write outcomes to a CSV file, returning its SHA-256 hash."""
    validated = validate_document_outcome_batch(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id_hash",
        "split",
        "outer_fold",
        "policy_id",
        "receiver_id",
        "receiver_config_hash",
        "logical_evaluation_id",
        "raw_response_sha256",
        "metric_name",
        "metric_value",
        "evaluable_status",
        "realized_tokens",
        "evidence_stratum",
        "source_feature_hash",
        "policy_artifact_sha256",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in validated:
            writer.writerow(r)
    return hashlib.sha256(output_path.read_bytes()).hexdigest()
