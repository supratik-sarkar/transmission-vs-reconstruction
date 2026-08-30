from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import load_settings
from .integrity import verify_freeze
from .private_guard import PrivateBoundaryError, assert_private_workspace
from .runner import ProtocolNotFrozenError, run_stage1
from .selftest import run_design_selftests

app = typer.Typer(no_args_is_help=True, help="Transmission-vs-reconstruction research CLI")
protocol_app = typer.Typer(help="Protocol integrity commands")
app.add_typer(protocol_app, name="protocol")
console = Console()


@app.command()
def doctor() -> None:
    settings = load_settings()
    private_home = settings.private_home.expanduser()
    settings.ensure_private_dirs()
    table = Table(title="Handoff Fidelity Doctor")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Private home", str(private_home))
    table.add_row("Relay provider/model", f"{settings.relay_provider} / {settings.relay_model}")
    table.add_row(
        "Receiver provider/model", f"{settings.receiver_provider} / {settings.receiver_model}"
    )
    table.add_row("Private .env", str(settings.env_file()))
    try:
        assert_private_workspace(private_home, Path.cwd())
        boundary = "PASS"
    except PrivateBoundaryError as exc:
        boundary = f"FAIL: {exc}"
    table.add_row("Public/private boundary", boundary)
    frozen, failures = verify_freeze(private_home)
    table.add_row("Binding freeze", "PASS" if frozen else "NOT READY")
    if failures:
        table.add_row("Freeze details", "; ".join(failures))
    console.print(table)


@app.command("self-test")
def self_test() -> None:
    results = run_design_selftests()
    for name, result in results.items():
        console.print(f"[green]{result}[/green] {name}")


@app.command()
def stage1(
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; make no provider calls."),
    execute: bool = typer.Option(False, "--execute", help="Attempt real Stage-1 execution."),
) -> None:
    if dry_run == execute:
        raise typer.BadParameter("Choose exactly one of --dry-run or --execute")
    settings = load_settings()
    try:
        plan = run_stage1(settings, execute=execute)
    except ProtocolNotFrozenError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    except NotImplementedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=3) from exc
    console.print(
        f"Stage={plan.stage}, documents={plan.documents}, k={plan.focal_atoms_per_document}, "
        f"execute={plan.execute}. No model call made."
    )


@protocol_app.command("verify")
def protocol_verify(
    private_home: Path | None = typer.Option(None, help="Override private workspace path."),
) -> None:
    settings = load_settings()
    home = (private_home or settings.private_home).expanduser()
    ok, failures = verify_freeze(home)
    if ok:
        console.print("[green]PASS[/green] binding freeze record verified")
        return
    console.print("[red]NOT READY[/red]")
    for failure in failures:
        console.print(f" - {failure}")
    raise typer.Exit(code=2)
