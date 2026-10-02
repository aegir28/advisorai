"""Configuration foundation: typed settings read from ADVISORAI_* environment variables.

Phase 2A has no secrets. When a database, auth provider or AI provider is added, its keys become
fields here (as `SecretStr`) and are read from the backend environment only.
"""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Request
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADVISORAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "advisorai-backend"
    version: str = __version__
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    docs_enabled: bool = True
    # Comma-separated in the environment (ADVISORAI_CORS_ORIGINS=a,b), a list here.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("a wildcard CORS origin is not allowed; list explicit origins")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_request(request: Request) -> Settings:
    """FastAPI dependency: the settings the running app was created with (see `create_app`)."""
    settings: Settings = request.app.state.settings
    return settings
