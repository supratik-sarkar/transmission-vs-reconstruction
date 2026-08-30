#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from handoff_fidelity.integrity import write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    root = args.root.resolve()
    paths = [Path(p) for p in args.paths]
    write_manifest(root, paths, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
