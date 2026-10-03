"""Settings, provider selection, key hygiene and the log redactor for the AI gateway."""

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ai.factory import build_gateway, build_provider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openai import OpenAIProvider
from app.core.config import Settings
from app.core.logging import RedactingFormatter, redact

KEY = "sk-test-" + "k" * 32


def settings(**kwargs: object) -> Settings:
    return Settings(environment="test", _env_file=None, **kwargs)  # type: ignore[arg-type]


def test_the_default_is_the_offline_fake_provider_with_no_key_required() -> None:
    s = settings()
    assert s.ai_provider == "fake" and s.openai_api_key is None
    assert isinstance(build_provider(s), FakeProvider)


def test_openai_requires_a_key_and_the_key_is_never_shown() -> None:
    with pytest.raises(ValidationError, match="ADVISORAI_OPENAI_API_KEY"):
        settings(ai_provider="openai")
    s = settings(ai_provider="openai", openai_api_key=KEY)
    assert isinstance(build_provider(s), OpenAIProvider)
    assert KEY not in repr(s) and KEY not in str(s) and KEY not in repr(s.model_dump())


def test_an_obviously_wrong_key_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="too short"):
        settings(openai_api_key="abc")


def test_the_key_is_read_from_the_backend_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVISORAI_AI_PROVIDER", "openai")
    monkeypatch.setenv("ADVISORAI_OPENAI_API_KEY", KEY)
    s = Settings(environment="test", _env_file=None)
    assert s.openai_api_key is not None and s.openai_api_key.get_secret_value() == KEY


@pytest.mark.parametrize(
    "field",
    ["ai_request_timeout_seconds", "ai_max_attempts", "ai_schema_retries", "ai_run_budget_usd"],
)
def test_gateway_limits_are_bounded(field: str) -> None:
    with pytest.raises(ValidationError):
        settings(**{field: -1})
    with pytest.raises(ValidationError):
        settings(**{field: 10_000})


def test_the_gateway_is_built_from_settings_and_routes_through_the_registry() -> None:
    gateway = build_gateway(settings(ai_max_attempts=2))
    assert gateway.provider_name == "fake"


def test_a_missing_registry_file_is_a_configuration_error_not_a_crash_later(tmp_path: Path) -> None:
    from app.ai.types import AIConfigError

    with pytest.raises(AIConfigError):
        build_gateway(settings(ai_models_file=tmp_path / "nope.yaml"))


def test_provider_keys_are_redacted_from_log_lines() -> None:
    assert KEY not in redact(f"calling with {KEY} now")
    assert "[redacted-key]" in redact("key sk-proj-abcdefgh12345678")
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord("advisorai.ai", logging.ERROR, __file__, 1, "failed with %s", (KEY,), None)
    assert KEY not in formatter.format(record)


def test_the_example_env_documents_the_variables_with_the_key_left_empty() -> None:
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    assert "ADVISORAI_OPENAI_API_KEY=" in text and "ADVISORAI_AI_PROVIDER=fake" in text
    line = next(row for row in text.splitlines() if row.startswith("ADVISORAI_OPENAI_API_KEY="))
    assert line.strip() == "ADVISORAI_OPENAI_API_KEY="
