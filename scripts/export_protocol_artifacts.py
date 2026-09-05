#!/usr/bin/env python3
"""Emit the frozen protocol artifacts FROM THE CODE.

Prompts, slot schemas and randomisation supports are generated rather than
maintained by hand, so a specification file cannot silently drift away from the
implementation it claims to describe. Re-running this script must be a no-op on
a clean tree; CI checks exactly that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from handoff_fidelity.atomizer.taxonomy import NUMERIC_SUBTYPES, SCOPE_VOCABULARY
from handoff_fidelity.causalrelay.renderer import RENDERER_VERSION, renderer_hash
from handoff_fidelity.interventions.skeleton import MIN_POPULATED_ROLES, OMITTED
from handoff_fidelity.models import AtomRole
from handoff_fidelity.receiver.prompt import (
    RECEIVER_INSTRUCTION,
    build_no_evidence_prompt,
    build_prior_probe_prompt,
    build_receiver_prompt,
    prompt_hashes,
)
from handoff_fidelity.receiver.slots import SLOT_SCHEMAS, k_effective
from handoff_fidelity.relay.task import GLOBAL_DOWNSTREAM_TASK, task_hash

ENTITY_SUPPORT_SIZE = 200
ENTITY_SEED = 20260907

_STEMS = (
    "Alder",
    "Brant",
    "Calder",
    "Denby",
    "Ellery",
    "Fenwick",
    "Gilby",
    "Harlow",
    "Ilford",
    "Jarrow",
    "Kelby",
    "Lomond",
    "Marden",
    "Norbury",
    "Orwell",
    "Pelham",
    "Quarry",
    "Redmoor",
    "Stanmore",
    "Thackley",
    "Ulverton",
    "Vantry",
    "Westby",
    "Yardley",
)
_QUALIFIERS = ("", "Vale", "Ridge", "Point", "Cross", "Field", "Bourne", "Wick")
_SUFFIXES = (
    "Holdings",
    "Industries",
    "Group",
    "Corporation",
    "Systems",
    "Partners",
    "Resources",
    "Technologies",
)


def entity_support() -> list[str]:
    """Deterministically generated fictitious names.

    HUMAN SCREENING AGAINST A REAL-ISSUER REGISTRY IS BLOCKING AND HAS NOT BEEN
    PERFORMED. Nothing here asserts that these names are unused in the world.
    """
    rng = random.Random(ENTITY_SEED)
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < ENTITY_SUPPORT_SIZE:
        name = " ".join(
            p for p in (rng.choice(_STEMS), rng.choice(_QUALIFIERS), rng.choice(_SUFFIXES)) if p
        )
        if name not in seen:
            seen.add(name)
            out.append(name)
    return sorted(out)


def period_annual_support() -> list[str]:
    return [f"FY{y}" for y in range(2016, 2022)]


def period_quarter_support() -> list[str]:
    return [f"FY{y}Q{q}" for y in range(2016, 2022) for q in (1, 2, 3, 4)]


def write(path: Path, text: str) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return str(path), hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="protocol")
    args = ap.parse_args()
    root = Path(args.out)
    written: dict[str, str] = {}

    header = (
        "GENERATED FROM CODE by scripts/export_protocol_artifacts.py.\n"
        "Do not edit by hand: a hand-edited specification can drift away from the\n"
        "implementation it claims to describe.\n"
    )

    p, h = write(root / "prompts" / "downstream_task.txt", f"# {header}\n{GLOBAL_DOWNSTREAM_TASK}")
    written[p] = h

    p, h = write(
        root / "prompts" / "receiver.txt",
        f"# {header}\n"
        "# ONE shared receiver prompt is used for the natural arm, the\n"
        "# counterfactual arm, both matched-skeleton arms and the no-evidence\n"
        "# baseline. Different prompts across arms would confound a prompt\n"
        "# difference with the availability contrast.\n\n"
        f"{RECEIVER_INSTRUCTION}\n\n--- EXAMPLE RENDERING ---\n"
        + build_receiver_prompt(
            message="- scope: North America\n- period: FY2019",
            role=AtomRole.NUMERIC,
            subject="the issuer",
            attribute="the change in segment margin",
        ),
    )
    written[p] = h

    p, h = write(
        root / "prompts" / "no_evidence_baseline.txt",
        f"# {header}\n"
        "# The EMPIRICAL chance baseline. This is the operative chance level,\n"
        "# because a receiver free to answer outside the candidate set matches\n"
        "# with probability P(output in K)/K <= 1/K.\n\n"
        + build_no_evidence_prompt(
            role=AtomRole.PERIOD,
            subject="the issuer",
            attribute="the change in segment margin",
        ),
    )
    written[p] = h

    p, h = write(
        root / "prompts" / "prior_probe.txt",
        f"# {header}\n"
        "# Closed book, fresh context, ONE focal atom per query. A batched\n"
        "# autoregressive vector would let earlier slots condition later ones, so\n"
        "# the probe would partly measure self-conditioning rather than prior\n"
        "# access.\n\n"
        + build_prior_probe_prompt(
            role=AtomRole.SCOPE,
            subject="the issuer",
            attribute="the segment whose margin improved",
        ),
    )
    written[p] = h

    slots = {
        role.value: {
            "question_template": s.question_template,
            "answer_format": s.answer_format,
            "constrained": s.constrained,
        }
        for role, s in sorted(SLOT_SCHEMAS.items(), key=lambda kv: kv[0].value)
    }
    p, h = write(root / "specs" / "slot_schema.json", json.dumps(slots, indent=2, sort_keys=True))
    written[p] = h

    ent = entity_support()
    p, h = write(
        root / "randomisation" / "entity_support.txt",
        "# "
        + header
        + f"# seed={ENTITY_SEED}  n={len(ent)}  K_eff={k_effective(AtomRole.ENTITY, len(ent))}\n"
        "# HUMAN SCREENING AGAINST A REAL-ISSUER REGISTRY IS BLOCKING AND HAS NOT\n"
        "# BEEN PERFORMED. Nothing here asserts these names are unused.\n" + "\n".join(ent),
    )
    written[p] = h

    for name, values in (
        ("period_annual_support.txt", period_annual_support()),
        ("period_quarter_support.txt", period_quarter_support()),
        ("scope_support.txt", sorted(SCOPE_VOCABULARY)),
    ):
        p, h = write(
            root / "randomisation" / name,
            "# " + header + f"# n={len(values)}  K_eff={len(values) - 1}  "
            "(the natural value is excluded from its own redraw)\n" + "\n".join(values),
        )
        written[p] = h

    p, h = write(
        root / "randomisation" / "numeric_support.md",
        "# "
        + header
        + """
# Numeric randomisation support

Only the `pct` subtype is randomised.

Currency magnitudes are not exchangeable across issuers: a uniformly redrawn
currency value would not be a plausible counterfactual, and implausibility would
change salience rather than prior access, which is the manipulation the design
needs to isolate.

Recognised subtypes: """
        + ", ".join(f"`{s}`" for s in NUMERIC_SUBTYPES)
        + """

For `pct`, the redraw support is the plausible range at two decimals, stated per
document, with the natural value excluded. `K_eff` is therefore recorded per
document rather than globally. **PROPOSED** pending approval of the range.
""",
    )
    written[p] = h

    meta = {
        "downstream_task_sha256": task_hash(),
        "prompt_hashes": prompt_hashes(),
        "renderer_version": RENDERER_VERSION,
        "renderer_sha256": renderer_hash(),
        "omitted_token": OMITTED,
        "min_populated_roles": MIN_POPULATED_ROLES,
        "artifacts": {Path(k).as_posix(): v for k, v in sorted(written.items())},
    }
    p, _ = write(root / "PROTOCOL_ARTIFACTS.json", json.dumps(meta, indent=2, sort_keys=True))
    print(f"wrote {len(written) + 1} artifacts under {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
