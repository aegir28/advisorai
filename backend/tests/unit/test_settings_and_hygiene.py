"""Settings for the security foundation, and repository-level privacy/secret hygiene."""

import re
import subprocess
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings

ROOT = Path(__file__).parents[3]

STRONG = "0123456789abcdef0123456789abcdef"
PRODUCTION = {
    "environment": "production",
    "database_url": SecretStr("postgresql+asyncpg://app_backend:pw@db.example:5432/postgres"),
    "system_database_url": SecretStr("postgresql+asyncpg://app_system:pw2@db.example:5432/postgres"),
    "supabase_jwks_url": "https://p.supabase.co/auth/v1/.well-known/jwks.json",
    "supabase_jwt_issuer": "https://p.supabase.co/auth/v1",
    "supabase_url": "https://p.supabase.co",
    "supabase_service_role_key": SecretStr("service-role-key"),
    "audit_ip_hmac_secret": SecretStr(STRONG),
}


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


# ── Settings ────────────────────────────────────────────────────────────────────────────────────
def test_data_mode_can_only_be_synthetic_only() -> None:
    assert make().data_mode == "synthetic_only"
    for other in ("real", "production", "phi", ""):
        with pytest.raises(ValidationError):
            make(data_mode=other)


def test_real_data_cannot_be_unlocked_by_an_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVISORAI_DATA_MODE", "real")
    with pytest.raises(ValidationError):
        make()


def test_secrets_never_appear_in_repr_or_str() -> None:
    settings = make(
        database_url=SecretStr("postgresql+asyncpg://u:hunter2@h/db"),
        supabase_service_role_key=SecretStr("SERVICEKEY123"),
        audit_ip_hmac_secret=SecretStr(STRONG),
    )
    rendered = repr(settings) + str(settings) + settings.model_dump_json()
    for secret in ("hunter2", "SERVICEKEY123", STRONG):
        assert secret not in rendered


def test_the_database_url_must_be_the_async_postgres_scheme() -> None:
    make(database_url=SecretStr("postgresql+asyncpg://u:p@h/db"))
    for bad in ("postgresql://u:p@h/db", "mysql://u:p@h/db", "sqlite:///x.db"):
        with pytest.raises(ValidationError):
            make(database_url=SecretStr(bad))


def test_the_system_path_is_a_separate_login_from_the_user_path() -> None:
    user = SecretStr("postgresql+asyncpg://app_backend:pw@h/db")
    system = SecretStr("postgresql+asyncpg://app_system:pw2@h/db")
    assert make(database_url=user, system_database_url=system).system_database_url == system
    with pytest.raises(ValidationError, match="different login"):
        make(database_url=user, system_database_url=user)
    with pytest.raises(ValidationError):
        make(system_database_url=SecretStr("postgresql://app_system:pw@h/db"))  # wrong scheme


def test_the_system_url_is_secret_too() -> None:
    settings = make(system_database_url=SecretStr("postgresql+asyncpg://app_system:SYSPW123@h/db"))
    assert "SYSPW123" not in repr(settings) + str(settings) + settings.model_dump_json()


def test_the_hmac_secret_must_be_long_enough() -> None:
    make(audit_ip_hmac_secret=SecretStr(STRONG))
    with pytest.raises(ValidationError):
        make(audit_ip_hmac_secret=SecretStr("short"))


@pytest.mark.parametrize("ttl", [0, 29, 301, 3600])
def test_signed_url_ttl_is_capped_at_five_minutes(ttl: int) -> None:
    with pytest.raises(ValidationError):
        make(signed_url_ttl_seconds=ttl)
    assert make(signed_url_ttl_seconds=300).signed_url_ttl_seconds == 300


def test_production_requires_the_whole_security_foundation() -> None:
    assert make(**PRODUCTION).environment == "production"
    for missing in [k for k in PRODUCTION if k != "environment"]:
        incomplete = {k: v for k, v in PRODUCTION.items() if k != missing}
        with pytest.raises(ValidationError, match=missing):
            make(**incomplete)


@pytest.mark.parametrize("field", ["supabase_jwks_url", "supabase_jwt_issuer", "supabase_url"])
def test_production_urls_must_be_https(field: str) -> None:
    with pytest.raises(ValidationError, match="https"):
        make(**{**PRODUCTION, field: "http://insecure.example"})


# ── Repository hygiene ──────────────────────────────────────────────────────────────────────────
def tracked_files() -> list[Path]:
    """Tracked plus untracked-but-not-ignored files (so a new file is checked before it is committed)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    return [ROOT / f for f in out if f and (ROOT / f).is_file()]


TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".sql",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".json",
    ".example",
    ".env",
    ".mjs",
}


def test_no_jwt_or_service_key_is_committed() -> None:
    jwt_like = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")
    offenders = []
    for path in tracked_files():
        if path.suffix not in TEXT_SUFFIXES or path.name in {"uv.lock", "package-lock.json"}:
            continue
        if jwt_like.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"JWT-looking strings committed: {offenders}"


def test_env_examples_hold_no_secret_values() -> None:
    secret_names = re.compile(r"(?i)(SECRET|SERVICE_ROLE|PASSWORD|DATABASE_URL|API_KEY|PRIVATE)")
    for example in [p for p in tracked_files() if p.name == ".env.example"]:
        for line in example.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            if secret_names.search(name):
                assert value.strip() == "", f"{example.relative_to(ROOT)}: {name} must be empty"


def test_no_service_role_or_secret_is_exposed_to_the_browser() -> None:
    public = re.compile(r"NEXT_PUBLIC_[A-Z0-9_]*(SERVICE|SECRET|PASSWORD|JWT|PRIVATE|DATABASE)")
    offenders = [
        str(p.relative_to(ROOT))
        for p in tracked_files()
        if p.is_relative_to(ROOT / "frontend")
        and p.suffix in TEXT_SUFFIXES | {".example"}
        and p.name != "package-lock.json"
        and public.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], f"secrets exposed through NEXT_PUBLIC_*: {offenders}"


def test_seed_data_has_no_credentials_and_no_real_looking_identity() -> None:
    seed = (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8").lower()
    # No statement may set a password or hold a credential; the comment saying so is fine.
    assert not re.search(r"alter\s+role|password\s+'|crypt\(", seed)
    assert "@advisorai.test" in seed  # reserved test domain only
    assert not re.search(r"@(gmail|yahoo|outlook|hotmail)\.", seed)


def test_migrations_never_store_a_password_or_key() -> None:
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?i)\bpassword\s+'", text), f"{path.name} sets a password"
        assert "eyJ" not in text


def test_every_migration_that_creates_a_table_also_enables_rls() -> None:
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        created = re.findall(r"create table public\.(\w+)", text)
        has_dynamic = "execute format('alter table public.%I enable row level security'" in text
        for table in created:
            assert has_dynamic or f"alter table public.{table} enable row level security" in text, (
                f"{path.name}: {table} is created without RLS in the same migration"
            )
            assert has_dynamic or f"alter table public.{table} force row level security" in text, (
                f"{path.name}: {table} is created without FORCE RLS"
            )
