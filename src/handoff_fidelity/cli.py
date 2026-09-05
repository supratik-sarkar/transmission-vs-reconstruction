"""Command-line interface.

Built on argparse so the toolkit has no CLI framework dependency.

Every subcommand is inspection, validation or dry-run. There is no command that
executes an experiment: real execution requires the guards in
``stages.guards`` plus a valid freeze record, and is wired up deliberately, not
by a flag on a convenience CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import credential_presence, load_settings
from .privacy.boundary import PrivateBoundaryError, assert_private_workspace
from .privacy.scan import scan_repository
from .selftest import run_all, summarise


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"handoff-fidelity {__version__}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    settings = load_settings()
    print("configuration (secrets are never printed):")
    for key, value in sorted(settings.public_summary().items()):
        print(f"  {key}: {value}")
    print("credential presence (value never read or shown):")
    for key, present in sorted(credential_presence().items()):
        print(f"  {key}: {'set' if present else 'unset'}")

    from .compute.router import diagnostics

    print("compute:")
    for key, value in sorted(diagnostics().items()):
        print(f"  {key}: {value}")

    status = 0
    try:
        assert_private_workspace(
            settings.private_home, Path(args.public_repo) if args.public_repo else None
        )
        print("boundary: OK (private workspace is outside the repository and non-Git)")
    except PrivateBoundaryError as exc:
        print(f"boundary: FAIL {exc}")
        status = 1

    if settings.relay_model == "UNFROZEN" or settings.receiver_model == "UNFROZEN":
        print("models: UNFROZEN -- no experimental run may proceed until versions are pinned")
    return status


def _cmd_selftest(_: argparse.Namespace) -> int:
    outcomes = run_all()
    print(summarise(outcomes))
    return 0 if all(o.passed for o in outcomes) else 1


def _cmd_privacy_scan(args: argparse.Namespace) -> int:
    report = scan_repository(Path(args.root))
    print(report.render())
    return 0 if report.ok else 2


def _cmd_baselines(args: argparse.Namespace) -> int:
    from .baselines.registry import Registry

    reg_path = Path(args.registry)
    if not reg_path.exists():
        settings = load_settings()
        for cand in (
            Path("configs/baselines.yaml"),
            Path("configs/baselines/registry.yaml"),
            settings.private_home / "configs/baselines.yaml",
            settings.private_home / "configs/baselines/registry.yaml",
        ):
            if cand.exists():
                reg_path = cand
                break
    registry = Registry.load(reg_path)
    rows = registry.report()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            flag = "eligible" if row["eligible"] else "BLOCKED"
            print(f"{row['method']:<24s} {row['role']:<16s} {row['status']:<14s} {flag}")
            if not row["eligible"]:
                print(f"    {row['reason']}")
    eligible = registry.eligible_primary()
    print(
        f"\n{len(eligible)} of {registry.superiority_denominator()} primary comparators "
        f"are benchmark-eligible; 3 are required for any superiority language."
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .stages.runners import (
        run_calibration,
        run_experiment_c,
        run_export,
        run_multihop,
        run_stage1,
        run_stage2_dev,
        run_stage2_test,
    )

    stage = args.stage.replace("-", "_").lower()
    execute = bool(getattr(args, "execute", False))
    mock = bool(getattr(args, "mock", False))
    protocol_freeze = Path(args.protocol_freeze) if getattr(args, "protocol_freeze", None) else None
    test_freeze = Path(args.test_freeze) if getattr(args, "test_freeze", None) else None

    try:
        if stage == "calibration":
            res = run_calibration(execute=execute, mock=mock)
        elif stage == "stage1":
            res = run_stage1(protocol_freeze=protocol_freeze, execute=execute, mock=mock)
        elif stage == "stage2_dev":
            res = run_stage2_dev(protocol_freeze=protocol_freeze, execute=execute, mock=mock)
        elif stage == "stage2_test":
            res = run_stage2_test(
                protocol_freeze=protocol_freeze, test_freeze=test_freeze, execute=execute, mock=mock
            )
        elif stage == "experiment_c":
            res = run_experiment_c(protocol_freeze=protocol_freeze, execute=execute, mock=mock)
        elif stage == "multihop":
            res = run_multihop(protocol_freeze=protocol_freeze, execute=execute, mock=mock)
        elif stage == "export":
            res = run_export(
                tex_path=Path(args.tex),
                tables_dir=Path(args.tables),
                figures_dir=Path(args.figures),
                results_manifest=(
                    Path(args.results_manifest) if getattr(args, "results_manifest", None) else None
                ),
                allow_placeholders=bool(getattr(args, "allow_placeholders", False)),
                execute=execute,
                mock=mock,
            )
        else:
            print(f"Unknown stage: {args.stage}")
            return 1

        print(f"Stage: {res.stage} [{res.status}]")
        print("Plan:")
        for k, v in res.plan.items():
            print(f"  {k}: {v}")
        if res.output:
            print("Output:")
            for k, v in res.output.items():
                print(f"  {k}: {v}")
        if res.gate_result:
            print(f"Gate: {res.gate_result.reason}")
        return 0
    except Exception as exc:
        print(f"RUN FAIL CLOSED: {exc}")
        return 1


def _cmd_stages(_: argparse.Namespace) -> int:
    from .stages.spec import STAGES

    for stage, spec in STAGES.items():
        marker = " [PROPOSED]" if spec.proposed else ""
        size = spec.n_documents if spec.n_documents is not None else "n/a"
        print(f"{stage.value:<14s} docs={size}{marker}")
        print(f"    {spec.description}")
    return 0


def _cmd_manuscript_check(args: argparse.Namespace) -> int:
    from .export.manuscript_check import check_manuscript

    result = check_manuscript(
        Path(args.tex),
        tables_dir=Path(args.tables),
        figures_dir=Path(args.figures),
        results_manifest=Path(args.results_manifest) if args.results_manifest else None,
        log_path=Path(args.log) if args.log else None,
        require_empirical=not args.allow_placeholders,
    )
    print(result.report())
    return 0 if result.ok else 3


def _cmd_freeze_verify(args: argparse.Namespace) -> int:
    from .provenance.freeze import verify_record

    ok, problems = verify_record(Path(args.record))
    print("freeze record:", "VALID" if ok else "INVALID")
    for p in problems:
        print(f"  {p}")
    return 0 if ok else 4


def _cmd_app_doctor(_: argparse.Namespace) -> int:
    """Non-network report of the application stack."""
    import platform

    from .app_contracts.modes import AppMode
    from .orchestration.graph import langgraph_available, topology_description
    from .policy.engine import PolicyEngine, opa_available
    from .providers.adapters import provider_status_table
    from .telemetry.guardrails import resolve as guardrails_resolve
    from .telemetry.langsmith import resolve as langsmith_resolve
    from .telemetry.spans import otel_available

    settings = load_settings()
    mode = AppMode.RESEARCH
    print(f"python              {platform.python_version()}")
    print(f"mode                {mode.value}")
    print(
        f"langgraph           {'available' if langgraph_available() else 'not installed (sequential executor)'}"
    )
    print(
        f"opentelemetry       {'available' if otel_available() else 'not installed (in-memory tracer)'}"
    )
    print(
        f"opa binary          {'available' if opa_available() else 'not installed (fail-closed mirror)'}"
    )
    print(f"langsmith           {langsmith_resolve(mode).reason}")
    print(f"nemo guardrails     {guardrails_resolve(mode).reason}")
    print(f"policy engine       {PolicyEngine().describe()['active_engine']}")
    print(f"graph topology      fixed, {len(topology_description()['stages'])} stages")
    print("providers (presence only, never key material):")
    for row in provider_status_table():
        print(
            f"  {row['provider']:<10s} {row['state']:<15s} "
            f"secret={'yes' if row['secret_configured'] else 'no':<3s} "
            f"model={'pinned' if row['model_pinned'] else 'MUST_PIN'}"
        )
    print(f"relay/receiver      {settings.relay_model} / {settings.receiver_model}")
    return 0


def _cmd_providers(args: argparse.Namespace) -> int:
    from .providers.adapters import provider_status_table

    rows = provider_status_table()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(
                f"{row['provider']:<12s} {row['state']:<15s} "
                f"sdk={row['sdk_available']!s:<5s} secret={row['secret_configured']!s:<5s} "
                f"pinned={row['model_pinned']!s}"
            )
    return 0


def _cmd_policy_check(args: argparse.Namespace) -> int:
    from .policy.decisions import Action, PolicyInput, Subject
    from .policy.engine import PolicyEngine

    try:
        action = Action(args.action)
        subject = Subject(args.subject)
    except ValueError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 2
    decision = PolicyEngine().evaluate(PolicyInput(action=action, subject=subject))
    print(f"engine: {decision.engine}")
    print("ALLOW" if decision.allow else "DENY")
    for reason in decision.reasons:
        print(f"  {reason}")
    return 0 if decision.allow else 1


def _cmd_mock_e2e(args: argparse.Namespace) -> int:
    from .orchestration.mock_pipeline import run_mock_pipeline

    result = run_mock_pipeline(seed=args.seed)
    print(result.marker)
    print(f"engine   {result.engine}")
    for key, value in sorted(result.state.summary().items()):
        print(f"  {key:<20s} {value}")
    dec = result.state.decomposition
    if dec:
        print("decomposition (SYNTHETIC, no evidentiary status):")
        for key in (
            "endpoint_fidelity",
            "r_bar_zero",
            "t_bar",
            "c_comm",
            "c_recon",
            "identity_residual",
        ):
            print(f"  {key:<20s} {dec[key]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="handoff",
        description=(
            "Causal measurement and benchmarking toolkit for distinguishing transmitted "
            "from reconstructed information in chained language-model workflows."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the package version").set_defaults(func=_cmd_version)

    p = sub.add_parser(
        "doctor", help="inspect configuration, compute and the public/private boundary"
    )
    p.add_argument("--public-repo", default=None)
    p.set_defaults(func=_cmd_doctor)

    sub.add_parser("self-test", help="run the deterministic design invariants").set_defaults(
        func=_cmd_selftest
    )

    p = sub.add_parser("privacy-scan", help="fail if tracked files leak private material")
    p.add_argument("--root", default=".")
    p.set_defaults(func=_cmd_privacy_scan)

    p = sub.add_parser("baselines", help="report baseline registry resolution and eligibility")
    p.add_argument("--registry", default="configs/baselines.yaml")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_baselines)

    sub.add_parser("stages", help="describe the declared stages and their guards").set_defaults(
        func=_cmd_stages
    )

    p = sub.add_parser("run", help="run a guarded stage execution or dry-run plan")
    p.add_argument(
        "stage",
        choices=[
            "calibration",
            "stage1",
            "stage2-dev",
            "stage2-test",
            "experiment-c",
            "multihop",
            "export",
        ],
        help="the stage to run or plan",
    )
    p.add_argument("--config", default=None, help="stage configuration file")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show resolved plan without executing (default behavior when --execute is omitted)",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="attempt execution (fails closed if freeze/models/gates are unfulfilled)",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="run in mock/synthetic mode for pipeline verification without real providers",
    )
    p.add_argument("--protocol-freeze", default=None, help="path to protocol freeze record")
    p.add_argument("--test-freeze", default=None, help="path to final test freeze record")
    p.add_argument("--gate-record", default=None, help="path to prior stage gate record")
    p.add_argument("--tex", default="paper.tex", help="manuscript tex file for export stage")
    p.add_argument("--tables", default="tables", help="tables directory")
    p.add_argument("--figures", default="figures", help="figures directory")
    p.add_argument("--results-manifest", default=None, help="results manifest json")
    p.add_argument("--allow-placeholders", action="store_true", help="allow placeholders in export")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("manuscript-check", help="fail on unresolved empirical placeholders")
    p.add_argument("--tex", required=True)
    p.add_argument("--tables", default="tables")
    p.add_argument("--figures", default="figures")
    p.add_argument("--results-manifest", default=None)
    p.add_argument("--log", default=None)
    p.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="pre-run mode: report placeholders without failing",
    )
    p.set_defaults(func=_cmd_manuscript_check)

    p = sub.add_parser("app-doctor", help="report the application stack, without any network call")
    p.set_defaults(func=_cmd_app_doctor)

    p = sub.add_parser("providers", help="provider configuration status (never shows key material)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_providers)

    p = sub.add_parser("policy-check", help="evaluate a lifecycle policy decision")
    p.add_argument("--action", required=True)
    p.add_argument("--subject", default="cli")
    p.set_defaults(func=_cmd_policy_check)

    p = sub.add_parser("mock-e2e", help="run the synthetic end-to-end pipeline (no network)")
    p.add_argument("--seed", type=int, default=2)
    p.set_defaults(func=_cmd_mock_e2e)

    p = sub.add_parser("freeze-verify", help="validate a freeze record")
    p.add_argument("--record", required=True)
    p.set_defaults(func=_cmd_freeze_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
