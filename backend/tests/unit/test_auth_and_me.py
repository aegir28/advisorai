"""The auth dependency, GET /me and GET /health/ready, end to end through the app (fake database)."""

import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.support import ISSUER, FakeDatabase, KeyPair, StaticKeyProvider, claims, make_keypair, mint

USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")

PROFILE = {
    "user_id": USER,
    "display_name": "Demo User",
    "locale": "en",
    "consented_at": None,
    "consent_version": None,
}


@pytest.fixture(scope="module")
def keys() -> KeyPair:
    return make_keypair("key-1")


@pytest.fixture
def database() -> FakeDatabase:
    return FakeDatabase(row=PROFILE)


@pytest.fixture
def client(keys: KeyPair, database: FakeDatabase) -> Iterator[TestClient]:
    settings = Settings(environment="test", supabase_jwt_issuer=ISSUER, _env_file=None)
    app = create_app(settings, database=database, key_provider=StaticKeyProvider(keys))  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


def bearer(keys: KeyPair, **kw: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(keys, claims(kw.pop('sub', USER), **kw))}"}


# ── Authentication failures: always the same generic 401 envelope ───────────────────────────────
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "bearer "},
    ],
)
def test_me_requires_a_valid_bearer_token(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    error = response.json()["error"]
    assert error["code"] == "UNAUTHENTICATED"
    assert error["request_id"] == response.headers["x-request-id"]


def test_the_failure_reason_is_never_revealed_to_the_caller(client: TestClient, keys: KeyPair) -> None:
    bodies = {
        client.get("/api/v1/me", headers=bearer(keys, expires_in=-600)).text,
        client.get("/api/v1/me", headers=bearer(keys, aud="anon")).text,
        client.get("/api/v1/me", headers=bearer(keys, iss="https://evil.example")).text,
        client.get("/api/v1/me", headers={"Authorization": "Bearer junk"}).text,
    }
    # Same message every time apart from the request ID.
    messages = {b.split('"request_id"')[0] for b in bodies}
    assert len(messages) == 1
    assert "expired" not in "".join(bodies).lower() and "audience" not in "".join(bodies).lower()


def test_a_database_session_is_never_opened_for_a_rejected_token(
    client: TestClient, database: FakeDatabase
) -> None:
    client.get("/api/v1/me", headers={"Authorization": "Bearer junk"})
    assert database.users == []


def test_token_rejections_are_logged_by_reason_but_never_with_the_token(
    client: TestClient, keys: KeyPair, caplog: pytest.LogCaptureFixture
) -> None:
    token = mint(keys, claims(USER, expires_in=-600))
    with caplog.at_level(logging.INFO, logger="advisorai.auth"):
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "expired" in text
    assert token not in text and "eyJ" not in text


# ── Success: the identity comes from the verified token and nothing else ────────────────────────
def test_me_returns_the_callers_own_profile(
    client: TestClient, keys: KeyPair, database: FakeDatabase
) -> None:
    response = client.get("/api/v1/me", headers=bearer(keys))
    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(USER),
        "display_name": "Demo User",
        "locale": "en",
        "data_mode": "synthetic_only",
    }
    assert [u.user_id for u in database.users] == [USER]


def test_the_database_session_is_opened_for_the_verified_subject_only(
    client: TestClient, keys: KeyPair, database: FakeDatabase
) -> None:
    client.get("/api/v1/me", headers=bearer(keys, sub=OTHER))
    assert [u.user_id for u in database.users] == [OTHER]


@pytest.mark.parametrize(
    "spoof",
    [
        {"X-User-Id": str(OTHER)},
        {"X-Owner-User-Id": str(OTHER)},
        {"X-Forwarded-User": str(OTHER)},
        {"X-Supabase-User": str(OTHER)},
        {"Cookie": f"user_id={OTHER}"},
    ],
)
def test_spoofed_identity_headers_change_nothing(
    client: TestClient, keys: KeyPair, database: FakeDatabase, spoof: dict[str, str]
) -> None:
    client.get("/api/v1/me", headers={**bearer(keys), **spoof})
    assert [u.user_id for u in database.users] == [USER]


def test_spoofed_query_parameters_and_bodies_change_nothing(
    client: TestClient, keys: KeyPair, database: FakeDatabase
) -> None:
    client.get(f"/api/v1/me?user_id={OTHER}&owner_user_id={OTHER}&sub={OTHER}", headers=bearer(keys))
    assert [u.user_id for u in database.users] == [USER]


def test_no_route_accepts_a_user_or_owner_id_from_the_client(client: TestClient) -> None:
    """ADR 0005, step 5: identity only ever comes from the verified token."""
    forbidden = {"user_id", "owner_user_id", "sub", "actor_user_id", "owner_id"}
    spec = client.get("/api/v1/openapi.json").json()
    seen: set[str] = set()
    for operations in spec["paths"].values():
        for operation in operations.values():
            for parameter in operation.get("parameters", []):
                seen.add(parameter["name"].lower())
            body = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            ref = body.get("$ref", "").rsplit("/", 1)[-1]
            seen.update(spec["components"]["schemas"].get(ref, body).get("properties", {}))
    assert seen.isdisjoint(forbidden), f"routes accept identity from the client: {seen & forbidden}"


def test_a_missing_profile_is_a_404_envelope(keys: KeyPair, database: FakeDatabase) -> None:
    settings = Settings(environment="test", supabase_jwt_issuer=ISSUER, _env_file=None)
    empty = FakeDatabase(row=None)
    app = create_app(settings, database=empty, key_provider=StaticKeyProvider(keys))  # type: ignore[arg-type]
    with TestClient(app) as c:
        response = c.get("/api/v1/me", headers=bearer(keys))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROFILE_NOT_FOUND"


# ── Not configured ──────────────────────────────────────────────────────────────────────────────
def test_without_auth_configuration_protected_routes_are_503_not_open(keys: KeyPair) -> None:
    settings = Settings(environment="test", _env_file=None)
    with TestClient(create_app(settings)) as c:
        response = c.get("/api/v1/me", headers=bearer(keys))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_with_a_verifier_but_no_database_me_is_503(keys: KeyPair) -> None:
    settings = Settings(environment="test", supabase_jwt_issuer=ISSUER, _env_file=None)
    with TestClient(create_app(settings, key_provider=StaticKeyProvider(keys))) as c:
        response = c.get("/api/v1/me", headers=bearer(keys))
    assert response.status_code == 503


# ── Readiness ───────────────────────────────────────────────────────────────────────────────────
def test_ready_when_the_database_answers(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_not_ready_without_a_database(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        response = c.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["error"]["details"] == {"checks": {"database": "not_configured"}}


def test_not_ready_when_the_database_fails_and_nothing_leaks(
    keys: KeyPair, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "postgresql://app_backend:hunter2@db.internal:5432/postgres"
    broken = FakeDatabase(ping_error=ConnectionError(f"could not connect to {secret}"))
    settings = Settings(environment="test", _env_file=None)
    with (
        TestClient(create_app(settings, database=broken)) as c,  # type: ignore[arg-type]
        caplog.at_level(logging.WARNING, logger="advisorai.health"),
    ):
        response = c.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"checks": {"database": "unavailable"}}
    assert "hunter2" not in response.text
    assert "hunter2" not in " ".join(r.getMessage() for r in caplog.records)


def test_health_endpoints_expose_no_personal_data(client: TestClient) -> None:
    for path in ("/api/v1/health", "/api/v1/health/ready"):
        text = client.get(path).text.lower()
        assert "email" not in text and "postgres" not in text


def test_every_route_with_optional_response_fields_omits_them_instead_of_sending_null(
    client: TestClient,
) -> None:
    """FastAPI serialises responses itself and would emit `null` for unset optional fields."""
    from fastapi.routing import APIRoute

    from app.schemas.common import WireModel

    for route in client.app.routes:  # type: ignore[attr-defined]
        if not isinstance(route, APIRoute) or not (
            isinstance(route.response_model, type) and issubclass(route.response_model, WireModel)
        ):
            continue
        has_optional = any(not f.is_required() for f in route.response_model.model_fields.values())
        assert not has_optional or route.response_model_exclude_none, (
            f"{route.path} can emit null for an unset optional field: set response_model_exclude_none=True"
        )
