"""Table generation and the manuscript readiness guard."""

from __future__ import annotations

import tempfile
from pathlib import Path

from handoff_fidelity.export.figures import (
    FIGURE_TARGETS,
    STATIC_CONCEPTUAL_FIGURES,
    NoResultsError,
)
from handoff_fidelity.export.manuscript_check import check_manuscript
from handoff_fidelity.export.tables import (
    BENCHMARK_COLUMNS,
    METRIC_DIRECTION,
    TABLE_TARGETS,
    Column,
    escape,
    fmt_interval,
    render_table,
    write_fragment,
)
from handoff_fidelity.provenance.results_manifest import ResultEntry, ResultsManifest

from ._support import raises

ROWS = [
    {
        "method": "head_truncation",
        "A": 0.40,
        "C_comm": 0.10,
        "C_recon": 0.30,
        "alignment": 0.01,
        "tokens": 500,
    },
    {
        "method": "causalrelay",
        "A": 0.60,
        "C_comm": 0.25,
        "C_recon": 0.15,
        "alignment": 0.05,
        "tokens": 498,
    },
]


def test_bold_follows_the_frozen_metric_direction():
    """Boldface is assigned by direction, not by a human editing the table
    after seeing results."""
    out = render_table(ROWS, BENCHMARK_COLUMNS, label="tab:x", caption="c")
    lines = [ln for ln in out.splitlines() if "causalrelay" in ln]
    assert r"\textbf{0.600}" in lines[0], "higher A should be bold"
    assert r"\textbf{0.150}" in lines[0], "lower C_recon should be bold"


def test_lower_is_better_metrics_bold_the_minimum():
    assert METRIC_DIRECTION["C_recon"] == "down"
    assert METRIC_DIRECTION["A"] == "up"
    out = render_table(ROWS, [Column("C_recon", "recon", "C_recon")], label="t", caption="c")
    assert r"\textbf{0.150}" in out


def test_no_bold_for_directionless_columns():
    out = render_table(ROWS, [Column("tokens", "tok", "tokens", 0)], label="t", caption="c")
    assert r"\textbf" not in out


def test_missing_values_render_as_a_dash_not_a_number():
    out = render_table([{"method": "m"}], BENCHMARK_COLUMNS, label="t", caption="c")
    assert "---" in out
    assert "0.000" not in out


def test_latex_special_characters_are_escaped():
    assert escape("a_b & c%") == r"a\_b \& c\%"


def test_interval_formatting():
    assert fmt_interval(0.5, 0.4, 0.6) == "0.500 [0.400, 0.600]"
    assert fmt_interval(None, None, None) == "---"


def test_every_manuscript_table_label_has_a_target():
    for label in (
        "tab:benchmark-main",
        "tab:benchmark-full",
        "tab:full-A",
        "tab:full-B",
        "tab:full-C",
        "tab:weighted",
        "tab:sweeps",
        "tab:setup",
        "tab:baseline-fidelity",
    ):
        assert label in TABLE_TARGETS


def test_every_empirical_figure_label_has_a_target():
    for label in (
        "fig:decomp-bars",
        "fig:selbias",
        "fig:dose",
        "fig:matched",
        "fig:placebo",
        "fig:allocation",
        "fig:depth",
        "fig:gallery",
    ):
        assert label in FIGURE_TARGETS


def test_conceptual_figures_are_not_expected_to_be_generated():
    """Demanding a generated file for a hand-drawn schematic would push toward
    fabricating one."""
    assert "fig:hero" in STATIC_CONCEPTUAL_FIGURES
    assert "fig:hero" not in FIGURE_TARGETS


def test_figure_functions_refuse_empty_input():
    from handoff_fidelity.export.figures import decomposition_bars

    with raises(NoResultsError):
        decomposition_bars([], Path(tempfile.mkdtemp()) / "x.pdf")


def _write_tex(root: Path, body: str) -> Path:
    path = root / "paper.tex"
    path.write_text(body, encoding="utf-8")
    return path


def test_guard_fails_on_unresolved_placeholders():
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(root, r"Result: \tbd" + "\n")
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f")
    assert result.ok is False
    assert any("tbd" in f for f in result.failures)


def test_guard_distinguishes_conceptual_from_experimental_placeholders():
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(
        root,
        r"""
\begin{figure}\phfig{3cm}{schematic}\label{fig:hero}\end{figure}
\begin{figure}\phfig{3cm}{bars}\label{fig:decomp-bars}\end{figure}
""",
    )
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f")
    assert result.ok is False
    assert any("fig:decomp-bars" in f for f in result.failures)
    assert all("fig:hero" not in f for f in result.failures)
    assert any("fig:hero" in w for w in result.warnings)


def test_guard_reports_missing_generated_fragments():
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(root, r"\label{tab:benchmark-main}" + "\n")
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f")
    assert any("benchmark_main.tex" in f for f in result.failures)


def test_guard_passes_when_everything_is_present():
    root = Path(tempfile.mkdtemp())
    tables = root / "tables"
    figures = root / "figures"
    write_fragment("x", tables, "benchmark_main.tex")
    figures.mkdir(parents=True, exist_ok=True)
    (figures / "decomposition_bars.pdf").write_bytes(b"%PDF-1.4")
    tex = _write_tex(root, r"\label{tab:benchmark-main} \label{fig:decomp-bars}" + "\n")

    manifest = ResultsManifest()
    for artifact in ("tables/benchmark_main.tex", "figures/decomposition_bars.pdf"):
        manifest.add(
            ResultEntry(
                artifact=artifact,
                kind="table",
                run_ids=["r1"],
                source_hashes=["s1"],
                config_hashes=["c1"],
                model_revisions={"receiver": "v1"},
                artifact_sha256="0" * 64,
            )
        )
    manifest_path = root / "RESULTS_MANIFEST.json"
    manifest.write(manifest_path)

    result = check_manuscript(
        tex, tables_dir=tables, figures_dir=figures, results_manifest=manifest_path
    )
    assert result.ok is True, result.report()


def test_guard_fails_when_an_asset_lacks_provenance():
    root = Path(tempfile.mkdtemp())
    tables = root / "tables"
    write_fragment("x", tables, "benchmark_main.tex")
    tex = _write_tex(root, r"\label{tab:benchmark-main}" + "\n")
    manifest = ResultsManifest()
    manifest.add(ResultEntry(artifact="tables/benchmark_main.tex", kind="table"))
    manifest_path = root / "RESULTS_MANIFEST.json"
    manifest.write(manifest_path)
    result = check_manuscript(
        tex, tables_dir=tables, figures_dir=root / "f", results_manifest=manifest_path
    )
    assert result.ok is False
    assert any("provenance" in f for f in result.failures)


def test_guard_detects_undefined_references_in_the_build_log():
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(root, "clean\n")
    log = root / "paper.log"
    log.write_text("LaTeX Warning: Citation `foo' undefined on page 3.\n", encoding="utf-8")
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f", log_path=log)
    assert result.ok is False
    assert any("undefined" in f for f in result.failures)


def test_pre_run_mode_reports_without_failing():
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(root, r"\tbd \label{tab:benchmark-main}" + "\n")
    result = check_manuscript(
        tex, tables_dir=root / "t", figures_dir=root / "f", require_empirical=False
    )
    assert result.ok is True
    assert result.counts["tbd_placeholders"] == 1


def test_all_empirical_figures_render_cleanly():
    from handoff_fidelity.export import figures as figs

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        p1 = figs.decomposition_bars(
            [
                {
                    "label": "M1",
                    "r_bar_zero": 0.3,
                    "volume": 0.2,
                    "alignment": 0.1,
                    "endpoint_fidelity": 0.6,
                    "a_lower": 0.55,
                    "a_upper": 0.65,
                }
            ],
            tmp / "decomp.pdf",
            synthetic=True,
        )
        assert p1.exists()

        p2 = figs.selection_bias_scatter(
            [{"label": "M1", "r_bar_zero": 0.3, "r_observational": 0.35}],
            tmp / "selbias.pdf",
            synthetic=True,
        )
        assert p2.exists()

        p3 = figs.prior_dose_response(
            bins=["[0, 0.2)", "[0.2, 0.5)"],
            means=[0.1, 0.4],
            counts=[50, 100],
            path=tmp / "dose.pdf",
            chance={"c1": 0.1},
            synthetic=True,
        )
        assert p3.exists()

        p4 = figs.matched_prior_contrast(
            [{"label": "M1", "point": 0.15, "lower": 0.10, "upper": 0.20}],
            tmp / "matched.pdf",
            synthetic=True,
        )
        assert p4.exists()

        p5 = figs.placebo_sensitivity(
            [
                {
                    "mechanism": "sham_del",
                    "epsilon_bar": 0.01,
                    "lower": 0.05,
                    "upper": 0.15,
                    "point_corrected": 0.10,
                }
            ],
            tmp / "placebo.pdf",
            synthetic=True,
        )
        assert p5.exists()

        p6 = figs.allocation_scatter(
            [{"delta_budget": 0.2, "transmitted": 1.0}],
            tmp / "allocation.pdf",
            eta_u=0.45,
            synthetic=True,
        )
        assert p6.exists()

        p7 = figs.depth_curves(
            {"M1": [{"hop": 1, "A": 0.8, "T_bar": 0.7}]},
            tmp / "depth.pdf",
            synthetic=True,
        )
        assert p7.exists()

        p8 = figs.qualitative_gallery(
            [
                {
                    "title": "Test Case",
                    "source_excerpt": "src",
                    "natural_handoff": "nat",
                    "counterfactual_handoff": "cf",
                    "outcome": "pass",
                }
            ],
            tmp / "gallery.pdf",
            synthetic=True,
        )
        assert p8.exists()


# --- manuscript contract classification (RC-0.1) ---------------------------


def test_static_structural_tables_are_declared_and_disjoint():
    """A notation index and a dependency map carry no measurement, so they have
    no exporter. Declaring them is what lets the checker tell 'no exporter
    because it is a notation index' from 'no exporter because we forgot'."""
    from handoff_fidelity.export.tables import STATIC_STRUCTURAL_TABLES

    assert STATIC_STRUCTURAL_TABLES
    assert not (STATIC_STRUCTURAL_TABLES & set(TABLE_TARGETS)), (
        "a table cannot be both statically written and machine-generated"
    )
    for label in (
        "tab:notation-a",
        "tab:notation-b",
        "tab:depmap",
        "tab:prereg",
        "tab:baseline-eligibility",
    ):
        assert label in STATIC_STRUCTURAL_TABLES


def test_container_float_labels_are_declared_and_disjoint():
    from handoff_fidelity.export.figures import CONTAINER_FLOAT_LABELS

    assert {"fig:main", "fig:prior", "alg:protocol"} <= CONTAINER_FLOAT_LABELS
    assert not (CONTAINER_FLOAT_LABELS & set(FIGURE_TARGETS))
    assert not (CONTAINER_FLOAT_LABELS & STATIC_CONCEPTUAL_FIGURES)


def test_guard_does_not_demand_a_file_for_a_subfigure_parent():
    """fig:main is the parent of fig:decomp-bars and fig:selbias. Its float
    carries their placeholders; it is not itself an exportable figure."""
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(
        root,
        r"""
\begin{figure}
\phfig{2cm}{left}\label{fig:decomp-bars}
\phfig{2cm}{right}\label{fig:selbias}
\label{fig:main}
\end{figure}
""",
    )
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f")
    assert all("fig:main" not in f for f in result.failures)
    assert any("fig:decomp-bars" in f for f in result.failures)


def test_guard_acknowledges_static_structural_tables():
    """A reader of the report must be able to tell that a static table was
    considered and exempted, not overlooked. The conceptual-figure notes already
    do this; the table side was silent."""
    root = Path(tempfile.mkdtemp())
    tex = _write_tex(root, r"\label{tab:notation-a} \label{tab:depmap}" + "\n")
    result = check_manuscript(tex, tables_dir=root / "t", figures_dir=root / "f")
    assert result.ok is True, result.report()
    assert result.counts["static_structural_tables_ok"] == 2
    assert any("tab:notation-a" in w and "static structural" in w for w in result.warnings)
