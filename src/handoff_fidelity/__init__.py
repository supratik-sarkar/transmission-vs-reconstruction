"""handoff_fidelity -- a causal measurement and benchmarking toolkit for
distinguishing transmitted from reconstructed information in chained
language-model workflows.

Nothing in this package performs a network request or a model call on import,
and no execution path runs without an explicit opt-in plus a valid freeze
record.
"""

from __future__ import annotations

__version__ = "0.2.0"
__all__ = ["__version__"]
