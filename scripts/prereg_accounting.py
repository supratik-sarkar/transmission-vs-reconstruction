#!/usr/bin/env python3
"""Mechanical leaf-level accounting for the pre-registration.

Counts every declared parameter by binding status, straight from the YAML,
and cross-checks it against the prose document and the stage configs.

Why mechanical: a hand-written classification table in an audit document is a
second source of truth that drifts. The only number worth reporting is one a
script recomputes.

The scientifically important check is UNDECLARED leaves. A parameter present in
the YAML with a value but no `status` is a parameter that has been frozen
silently -- which is precisely the failure the pre-registration exists to
prevent.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

VALID_STATUSES = {"frozen", "proposed", "must_be_pinned", "derived"}
#: Keys that are metadata about the document, not scientific parameters.
META_KEYS = {"version", "binding", "resolved", "supersedes", "note", "integrity"}


def walk(node, path=""):
    """Yield (path, kind, payload) for every leaf.

    kind is 'declared' when the node carries an explicit status, 'undeclared'
    when it is a bare value inside a scientific section.
    """
    if isinstance(node, dict):
        if "status" in node:
            yield path, "declared", node
            return
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, dict | list):
                yield from walk(value, child)
            else:
                yield child, "undeclared", value
    elif isinstance(node, list):
        # A list of scalars is a single value, not a set of leaves.
        if any(isinstance(x, dict | list) for x in node):
            for i, value in enumerate(node):
                yield from walk(value, f"{path}[{i}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yaml", default="configs/preregistration_v1_2.yaml")
    ap.add_argument("--md", default="protocol/PREREGISTRATION_v1.2.md")
    ap.add_argument("--stage-configs", nargs="*", default=[])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    doc = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))
    sections = {k: v for k, v in doc.items() if k not in META_KEYS}

    declared: list[tuple[str, str]] = []
    undeclared: list[tuple[str, object]] = []
    bad_status: list[tuple[str, str]] = []

    for path, kind, payload in walk(sections):
        if kind == "declared":
            status = str(payload.get("status", "")).strip().lower()
            declared.append((path, status))
            if status not in VALID_STATUSES:
                bad_status.append((path, status))
        else:
            undeclared.append((path, payload))

    counts = Counter(status for _, status in declared)

    # A `proposed` leaf is only acceptable if its RESOLUTION RULE is already
    # frozen. Otherwise it is an open value with no plan, which is
    # indistinguishable from having been forgotten.
    unruled: list[str] = []
    for path, kind, payload in walk(sections):
        if kind != "declared" or str(payload.get("status")) != "proposed":
            continue
        stage = payload.get("resolution_stage")
        ruled = payload.get("selection_rule_status") or payload.get("search_rule_status")
        if stage not in {"CALIBRATION", "DEVELOPMENT"} or ruled != "FROZEN":
            unruled.append(path)

    # ---- prose document cross-check --------------------------------------
    md = Path(args.md).read_text(encoding="utf-8")
    # Count only the BOLD status marker. The bare word also appears in
    # explanatory prose ("Values marked PROPOSED are not approved"), and counting
    # those inflates the total and makes the cross-check look broken when it is
    # not.
    md_proposed = len(re.findall(r"\*\*PROPOSED\*\*", md))
    md_proposed_word_total = len(re.findall(r"\bPROPOSED\b", md))
    md_blanks = len(re.findall(r"\[ \]", md))

    # ---- integrity blanks -------------------------------------------------
    integrity = doc.get("integrity", {}) or {}
    integrity_unfilled = sorted(k for k, v in integrity.items() if v in (None, ""))

    # ---- stage config cross-check ----------------------------------------
    stage_mismatch: list[str] = []
    stage_files = args.stage_configs or sorted(str(p) for p in Path("configs").glob("stage*.yaml"))
    yaml_stages = sections.get("stages", {})
    for path_str in stage_files:
        p = Path(path_str)
        if not p.exists():
            continue
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        name = str(cfg.get("stage", "")).lower()
        declared_docs = (yaml_stages.get(name, {}) or {}).get("documents")
        actual = cfg.get("documents")
        if declared_docs is not None and actual is not None and declared_docs != actual:
            stage_mismatch.append(
                f"{p.name}: documents={actual} but preregistration says {declared_docs}"
            )

    report = {
        "yaml": args.yaml,
        "binding": doc.get("binding"),
        "resolved": doc.get("resolved"),
        "total_declared_leaves": len(declared),
        "by_status": dict(sorted(counts.items())),
        "undeclared_leaves": [p for p, _ in undeclared],
        "invalid_status_values": bad_status,
        "proposed_without_frozen_rule": unruled,
        "integrity_unfilled": integrity_unfilled,
        "prose_proposed_status_markers": md_proposed,
        "prose_proposed_word_occurrences": md_proposed_word_total,
        "prose_blank_slots": md_blanks,
        "stage_config_mismatches": stage_mismatch,
        "proposed_paths": sorted(p for p, s in declared if s == "proposed"),
        "must_pin_paths": sorted(p for p, s in declared if s == "must_be_pinned"),
    }

    print(f"pre-registration: {args.yaml}")
    print(f"binding={doc.get('binding')}  resolved={doc.get('resolved')}")
    print()
    print(f"declared leaves: {len(declared)}")
    for status, n in sorted(counts.items()):
        print(f"  {status:<16s} {n:3d}")
    print()
    print(f"undeclared leaves (silently frozen if any): {len(undeclared)}")
    for path, value in undeclared:
        print(f"  UNDECLARED  {path} = {value!r}")
    if bad_status:
        print()
        for path, status in bad_status:
            print(f"  INVALID STATUS  {path}: {status!r}")
    print()
    print(f"proposed leaves lacking a frozen resolution rule: {len(unruled)}")
    for path in unruled:
        print(f"  UNRULED  {path}")
    print()
    print(f"integrity fields still unfilled: {len(integrity_unfilled)} -> {integrity_unfilled}")
    print(
        f"prose PROPOSED status markers: {md_proposed}"
        f"   (word occurrences incl. prose: {md_proposed_word_total})"
        f"   blank slots: {md_blanks}"
    )
    if stage_mismatch:
        print()
        for m in stage_mismatch:
            print(f"  STAGE MISMATCH  {m}")
    else:
        print("stage configs agree with the pre-registration")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.json}")

    problems = len(undeclared) + len(bad_status) + len(stage_mismatch) + len(unruled)
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
