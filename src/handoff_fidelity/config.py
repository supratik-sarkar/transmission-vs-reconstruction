from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment/private .env.

    The public repository never requires a committed secret. By default we look
    for a .env file only inside the private runtime workspace.
    """

    model_config = SettingsConfigDict(
        env_prefix="HANDOFF_",
        extra="ignore",
        case_sensitive=False,
    )

    private_home: Path = Field(default=Path("~/Desktop/handoff-fidelity"))
    relay_provider: str = "mock"
    receiver_provider: str = "mock"
    relay_model: str = "UNFROZEN"
    receiver_model: str = "UNFROZEN"
    source_token_budget: int = 2000
    relay_budget_tokens: int | None = None
    tokenizer_name: str = "cl100k_base"

    @field_validator("private_home", mode="before")
    @classmethod
    def _expand_home(cls, value: object) -> object:
        if isinstance(value, str):
            return str(Path(value).expanduser())
        return value

    def env_file(self) -> Path:
        return self.private_home.expanduser() / ".env"

    def ensure_private_dirs(self) -> None:
        for name in (
            "data/raw",
            "data/interim",
            "data/processed",
            "runs",
            "cache",
            "logs",
            "calibration",
            "source_manifests",
            "protocol_freeze",
        ):
            (self.private_home.expanduser() / name).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    preliminary = Settings()
    env_file = preliminary.env_file()
    if env_file.exists():
        return Settings(_env_file=env_file, _env_file_encoding="utf-8")
    return preliminary
