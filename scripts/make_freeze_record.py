#!/usr/bin/env python3
"""Write a protocol or final-test freeze record.

Every required field must carry a real value. Placeholders are rejected: a
freeze record that says TBD is a record that was false the moment it was signed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handoff_fidelity.causalrelay.features import schema_hash  # noqa: E402
from handoff_fidelity.causalrelay.renderer import renderer_hash  # noqa: E402
from handoff_fidelity.config import load_settings  # noqa: E402
from handoff_fidelity.provenance.freeze import (  # noqa: E402
    PROTOCOL_FIELDS,
    TEST_FIELDS,
    FreezeIncomplete,
    new_record,
)
from handoff_fidelity.receiver.prompt import prompt_hashes  # noqa: E402
from handoff_fidelity.relay.task import task_hash  # noqa: E402


def _git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=["protocol", "final_test"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--dry-run", action="store_true", help="report what is still missing")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    settings = load_settings()

    fields: dict[str, object] = {
        "git_commit": _git_commit(root),
        "relay_model": settings.relay_model,
        "receiver_model": settings.receiver_model,
        "tokenizer": settings.tokenizer_name,
        "source_window_tokens": settings.source_window_tokens,
        "relay_budget_tokens": settings.relay_budget_tokens,
        "sampling_k": settings.k_focal,
        "master_seed": settings.master_seed,
        "downstream_task_sha256": task_hash(),
        "receiver_prompt_sha256": prompt_hashes()["slot_schemas"],
        "renderer_sha256": renderer_hash(),
        "feature_schema_sha256": schema_hash(),
    }
    for item in args.set:
        key, _, value = item.partition("=")
        fields[key.strip()] = value.strip()

    record = new_record(args.kind, **fields)
    required = TEST_FIELDS if args.kind == "final_test" else PROTOCOL_FIELDS
    missing = record.missing()

    print(
        f"{args.kind} freeze record: {len(required) - len(missing)}/{len(required)} fields filled"
    )
    if missing:
        print("\nStill required (supply with --set KEY=VALUE):")
        for field in missing:
            print(f"  {field}")

    if args.dry_run:
        return 0
    try:
        path = record.write(Path(args.out))
    except FreezeIncomplete as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 1
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
