#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from handoff_fidelity.integrity import sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-pool", type=Path, required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--relay-model", required=True)
    parser.add_argument("--receiver-model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if "UNFROZEN" in {args.relay_model, args.receiver_model}:
        raise SystemExit("Refusing to freeze with UNFROZEN model strings")
    payload = {
        "preregistration_sha256": sha256_file(args.preregistration),
        "artifact_manifest_sha256": sha256_file(args.manifest),
        "source_pool_sha256": sha256_file(args.source_pool),
        "git_commit": args.git_commit,
        "frozen_utc": datetime.now(UTC).isoformat(),
        "relay_model": args.relay_model,
        "receiver_model": args.receiver_model,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
