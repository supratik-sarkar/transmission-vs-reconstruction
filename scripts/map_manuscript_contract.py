#!/usr/bin/env python3
"""Mechanically map a real manuscript to the exporter targets.

Answers, from the actual .tex rather than from a hand-written table:

  * which table/figure labels does the manuscript define?
  * which of those does an exporter know how to produce?
  * which exporter targets does the manuscript never reference (orphans)?
  * which bibliography keys are cited but undefined, or defined but uncited?
  * how many empirical placeholders remain, and where?

The check runs in BOTH directions. A one-directional check passes while an
exporter quietly produces a fragment no manuscript label consumes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handoff_fidelity.export.figures import (  # noqa: E402
    CONTAINER_FLOAT_LABELS,
    FIGURE_TARGETS,
    STATIC_CONCEPTUAL_FIGURES,
)
from handoff_fidelity.export.tables import (  # noqa: E402
    STATIC_STRUCTURAL_TABLES,
    TABLE_TARGETS,
)
from handoff_fidelity.provenance.hashing import sha256_file  # noqa: E402

_LABEL = re.compile(r"\\label\{([^}]+)\}")
_CITE = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]+)\}")
_BIBKEY = re.compile(r"^@\w+\{\s*([^,\s]+)\s*,", re.M)
_TBD = re.compile(r"\\tbd\b")
_PHFIG = re.compile(r"\\phfig\b")
_ENVBLOCK = re.compile(r"\\begin\{(table|figure)\*?\}(.*?)\\end\{\1\*?\}", re.S)


def _labels_by_env(tex: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"table": set(), "figure": set()}
    for env, body in _ENVBLOCK.findall(tex):
        out[env].update(_LABEL.findall(body))
    return out


def _placeholder_labels(tex: str) -> dict[str, set[str]]:
    """Labels of floats that still contain \\tbd or \\phfig."""
    out: dict[str, set[str]] = {"tbd": set(), "phfig": set()}
    for _env, body in _ENVBLOCK.findall(tex):
        labels = set(_LABEL.findall(body))
        if _TBD.search(body):
            out["tbd"] |= labels
        if _PHFIG.search(body):
            out["phfig"] |= labels
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tex", required=True)
    ap.add_argument("--bib", default=None)
    ap.add_argument("--json", default=None, help="write the machine-readable report here")
    args = ap.parse_args()

    tex_path = Path(args.tex)
    tex = tex_path.read_text(encoding="utf-8", errors="replace")
    by_env = _labels_by_env(tex)
    placeholders = _placeholder_labels(tex)
    all_labels = set(_LABEL.findall(tex))

    report: dict[str, object] = {
        "tex": str(tex_path.name),
        "tex_sha256": sha256_file(tex_path),
        "tex_lines": tex.count("\n") + 1,
    }

    # ---- tables, both directions -----------------------------------------
    tex_tables = by_env["table"]
    known_tables = set(TABLE_TARGETS)
    report["tables"] = {
        "in_manuscript": sorted(tex_tables),
        "mapped": sorted(tex_tables & known_tables),
        "declared_static": sorted(tex_tables & STATIC_STRUCTURAL_TABLES),
        "unmapped_in_manuscript": sorted(tex_tables - known_tables - STATIC_STRUCTURAL_TABLES),
        "orphan_exporters": sorted(known_tables - tex_tables),
        "declared_static_not_present": sorted(STATIC_STRUCTURAL_TABLES - tex_tables),
    }

    # ---- figures, both directions ----------------------------------------
    tex_figures = by_env["figure"]
    known_figures = set(FIGURE_TARGETS)
    conceptual = tex_figures & STATIC_CONCEPTUAL_FIGURES
    report["figures"] = {
        "in_manuscript": sorted(tex_figures),
        "mapped_empirical": sorted(tex_figures & known_figures),
        "declared_conceptual": sorted(conceptual),
        "declared_container": sorted(tex_figures & CONTAINER_FLOAT_LABELS),
        "unmapped_in_manuscript": sorted(
            tex_figures - known_figures - STATIC_CONCEPTUAL_FIGURES - CONTAINER_FLOAT_LABELS
        ),
        "orphan_exporters": sorted(known_figures - tex_figures),
    }

    # ---- placeholders -----------------------------------------------------
    report["placeholders"] = {
        "tbd_total_occurrences": len(_TBD.findall(tex)),
        "phfig_total_occurrences": len(_PHFIG.findall(tex)),
        "floats_with_tbd": sorted(placeholders["tbd"]),
        "floats_with_phfig_empirical": sorted(placeholders["phfig"] - STATIC_CONCEPTUAL_FIGURES),
        "floats_with_phfig_conceptual": sorted(placeholders["phfig"] & STATIC_CONCEPTUAL_FIGURES),
    }

    # ---- bibliography -----------------------------------------------------
    if args.bib:
        bib_path = Path(args.bib)
        bib = bib_path.read_text(encoding="utf-8", errors="replace")
        defined = set(_BIBKEY.findall(bib))
        cited: set[str] = set()
        for group in _CITE.findall(tex):
            # A long \\citep{...} is wrapped across lines with a trailing '%',
            # so raw splitting yields keys like "%\nCiteVQA2026". Strip the
            # continuation marker and surrounding whitespace before comparing,
            # or every wrapped citation is reported as undefined.
            for raw in group.split(","):
                key = raw.replace("%", "").strip()
                if key:
                    cited.add(key)
        report["bibliography"] = {
            "bib_sha256": sha256_file(bib_path),
            "defined": len(defined),
            "cited": len(cited),
            "cited_but_undefined": sorted(cited - defined),
            "defined_but_uncited": sorted(defined - cited),
        }

    report["all_labels"] = len(all_labels)

    # ---- print ------------------------------------------------------------
    t = report["tables"]
    f = report["figures"]
    p = report["placeholders"]
    print(f"manuscript: {report['tex']}  ({report['tex_lines']} lines)")
    print(f"sha256:     {report['tex_sha256']}")
    print()
    print(
        f"TABLES   in manuscript {len(t['in_manuscript']):2d}"
        f" | mapped {len(t['mapped']):2d}"
        f" | static {len(t['declared_static']):2d}"
        f" | unmapped {len(t['unmapped_in_manuscript']):2d}"
        f" | orphan exporters {len(t['orphan_exporters']):2d}"
    )
    for label in t["unmapped_in_manuscript"]:
        print(f"    UNMAPPED table label with no exporter: {label}")
    for label in t["orphan_exporters"]:
        print(f"    ORPHAN exporter target never referenced: {label}")
    print()
    print(
        f"FIGURES  in manuscript {len(f['in_manuscript']):2d}"
        f" | empirical mapped {len(f['mapped_empirical']):2d}"
        f" | conceptual {len(f['declared_conceptual']):2d}"
        f" | container {len(f['declared_container']):2d}"
        f" | unmapped {len(f['unmapped_in_manuscript']):2d}"
        f" | orphan exporters {len(f['orphan_exporters']):2d}"
    )
    for label in f["unmapped_in_manuscript"]:
        print(f"    UNMAPPED figure label, neither exporter nor declared conceptual: {label}")
    for label in f["orphan_exporters"]:
        print(f"    ORPHAN exporter target never referenced: {label}")
    print()
    print(
        f"PLACEHOLDERS  tbd={p['tbd_total_occurrences']}"
        f"  phfig={p['phfig_total_occurrences']}"
        f"  empirical-phfig floats={len(p['floats_with_phfig_empirical'])}"
        f"  conceptual-phfig floats={len(p['floats_with_phfig_conceptual'])}"
    )
    if "bibliography" in report:
        b = report["bibliography"]
        print()
        print(
            f"BIBLIOGRAPHY  defined={b['defined']}  cited={b['cited']}"
            f"  cited-but-undefined={len(b['cited_but_undefined'])}"
            f"  defined-but-uncited={len(b['defined_but_uncited'])}"
        )
        for key in b["cited_but_undefined"]:
            print(f"    MISSING bib entry: {key}")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.json}")

    problems = (
        len(t["unmapped_in_manuscript"])
        + len(f["unmapped_in_manuscript"])
        + len(report.get("bibliography", {}).get("cited_but_undefined", []))
    )
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
