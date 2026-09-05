"""API configuration.

Secrets are read from the environment into ``SecretStr``-style holders that
cannot be rendered. No default anywhere in this file points at a real machine:
the private workspace location arrives through ``HANDOFF_PRIVATE_HOME`` and the
environment file through ``HANDOFF_ENV_FILE``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from handoff_fidelity.app_contracts.modes import AppMode

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8099
ENV_FILE_VAR = "HANDOFF_ENV_FILE"


class Secret:
    """A value that cannot be printed.

    ``__repr__``/``__str__`` are overridden and the value is only reachable
    through an explicit ``reveal()``, which nothing in the API layer calls. A
    plain string would eventually reach a log line or an f-string.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str = "") -> None:
        self._value = value

    def __repr__(self) -> str:
        return "Secret(**redacted**)"

    __str__ = __repr__

    def __bool__(self) -> bool:
        return bool(self._value.strip())

    def reveal(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True)
class ApiSettings:
    mode: AppMode = AppMode.RESEARCH
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    max_request_bytes: int = 1_048_576
    private_home: Path | None = None
    demo_enabled: bool = False
    secrets: dict[str, Secret] = field(default_factory=dict, repr=False)

    def public_dict(self) -> dict[str, object]:
        """The only settings shape that reaches a client."""
        return {
            "mode": self.mode.value,
            "host": self.host,
            "port": self.port,
            "demo_enabled": self.demo_enabled,
            "max_request_bytes": self.max_request_bytes,
            "private_home_configured": self.private_home is not None,
        }


SECRET_VARS = ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")


def load_settings(env: dict[str, str] | None = None) -> ApiSettings:
    src = dict(os.environ if env is None else env)

    env_file = src.get(ENV_FILE_VAR, "").strip()
    if env_file and Path(env_file).is_file():
        # Minimal parser: no third-party dependency, and values never logged.
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            src.setdefault(key.strip(), value.strip().strip("'\""))

    mode = (
        AppMode.DEMO
        if src.get("HANDOFF_APP_MODE", "").upper().startswith("DEMO")
        else AppMode.RESEARCH
    )
    home = src.get("HANDOFF_PRIVATE_HOME", "").strip()
    origins = tuple(
        o.strip() for o in src.get("HANDOFF_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ) or ("http://127.0.0.1:5173", "http://localhost:5173")

    return ApiSettings(
        mode=mode,
        host=src.get("HANDOFF_API_HOST", DEFAULT_HOST),
        port=int(src.get("HANDOFF_API_PORT", DEFAULT_PORT)),
        allowed_origins=origins,
        private_home=Path(home).expanduser() if home else None,
        demo_enabled=(mode is AppMode.DEMO),
        secrets={v: Secret(src.get(v, "")) for v in SECRET_VARS},
    )
