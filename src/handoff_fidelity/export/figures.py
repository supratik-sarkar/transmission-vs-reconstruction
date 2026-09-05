"""Figure generation.

Every plotting function consumes STRUCTURED RESULT ARTEFACTS. None accepts a
hand-entered number, and none invents data: passing an empty result set raises
rather than drawing an illustrative curve.

For dry-run testing use ``synthetic_fixture`` -- its output is stamped
SYNTHETIC TEST FIXTURE directly onto the canvas so a fixture plot can never be
mistaken for a result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: manuscript label -> generated figure filename
FIGURE_TARGETS: dict[str, str] = {
    "fig:decomp-bars": "decomposition_bars.pdf",
    "fig:selbias": "selection_bias_scatter.pdf",
    "fig:dose": "prior_dose_response.pdf",
    "fig:matched": "matched_prior_contrast.pdf",
    "fig:placebo": "placebo_sensitivity.pdf",
    "fig:allocation": "allocation_scatter.pdf",
    "fig:depth": "depth_curves.pdf",
    "fig:gallery": "qualitative_gallery.pdf",
}

#: Conceptual figures are drawn once by hand and are NOT experimental outputs.
#: The manuscript guard must not demand a generated file for them.
STATIC_CONCEPTUAL_FIGURES: frozenset[str] = frozenset(
    {"fig:hero", "fig:flow", "fig:appendix-workflow"}
)

#: Labels that live inside a float environment but are not themselves an
#: exportable figure: the parent label of a subfigure pair, and the algorithm
#: float, which uses a figure container only for placement. Each of these has
#: child labels that DO map to exporters.
CONTAINER_FLOAT_LABELS: frozenset[str] = frozenset(
    {
        "fig:main",  # parent of fig:decomp-bars and fig:selbias
        "fig:prior",  # parent of fig:dose and fig:matched
        "alg:protocol",  # algorithm float, not a figure
    }
)

SYNTHETIC_STAMP = "SYNTHETIC TEST FIXTURE -- NOT A RESULT"


class NoResultsError(ValueError):
    """Raised when a plotting function is called with no data. Deliberately
    fatal: a plausible-looking placebo curve is worse than a missing figure."""


@dataclass(frozen=True, slots=True)
class FigureSpec:
    label: str
    filename: str
    synthetic: bool = False


def _plt():
    try:
        import matplotlib  # noqa: PLC0415

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415

        return plt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required for figure export") from exc


def _finish(fig, path: Path, synthetic: bool) -> Path:
    if synthetic:
        fig.text(
            0.5,
            0.5,
            SYNTHETIC_STAMP,
            ha="center",
            va="center",
            fontsize=16,
            color="red",
            alpha=0.30,
            rotation=25,
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    _plt().close(fig)
    return path


def decomposition_bars(
    rows: Sequence[Mapping[str, Any]], path: Path, *, synthetic: bool = False
) -> Path:
    """Stacked A = Rbar_0 + Tbar*Deltabar + Cov(T,Delta), one bar per
    relay-receiver pair, with bootstrap error bars."""
    if not rows:
        raise NoResultsError("decomposition_bars requires at least one result row")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    labels = [str(r["label"]) for r in rows]
    r0 = [float(r["r_bar_zero"]) for r in rows]
    vol = [float(r["volume"]) for r in rows]
    align = [float(r["alignment"]) for r in rows]
    x = range(len(rows))
    ax.bar(x, r0, label=r"$\bar R_0$ reconstruction")
    ax.bar(x, vol, bottom=r0, label=r"$\bar T\bar\Delta$ volume")
    ax.bar(x, align, bottom=[a + b for a, b in zip(r0, vol, strict=False)], label="alignment")
    if all("a_lower" in r and "a_upper" in r for r in rows):
        a = [float(r["endpoint_fidelity"]) for r in rows]
        lo = [a[i] - float(rows[i]["a_lower"]) for i in range(len(rows))]
        hi = [float(rows[i]["a_upper"]) - a[i] for i in range(len(rows))]
        ax.errorbar(list(x), a, yerr=[lo, hi], fmt="k.", capsize=3, label="A (95% CI)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("endpoint fidelity")
    ax.legend(fontsize=7, frameon=False)
    return _finish(fig, path, synthetic)


def selection_bias_scatter(
    rows: Sequence[Mapping[str, Any]], path: Path, *, synthetic: bool = False
) -> Path:
    """R_obs against Rbar_0 per atom class with the 45-degree line; the signed
    vertical distance IS the selection bias."""
    if not rows:
        raise NoResultsError("selection_bias_scatter requires result rows")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.0, 3.6))
    xs = [float(r["r_bar_zero"]) for r in rows]
    ys = [float(r["r_observational"]) for r in rows]
    ax.scatter(xs, ys)
    for r, x, y in zip(rows, xs, ys, strict=False):
        ax.annotate(
            str(r.get("label", "")), (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points"
        )
    lo = min(xs + ys + [0.0])
    hi = max(xs + ys + [1.0])
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8)
    ax.set_xlabel(r"$\bar R_0$ (design-weighted)")
    ax.set_ylabel(r"$R^{\mathrm{obs}} = E[R^-\mid T=0]$")
    return _finish(fig, path, synthetic)


def prior_dose_response(
    bins: Sequence[str],
    means: Sequence[float],
    counts: Sequence[int],
    path: Path,
    *,
    chance: Mapping[str, float] | None = None,
    synthetic: bool = False,
) -> Path:
    """Reliability-aware stratification, NOT a slope on a mismeasured
    regressor. Per-class chance lines are drawn separately because a pooled
    chance level is not interpretable."""
    if not bins:
        raise NoResultsError("prior_dose_response requires bins")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    ax.bar(range(len(bins)), list(means))
    for i, c in enumerate(counts):
        ax.annotate(f"n={c}", (i, 0.02), ha="center", fontsize=7)
    for name, level in (chance or {}).items():
        ax.axhline(level, linestyle=":", linewidth=0.8)
        ax.annotate(f"chance {name} = 1/K_eff", (0, level), fontsize=6, va="bottom")
    ax.set_xticks(range(len(bins)))
    ax.set_xticklabels(list(bins))
    ax.set_xlabel("measured closed-book prior access (binned)")
    ax.set_ylabel(r"$R^-$")
    return _finish(fig, path, synthetic)


def matched_prior_contrast(
    rows: Sequence[Mapping[str, Any]], path: Path, *, gate: float = 0.10, synthetic: bool = False
) -> Path:
    if not rows:
        raise NoResultsError("matched_prior_contrast requires result rows")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    labels = [str(r["label"]) for r in rows]
    point = [float(r["point"]) for r in rows]
    lo = [float(r["point"]) - float(r["lower"]) for r in rows]
    hi = [float(r["upper"]) - float(r["point"]) for r in rows]
    ax.errorbar(range(len(rows)), point, yerr=[lo, hi], fmt="o", capsize=3)
    ax.axhline(gate, linestyle="--", linewidth=0.9)
    ax.annotate(f"pre-registered {gate:.2f} discovery gate", (0, gate), fontsize=7, va="bottom")
    ax.axhline(0.0, color="k", linewidth=0.6)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel(r"$\Delta R^{\mathrm{m}}_{\mathrm{prior}}$")
    return _finish(fig, path, synthetic)


def placebo_sensitivity(
    regions: Sequence[Mapping[str, Any]], path: Path, *, synthetic: bool = False
) -> Path:
    """Partial-identification width as a function of the assumed bound on the
    residual semantic artefact."""
    if not regions:
        raise NoResultsError("placebo_sensitivity requires regions")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.4, 3.4))
    for mech in sorted({str(r["mechanism"]) for r in regions}):
        sub = sorted(
            (r for r in regions if r["mechanism"] == mech), key=lambda r: float(r["epsilon_bar"])
        )
        eb = [float(r["epsilon_bar"]) for r in sub]
        ax.fill_between(
            eb,
            [float(r["lower"]) for r in sub],
            [float(r["upper"]) for r in sub],
            alpha=0.25,
            label=f"{mech} region",
        )
        ax.plot(eb, [float(r["point_corrected"]) for r in sub], label=f"{mech} corrected")
    ax.axhline(0.0, color="k", linewidth=0.6)
    ax.set_xlabel(r"assumed bound $\bar\varepsilon$ on the residual semantic artefact")
    ax.set_ylabel(r"$\bar\Delta$ region")
    ax.legend(fontsize=7, frameon=False)
    return _finish(fig, path, synthetic)


def allocation_scatter(
    rows: Sequence[Mapping[str, Any]],
    path: Path,
    *,
    eta_u: float | None = None,
    synthetic: bool = False,
) -> Path:
    """T_z against Delta^bu_z. Delta^av is deliberately NOT used here."""
    if not rows:
        raise NoResultsError("allocation_scatter requires result rows")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    ax.scatter(
        [float(r["delta_budget"]) for r in rows],
        [float(r["transmitted"]) for r in rows],
        alpha=0.6,
        s=14,
    )
    ax.axvline(0.0, color="k", linewidth=0.6)
    ax.set_xlabel(r"$\Delta^{\mathrm{bu}}_z$ (budget-neutral surplus)")
    ax.set_ylabel(r"$T_z$")
    if eta_u is not None:
        ax.annotate(rf"$\eta_U={eta_u:.3f}$", (0.03, 0.88), xycoords="axes fraction", fontsize=9)
    return _finish(fig, path, synthetic)


def depth_curves(
    series: Mapping[str, Sequence[Mapping[str, Any]]], path: Path, *, synthetic: bool = False
) -> Path:
    """A^(h) and Tbar^(h) plotted TOGETHER. Reporting A^(h) alone would be
    precisely the error this project is about."""
    if not series:
        raise NoResultsError("depth_curves requires at least one method series")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    for method, points in sorted(series.items()):
        pts = sorted(points, key=lambda p: int(p["hop"]))
        hops = [int(p["hop"]) for p in pts]
        ax.plot(hops, [float(p["A"]) for p in pts], marker="o", label=f"{method}: $A^{{(h)}}$")
        ax.plot(
            hops,
            [float(p["T_bar"]) for p in pts],
            marker="s",
            linestyle="--",
            label=rf"{method}: $\bar T^{{(h)}}$",
        )
    ax.set_xlabel("handoff depth $h$")
    ax.set_ylabel("value")
    ax.legend(fontsize=6, frameon=False, ncol=2)
    return _finish(fig, path, synthetic)


def qualitative_gallery(
    cases: Sequence[Mapping[str, Any]], path: Path, *, synthetic: bool = False
) -> Path:
    """Qualitative side-by-side gallery of natural vs counterfactual handoffs
    and receiver reconstructions."""
    if not cases:
        raise NoResultsError("qualitative_gallery requires at least one case")
    plt = _plt()
    n_cases = len(cases)
    fig, axes = plt.subplots(n_cases, 1, figsize=(6.5, 2.0 * n_cases), squeeze=False)
    for i, case in enumerate(cases):
        ax = axes[i, 0]
        ax.axis("off")
        title = str(case.get("title", f"Case {i + 1}"))
        source = str(case.get("source_excerpt", ""))
        natural = str(case.get("natural_handoff", ""))
        cf = str(case.get("counterfactual_handoff", ""))
        text = (
            f"[{title}]\n"
            f"Source: {source}\n"
            f"Natural message: {natural}\n"
            f"Counterfactual message: {cf}\n"
            f"Outcome: {case.get('outcome', '')}"
        )
        ax.text(
            0.02,
            0.95,
            text,
            va="top",
            ha="left",
            fontsize=7.5,
            family="monospace",
            transform=ax.transAxes,
            bbox={
                "boxstyle": "round,pad=0.5",
                "facecolor": "#f5f5f5",
                "edgecolor": "#cccccc",
            },
        )
    return _finish(fig, path, synthetic)


def synthetic_fixture(path: Path) -> Path:
    """A clearly-stamped fixture for dry-run testing of the export path."""
    rows = [
        {
            "label": "fixture-A",
            "endpoint_fidelity": 0.62,
            "r_bar_zero": 0.30,
            "volume": 0.24,
            "alignment": 0.08,
        },
        {
            "label": "fixture-B",
            "endpoint_fidelity": 0.55,
            "r_bar_zero": 0.35,
            "volume": 0.18,
            "alignment": 0.02,
        },
    ]
    return decomposition_bars(rows, path, synthetic=True)
