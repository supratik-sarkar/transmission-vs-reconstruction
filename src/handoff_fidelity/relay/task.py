"""The frozen global downstream task.

Every compressor -- controls, external SOTA adapters and CausalRelay -- receives
EXACTLY this text and nothing else that is task-specific. It is frozen before
focal sampling.

Focal atom identities and values are never placed in any compressor prompt or
configuration. Without that rule, a query-aware compressor would be handed the
very atoms used to score it, and the benchmark would measure supervision rather
than allocation.
"""

from __future__ import annotations

import hashlib

GLOBAL_DOWNSTREAM_TASK = (
    "You are preparing a handoff note for a second analyst who will not see the "
    "source document. Within the stated token budget, preserve the information "
    "an analyst would need to answer factual questions about the source: named "
    "entities, business segments and geographies, reporting periods, numeric "
    "values with their units, and references to notes or exhibits. Do not add "
    "information that is not in the source. Do not speculate."
)


def task_hash() -> str:
    return hashlib.sha256(GLOBAL_DOWNSTREAM_TASK.encode("utf-8")).hexdigest()


class FocalLeakError(AssertionError):
    """Raised when a focal atom identity or value reaches a compressor."""


def assert_no_focal_leak(payload: str, focal_values: list[str] | tuple[str, ...]) -> None:
    """Mechanical check that no focal identity reaches a compressor.

    Applied to every prompt and every serialised configuration handed to any
    adapter. This is the guard that keeps the benchmark honest, so it raises
    rather than warns.
    """
    lowered = payload.casefold()
    for value in focal_values:
        v = value.strip().casefold()
        if v and v in lowered:
            raise FocalLeakError(
                "a focal atom value reached a compressor payload; focal sampling "
                "must remain hidden from every compression method"
            )
