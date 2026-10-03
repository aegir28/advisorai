"""Security headers on every response, and the request-size limit."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import MAX_BODY_BYTES
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(environment="test", _env_file=None)))


def test_every_response_is_uncacheable_and_locked_down() -> None:
    for path in ("/api/v1/health", "/api/v1/nope", "/api/v1/me"):  # ok, 404 and 401/503 all carry them
        r = client().get(path)
        assert r.headers["Cache-Control"] == "no-store", path
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"
        assert r.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert "Strict-Transport-Security" not in r.headers  # not in local/test


def test_the_interactive_docs_are_not_broken_by_the_api_csp() -> None:
    r = client().get("/api/v1/docs")
    assert r.status_code == 200 and "Content-Security-Policy" not in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_is_sent_in_production_only() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://u:p@h/d",
        system_database_url="postgresql+asyncpg://s:p@h/d",
        supabase_jwks_url="https://x.test/jwks",
        supabase_jwt_issuer="https://x.test/auth/v1",
        supabase_url="https://x.test",
        supabase_service_role_key="k",
        audit_ip_hmac_secret="0123456789abcdef0123456789abcdef",
        docs_enabled=False,
        _env_file=None,
    )
    r = TestClient(create_app(settings)).get("/api/v1/health")
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")


def test_an_oversized_body_is_refused_before_it_is_read() -> None:
    r = client().post(
        "/api/v1/cases", content=b"x" * (MAX_BODY_BYTES + 1), headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE" and r.json()["error"]["request_id"]
    assert r.headers["Cache-Control"] == "no-store"


def test_an_oversized_chunked_body_is_refused_too() -> None:
    def chunks() -> object:
        for _ in range(3):
            yield b"x" * (MAX_BODY_BYTES // 2)

    r = client().post("/api/v1/cases", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize("size", [0, 100, MAX_BODY_BYTES])
def test_bodies_up_to_the_limit_reach_the_route(size: int) -> None:
    r = client().post("/api/v1/cases", content=b"x" * size, headers={"Content-Type": "application/json"})
    assert r.status_code != 413
