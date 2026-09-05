"""Manuscript readiness guard.

Fails if the submission manuscript still carries unresolved empirical content:

  * \\tbd placeholders
  * \\phfig placeholders for EMPIRICAL figures
  * missing generated table fragments
  * missing generated figure files
  * unresolved citations or references
  * empirical artefacts absent from RESULTS_MANIFEST.json

It deliberately distinguishes intentionally STATIC CONCEPTUAL figures (the hero
schematic, the workflow diagrams) from unresolved EXPERIMENTAL figures. A
conceptual figure is drawn once by hand and is not a result; demanding a
generated file for it would push toward fabricating one.

The guard never makes itself pass by inventing data. If a check fails the
correct action is to run the experiment, not to fill the placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .figures import CONTAINER_FLOAT_LABELS, FIGURE_TARGETS, STATIC_CONCEPTUAL_FIGURES
from .tables import STATIC_STRUCTURAL_TABLES, TABLE_TARGETS

_TBD = re.compile(r"\\tbd\b")
_PHFIG = re.compile(r"\\phfig\b")
_LABEL = re.compile(r"\\label\{([^}]+)\}")
_UNDEFINED_LOG = re.compile(
    r"(Citation .* undefined|Reference .* undefined|LaTeX Warning: There were undefined)"
)


@dataclass(slots=True)
class CheckResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def report(self) -> str:
        lines = [("PASS" if self.ok else "FAIL") + ": manuscript readiness"]
        for key, value in sorted(self.counts.items()):
            lines.append(f"  {key}: {value}")
        for f in self.failures:
            lines.append(f"  FAIL {f}")
        for w in self.warnings:
            lines.append(f"  warn {w}")
        return "\n".join(lines)


def _phfig_labels(tex: str) -> set[str]:
    """Labels of floats that still contain a \\phfig placeholder."""
    out: set[str] = set()
    for block in re.split(r"\\begin\{figure\*?\}", tex)[1:]:
        body = block.split(r"\end{figure}")[0]
        if _PHFIG.search(body):
            out.update(_LABEL.findall(body))
    return out


def check_manuscript(
    tex_path: Path,
    *,
    tables_dir: Path,
    figures_dir: Path,
    results_manifest: Path | None = None,
    log_path: Path | None = None,
    require_empirical: bool = True,
) -> CheckResult:
    tex = Path(tex_path).read_text(encoding="utf-8", errors="replace")
    res = CheckResult(ok=True)

    n_tbd = len(_TBD.findall(tex))
    res.counts["tbd_placeholders"] = n_tbd
    if require_empirical and n_tbd:
        res.failures.append(f"{n_tbd} unresolved \\tbd placeholder(s)")

    ph_labels = _phfig_labels(tex)
    # A parent label of a subfigure pair sits on a float whose CHILDREN carry the
    # placeholders. Counting the parent as an unresolved empirical figure would
    # demand a generated file that no exporter should ever produce.
    exempt = STATIC_CONCEPTUAL_FIGURES | CONTAINER_FLOAT_LABELS
    empirical_ph = sorted(ph_labels - exempt)
    conceptual_ph = sorted(ph_labels & exempt)
    res.counts["phfig_empirical"] = len(empirical_ph)
    res.counts["phfig_conceptual_ok"] = len(conceptual_ph)
    if require_empirical and empirical_ph:
        res.failures.append("empirical figure placeholders remain: " + ", ".join(empirical_ph))
    for label in conceptual_ph:
        res.warnings.append(f"{label} is an intentionally static conceptual figure")

    referenced_labels = set(_LABEL.findall(tex))
    missing_tables = [
        f
        for lab, f in sorted(TABLE_TARGETS.items())
        if lab in referenced_labels and not (Path(tables_dir) / f).exists()
    ]
    res.counts["missing_table_fragments"] = len(missing_tables)
    if require_empirical and missing_tables:
        res.failures.append("missing generated table fragments: " + ", ".join(missing_tables))

    # Symmetry with the conceptual-figure notes below. Without this a reader of
    # the report cannot tell that a static table was considered and correctly
    # exempted, as opposed to overlooked.
    static_tables = sorted(referenced_labels & STATIC_STRUCTURAL_TABLES)
    res.counts["static_structural_tables_ok"] = len(static_tables)
    for label in static_tables:
        res.warnings.append(f"{label} is an intentionally static structural table")

    missing_figs = [
        f
        for lab, f in sorted(FIGURE_TARGETS.items())
        if lab in referenced_labels and not (Path(figures_dir) / f).exists()
    ]
    res.counts["missing_figure_files"] = len(missing_figs)
    if require_empirical and missing_figs:
        res.failures.append("missing generated figure files: " + ", ".join(missing_figs))

    if log_path and Path(log_path).exists():
        log = Path(log_path).read_text(encoding="utf-8", errors="replace")
        undefined = _UNDEFINED_LOG.findall(log)
        res.counts["undefined_refs_or_citations"] = len(undefined)
        if undefined:
            res.failures.append(
                f"{len(undefined)} undefined citation/reference warning(s) in the build log"
            )
        if "??" in log and "LaTeX Warning" in log:
            res.warnings.append("build log mentions '??'; check for rendered question marks")

    if results_manifest is not None:
        if not Path(results_manifest).exists():
            if require_empirical:
                res.failures.append("RESULTS_MANIFEST.json is absent")
        else:
            from ..provenance.results_manifest import ResultsManifest  # noqa: PLC0415

            manifest = ResultsManifest.load(Path(results_manifest))
            gaps = manifest.unprovenanced()
            res.counts["unprovenanced_artifacts"] = len(gaps)
            if gaps:
                res.failures.append(
                    "artefacts lacking provenance: "
                    + ", ".join(f"{k} (missing {', '.join(v)})" for k, v in sorted(gaps.items()))
                )
            expected = {f for lab, f in TABLE_TARGETS.items() if lab in referenced_labels}
            expected |= {f for lab, f in FIGURE_TARGETS.items() if lab in referenced_labels}
            recorded = {Path(a).name for a in manifest.artifacts()}
            unrecorded = sorted(expected - recorded)
            if require_empirical and unrecorded:
                res.failures.append(
                    "empirical assets not present in RESULTS_MANIFEST.json: "
                    + ", ".join(unrecorded)
                )

    res.ok = not res.failures
    return res
