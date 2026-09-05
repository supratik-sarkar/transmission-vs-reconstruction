#!/usr/bin/env python3
"""Emit a blank human-verification sheet for an atom inventory.

Human verification is blocking. Rows without an explicit decision are not
admitted to the target population; they are never defaulted to accepted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handoff_fidelity.atomizer.rules import atomize  # noqa: E402
from handoff_fidelity.atomizer.verify import filter_eligible, write_review_template  # noqa: E402
from handoff_fidelity.corpus.frame import (  # noqa: E402
    assert_inventory_within_frame,
    build_source_frame,
)
from handoff_fidelity.tokenization import get_tokenizer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", required=True, help="path to a relay-visible source frame (.txt)")
    ap.add_argument("--document-id", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-tokenizer-fallback", action="store_true")
    args = ap.parse_args()

    frame_path = Path(args.frame)
    document_id = args.document_id or frame_path.stem
    tokenizer = get_tokenizer(allow_fallback=args.allow_tokenizer_fallback)

    frame = build_source_frame(
        document_id=document_id,
        raw_text=frame_path.read_text(encoding="utf-8"),
        window_tokens=10**9,
        tokenizer=tokenizer,
        section="full",
    )
    atoms = atomize(frame.document_id, frame.text)
    assert_inventory_within_frame(frame, atoms)

    report = filter_eligible(atoms, frame.text, require_human_verification=False)
    n = write_review_template(report.eligible, Path(args.out))

    print(f"frame sha256: {frame.sha256}")
    print(f"{len(atoms)} atom(s) extracted; {n} written for review")
    if report.excluded:
        print("pre-treatment exclusions:")
        for reason, rate in sorted(report.rates().items()):
            if rate:
                print(f"  {reason}: {rate:.3f}")
    print("\nFill the 'decision' column with accepted/rejected. Change nothing else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
