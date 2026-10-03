"""Configuration foundation: typed settings read from ADVISORAI_* environment variables.

Secrets (`database_url`, `supabase_service_role_key`, `audit_ip_hmac_secret`) are `SecretStr`: they
never appear in `repr()`, logs or error messages. They are read from the BACKEND environment only and
never reach the frontend or any `NEXT_PUBLIC_*` variable.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from fastapi import Request
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

API_PREFIX = "/api/v1"
# Maximum lifetime of any signed URL the backend issues (blueprint: 5 minutes).
MAX_SIGNED_URL_TTL_SECONDS = 300


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

    # Prototype guard (ADR 0004): the only accepted value. Real patient data stays locked out until a
    # deliberate migration and ADR change this, so it cannot be enabled by configuration alone.
    data_mode: Literal["synthetic_only"] = "synthetic_only"

    # Direct Postgres access as the fail-closed `app_backend` role: the USER path (ADR 0005).
    database_url: SecretStr | None = None
    # A SEPARATE login as the narrow `app_system` role: the SYSTEM path (ADR 0005). Never derived from
    # database_url, so code holding the user-path connection cannot reach it.
    system_database_url: SecretStr | None = None
    # Supabase Auth: JWTs are verified against the project's JWKS (asymmetric keys only).
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    # Supabase Storage API (signed URLs). The service-role key is backend-only.
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    storage_bucket: str = "case-documents"
    signed_url_ttl_seconds: int = Field(
        default=MAX_SIGNED_URL_TTL_SECONDS, ge=30, le=MAX_SIGNED_URL_TTL_SECONDS
    )
    # Upload limits (the 20 MB / PDF-JPEG-PNG rules are fixed by the bucket and `docintel.validate`).
    max_documents_per_case: int = Field(default=30, ge=1, le=100)
    # Background workflow worker (Phase 2D). Off by default: with no node types registered (the AI phase adds
    # them) a run could only fail, so nothing starts it unless it is turned on deliberately.
    worker_enabled: bool = False
    worker_lease_seconds: int = Field(default=60, ge=10, le=600)
    worker_poll_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
    # Versioned workflow definitions (YAML). Default: the repository's `workflows/` folder.
    workflows_dir: Path = Path(__file__).resolve().parents[3] / "workflows"
    # Server-side secret for the HMAC of client IPs in the audit log.
    audit_ip_hmac_secret: SecretStr | None = None

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

    @field_validator("database_url", "system_database_url")
    @classmethod
    def _async_postgres_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("database URLs must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("audit_ip_hmac_secret")
    @classmethod
    def _strong_hmac_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("audit_ip_hmac_secret must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def _the_two_database_urls_are_different_logins(self) -> Self:
        user, system = self.database_url, self.system_database_url
        if user is not None and system is not None and user.get_secret_value() == system.get_secret_value():
            raise ValueError("system_database_url must be a different login (app_system) from database_url")
        return self

    @model_validator(mode="after")
    def _production_requires_the_security_foundation(self) -> Self:
        if self.environment != "production":
            return self
        missing = [
            name
            for name, value in {
                "database_url": self.database_url,
                "system_database_url": self.system_database_url,
                "supabase_jwks_url": self.supabase_jwks_url,
                "supabase_jwt_issuer": self.supabase_jwt_issuer,
                "supabase_url": self.supabase_url,
                "supabase_service_role_key": self.supabase_service_role_key,
                "audit_ip_hmac_secret": self.audit_ip_hmac_secret,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(f"production requires: {', '.join(missing)}")
        for name in ("supabase_jwks_url", "supabase_jwt_issuer", "supabase_url"):
            if not str(getattr(self, name)).startswith("https://"):
                raise ValueError(f"{name} must be https in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_request(request: Request) -> Settings:
    """FastAPI dependency: the settings the running app was created with (see `create_app`)."""
    settings: Settings = request.app.state.settings
    return settings
