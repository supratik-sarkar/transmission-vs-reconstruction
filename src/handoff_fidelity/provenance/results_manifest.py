"""RESULTS_MANIFEST.json.

Maps every reported artefact -- each table, each figure, each headline metric --
back to the run IDs, source hashes, config hashes, model revisions, baseline
revisions, analysis version and exporter version that produced it.

No result artefact without provenance may be accepted for manuscript export.
The manuscript guard enforces that, so a number cannot reach the paper by being
typed in.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .hashing import sha256_file, sha256_json

ANALYSIS_VERSION = "analysis-v1"
EXPORTER_VERSION = "exporter-v1"


@dataclass(slots=True)
class ResultEntry:
    artifact: str  # e.g. "tables/benchmark_main.tex"
    kind: str  # table | figure | metric
    run_ids: list[str] = field(default_factory=list)
    source_hashes: list[str] = field(default_factory=list)
    config_hashes: list[str] = field(default_factory=list)
    model_revisions: dict[str, str] = field(default_factory=dict)
    baseline_revisions: dict[str, str] = field(default_factory=dict)
    analysis_version: str = ANALYSIS_VERSION
    exporter_version: str = EXPORTER_VERSION
    artifact_sha256: str | None = None
    stage: str = ""
    notes: str = ""

    def incomplete(self) -> list[str]:
        gaps: list[str] = []
        if not self.run_ids:
            gaps.append("run_ids")
        if not self.source_hashes:
            gaps.append("source_hashes")
        if not self.config_hashes:
            gaps.append("config_hashes")
        if not self.model_revisions:
            gaps.append("model_revisions")
        if self.artifact_sha256 is None:
            gaps.append("artifact_sha256")
        return gaps


@dataclass(slots=True)
class ResultsManifest:
    entries: dict[str, ResultEntry] = field(default_factory=dict)

    def add(self, entry: ResultEntry) -> None:
        self.entries[entry.artifact] = entry

    def stamp(self, artifact: str, path: Path) -> None:
        if artifact in self.entries and Path(path).exists():
            self.entries[artifact].artifact_sha256 = sha256_file(Path(path))

    def unprovenanced(self) -> dict[str, list[str]]:
        return {k: v.incomplete() for k, v in sorted(self.entries.items()) if v.incomplete()}

    def to_json(self) -> str:
        body = {
            "analysis_version": ANALYSIS_VERSION,
            "exporter_version": EXPORTER_VERSION,
            "entries": {k: asdict(v) for k, v in sorted(self.entries.items())},
        }
        body["manifest_sha256"] = sha256_json(body)
        return json.dumps(body, indent=2, sort_keys=True) + "\n"

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> ResultsManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = {k: ResultEntry(**v) for k, v in (payload.get("entries") or {}).items()}
        return cls(entries)

    def artifacts(self) -> Iterable[str]:
        return sorted(self.entries)
