"""Runtime configuration.

Design rules enforced here:

* No filesystem path belonging to any particular machine appears in this
  repository. The private workspace location is supplied at runtime through
  ``HANDOFF_PRIVATE_HOME``; if unset, a neutral per-user default under
  ``Path.home()`` is used.
* Credentials are read from the environment only and are never logged,
  serialised or echoed.
* Model identifiers default to ``UNFROZEN`` so that an unpinned run is a hard
  error rather than a silent default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .tokenization import FROZEN_TOKENIZER

UNFROZEN = "UNFROZEN"

_PRIVATE_SUBDIRS: tuple[str, ...] = (
    "configs",
    "data/raw",
    "data/interim",
    "data/processed",
    "data/calibration",
    "data/source_pool",
    "data/stage1",
    "data/stage2_dev",
    "data/stage2_test",
    "source_manifests",
    "calibration",
    "preregistration",
    "protocol_freeze",
    "test_freeze",
    "third_party",
    "envs",
    "runs/calibration",
    "runs/baseline_reproduction",
    "runs/stage1",
    "runs/stage2_dev",
    "runs/stage2_test",
    "runs/experiment_c",
    "runs/multihop",
    "cache",
    "logs",
    "artifacts",
    "tables",
    "figures",
    "manuscript_exports",
)

_SECRET_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "HF_TOKEN",
)


def default_private_home() -> Path:
    """Neutral default. Overridden by ``HANDOFF_PRIVATE_HOME``."""
    return Path.home() / ".handoff-fidelity"


@dataclass(frozen=True, slots=True)
class Settings:
    private_home: Path = field(default_factory=default_private_home)
    relay_provider: str = "mock"
    receiver_provider: str = "mock"
    relay_model: str = UNFROZEN
    receiver_model: str = UNFROZEN
    tokenizer_name: str = FROZEN_TOKENIZER
    allow_tokenizer_fallback: bool = False
    source_window_tokens: int = 2000
    relay_budget_tokens: int = 500
    k_focal: int = 3
    master_seed: int = 20260907
    decoder_regime: str = "D"
    allow_network: bool = False

    # ---- derived locations -------------------------------------------------
    def path(self, *parts: str) -> Path:
        return self.private_home.expanduser().joinpath(*parts)

    def ensure_dirs(self) -> None:
        for sub in _PRIVATE_SUBDIRS:
            self.path(*sub.split("/")).mkdir(parents=True, exist_ok=True)

    # ---- redaction ---------------------------------------------------------
    def public_summary(self) -> dict[str, Any]:
        """Everything safe to print or write to a log."""
        return {
            "relay_provider": self.relay_provider,
            "receiver_provider": self.receiver_provider,
            "relay_model": self.relay_model,
            "receiver_model": self.receiver_model,
            "tokenizer_name": self.tokenizer_name,
            "source_window_tokens": self.source_window_tokens,
            "relay_budget_tokens": self.relay_budget_tokens,
            "k_focal": self.k_focal,
            "master_seed": self.master_seed,
            "decoder_regime": self.decoder_regime,
            "allow_network": self.allow_network,
            "private_home_configured": self.private_home is not None,
        }


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from the environment. Never reads a committed secret."""
    src = dict(os.environ if env is None else env)
    home_raw = src.get("HANDOFF_PRIVATE_HOME", "").strip()
    home = Path(home_raw).expanduser() if home_raw else default_private_home()
    return Settings(
        private_home=home,
        relay_provider=src.get("HANDOFF_RELAY_PROVIDER", "mock"),
        receiver_provider=src.get("HANDOFF_RECEIVER_PROVIDER", "mock"),
        relay_model=src.get("HANDOFF_RELAY_MODEL", UNFROZEN),
        receiver_model=src.get("HANDOFF_RECEIVER_MODEL", UNFROZEN),
        tokenizer_name=src.get("HANDOFF_TOKENIZER", FROZEN_TOKENIZER),
        allow_tokenizer_fallback=_env_bool("HANDOFF_ALLOW_TOKENIZER_FALLBACK", False),
        source_window_tokens=_env_int("HANDOFF_SOURCE_WINDOW_TOKENS", 2000),
        relay_budget_tokens=_env_int("HANDOFF_RELAY_BUDGET_TOKENS", 500),
        k_focal=_env_int("HANDOFF_K_FOCAL", 3),
        master_seed=_env_int("HANDOFF_MASTER_SEED", 20260907),
        decoder_regime=src.get("HANDOFF_DECODER_REGIME", "D"),
        allow_network=_env_bool("HANDOFF_ALLOW_NETWORK", False),
    )


def with_overrides(settings: Settings, **kwargs: Any) -> Settings:
    return replace(settings, **kwargs)


def credential_presence(env: dict[str, str] | None = None) -> dict[str, bool]:
    """Report only WHETHER a credential is present. Never its value."""
    src = dict(os.environ if env is None else env)
    return {key: bool(src.get(key, "").strip()) for key in _SECRET_ENV_KEYS}


class UnfrozenModelError(RuntimeError):
    pass


def require_frozen_models(settings: Settings) -> None:
    unfrozen = [
        name
        for name, value in (
            ("relay_model", settings.relay_model),
            ("receiver_model", settings.receiver_model),
        )
        if value == UNFROZEN or not value.strip()
    ]
    if unfrozen:
        raise UnfrozenModelError(
            "Refusing to proceed with unpinned model identifiers: "
            + ", ".join(unfrozen)
            + ". Pin exact version strings in the preregistration first."
        )
