"""Protocol and final-test freeze records.

Two records, not one:

* PROTOCOL freeze -- before Stage 1. Binds the source frame rule, budget, task,
  atomizer, sampler, receiver, matcher, editor, randomisation supports,
  skeleton rule, gates, bootstrap, baseline suite and superiority rule.

* FINAL TEST freeze -- before any final-test execution. Additionally binds the
  test documents, focal samples, atom inventories, model versions, prompts,
  baseline revisions, the FITTED CausalRelay artefact, the feature schema, the
  renderer, budgets, tokenizer, analysis code and every generator.

No final-test runner may execute without a valid test freeze record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .hashing import sha256_file, sha256_json

PROTOCOL_FIELDS: tuple[str, ...] = (
    "preregistration_sha256",
    "artifact_manifest_sha256",
    "source_pool_sha256",
    "git_commit",
    "frozen_utc",
    "relay_model",
    "receiver_model",
    "tokenizer",
    "source_window_tokens",
    "relay_budget_tokens",
    "downstream_task_sha256",
    "receiver_prompt_sha256",
    "renderer_sha256",
    "sampling_k",
    "master_seed",
)

TEST_FIELDS: tuple[str, ...] = PROTOCOL_FIELDS + (
    "test_document_manifest_sha256",
    "focal_sample_sha256",
    "atom_inventory_sha256",
    "baseline_revisions_sha256",
    "causalrelay_artifact_sha256",
    "feature_schema_sha256",
    "analysis_code_sha256",
    "table_generator_sha256",
    "figure_generator_sha256",
    "bootstrap_code_sha256",
    "superiority_rule_sha256",
)


class FreezeIncomplete(RuntimeError):
    pass


@dataclass(slots=True)
class FreezeDocument:
    kind: str
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def required(self) -> tuple[str, ...]:
        return TEST_FIELDS if self.kind == "final_test" else PROTOCOL_FIELDS

    def missing(self) -> list[str]:
        return [
            f
            for f in self.required
            if self.fields.get(f) in (None, "", "UNFROZEN", "TBD", "PROPOSED")
        ]

    def validate(self) -> None:
        gaps = self.missing()
        if gaps:
            raise FreezeIncomplete(
                f"{self.kind} freeze record is incomplete. Unfilled: {', '.join(gaps)}. "
                "These are blanks by design -- fill them with real values, never "
                "placeholders, before running."
            )

    def to_json(self) -> str:
        body = {"kind": self.kind, "fields": dict(sorted(self.fields.items()))}
        body["record_sha256"] = sha256_json(body)
        return json.dumps(body, indent=2, sort_keys=True) + "\n"

    def write(self, path: Path) -> Path:
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def new_record(kind: str, **fields: Any) -> FreezeDocument:
    payload = dict(fields)
    payload.setdefault("frozen_utc", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return FreezeDocument(kind=kind, fields=payload)


def load_record(path: Path) -> FreezeDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return FreezeDocument(kind=payload["kind"], fields=payload.get("fields", {}))


def verify_record(
    path: Path, *, referenced: dict[str, Path] | None = None
) -> tuple[bool, list[str]]:
    """Check the record is complete AND that the artefacts it names still hash
    to the recorded values."""
    problems: list[str] = []
    try:
        doc = load_record(path)
    except Exception as exc:
        return False, [f"unreadable freeze record: {exc}"]
    gaps = doc.missing()
    if gaps:
        problems.append(f"unfilled fields: {', '.join(gaps)}")
    for key, target in (referenced or {}).items():
        expected = doc.fields.get(key)
        if expected is None:
            problems.append(f"record does not carry {key}")
            continue
        if not Path(target).exists():
            problems.append(f"referenced artefact missing: {target}")
            continue
        if sha256_file(Path(target)) != expected:
            problems.append(f"referenced artefact changed since freeze: {target}")
    return (not problems, problems)
