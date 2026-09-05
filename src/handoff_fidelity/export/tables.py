"""LaTeX table fragment generation.

Every empirical table in the manuscript is produced here from structured result
artefacts. No number is typed into LaTeX by hand -- that is the rule the
manuscript guard enforces.

Cell formatting, including which cell is bold, is decided by the frozen metric
direction, not by a human editing the table after seeing the results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: manuscript label -> generated fragment filename
TABLE_TARGETS: dict[str, str] = {
    "tab:setup": "setup.tex",
    "tab:benchmark-main": "benchmark_main.tex",
    "tab:benchmark-full": "benchmark_full.tex",
    "tab:baseline-fidelity": "baseline_fidelity.tex",
    "tab:full-A": "full_A.tex",
    "tab:weighted": "weighted.tex",
    "tab:full-B": "full_B.tex",
    "tab:full-C": "full_C.tex",
    "tab:sweeps": "sweeps.tex",
}

#: Tables that carry NO empirical result and therefore have no exporter.
#: They are written once by hand and are correct by construction: an eligibility
#: rule, a dependency map, a notation index, a table of pre-registered values.
#: Without this declaration the contract checker cannot distinguish "this table
#: has no exporter because it is a notation index" from "this table has no
#: exporter because we forgot to write one", which is the whole point of
#: checking.
STATIC_STRUCTURAL_TABLES: frozenset[str] = frozenset(
    {
        "tab:baseline-eligibility",  # inclusion rule, not a measurement
        "tab:depmap",  # formal-object dependency map
        "tab:notation-a",  # notation index
        "tab:notation-b",  # notation index
        "tab:prereg",  # pre-registered values, fixed before any run
    }
)

#: Frozen metric directions. "up" means larger is better.
METRIC_DIRECTION: dict[str, str] = {
    "A": "up",
    "C_comm": "up",
    "C_recon": "down",
    "alignment": "up",
    "tokens": "none",
    "latency_ms": "down",
}

LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape(text: str) -> str:
    return "".join(LATEX_ESCAPES.get(ch, ch) for ch in str(text))


def fmt(value: Any, places: int = 3) -> str:
    if value is None:
        return "---"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return escape(value)


def fmt_interval(point: float | None, lo: float | None, hi: float | None, places: int = 3) -> str:
    if point is None:
        return "---"
    if lo is None or hi is None:
        return fmt(point, places)
    return f"{point:.{places}f} [{lo:.{places}f}, {hi:.{places}f}]"


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    header: str
    metric: str | None = None
    places: int = 3


def _best_index(rows: Sequence[Mapping[str, Any]], col: Column) -> int | None:
    if col.metric is None:
        return None
    direction = METRIC_DIRECTION.get(col.metric, "none")
    if direction == "none":
        return None
    values: list[tuple[int, float]] = [
        (i, float(v))
        for i, r in enumerate(rows)
        if (v := r.get(col.key)) is not None and isinstance(v, int | float)
    ]
    if not values:
        return None
    return (max if direction == "up" else min)(values, key=lambda kv: kv[1])[0]


def render_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Column],
    *,
    label: str,
    caption: str = "",
    row_key: str = "method",
    bold_best: bool = True,
) -> str:
    """Emit a booktabs tabular fragment.

    Boldface is assigned by the frozen metric direction after the analysis has
    read real outputs; no manual table editing is permitted once results are
    known.
    """
    best = {c.key: (_best_index(rows, c) if bold_best else None) for c in columns}
    spec = "l" + "c" * len(columns)
    out = [
        "% GENERATED FILE -- do not edit by hand.",
        f"% label: {label}",
    ]
    if caption:
        out.append(f"% caption: {caption}")
    out += [
        r"\begin{tabular}{" + spec + "}",
        r"\toprule",
        escape(row_key.replace("_", " ").title())
        + " & "
        + " & ".join(c.header for c in columns)
        + r" \\",
        r"\midrule",
    ]
    for i, row in enumerate(rows):
        cells = []
        for c in columns:
            text = fmt(row.get(c.key), c.places)
            if best.get(c.key) == i and text != "---":
                text = r"\textbf{" + text + "}"
            cells.append(text)
        out.append(escape(str(row.get(row_key, ""))) + " & " + " & ".join(cells) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(out)


def write_fragment(text: str, out_dir: Path, filename: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


BENCHMARK_COLUMNS: tuple[Column, ...] = (
    Column("A", r"$A\uparrow$", "A"),
    Column("C_comm", r"$C_{\mathrm{comm}}\uparrow$", "C_comm"),
    Column("C_recon", r"$C_{\mathrm{recon}}\downarrow$", "C_recon"),
    Column("alignment", r"$\mathrm{Cov}(T,\Delta)\uparrow$", "alignment"),
    Column("tokens", "Tok.", "tokens", 0),
)

FULL_A_COLUMNS: tuple[Column, ...] = (
    Column("n", "$n$", None, 0),
    Column("T_bar", r"$\bar T$", None),
    Column("r_minus", "$R^-$", None),
    Column("d_plus", "$D^+$", None),
    Column("delta", r"$\Delta^{\mathrm{av}}$", None),
    Column("p_delta_neg", r"$\Pr[\Delta<0]$", None),
)
