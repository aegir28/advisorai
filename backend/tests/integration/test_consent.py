"""POST /me/consent through the real app and RLS."""

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.main import create_app
from tests.integration.conftest import Admin
from tests.support import ISSUER, StaticKeyProvider, claims, make_keypair, mint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]


@pytest.fixture
async def api(
    app_database_url: SecretStr, system_database_url: SecretStr
) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    keys = make_keypair("k")
    settings = Settings(
        environment="test",
        database_url=app_database_url,
        system_database_url=system_database_url,
        supabase_jwt_issuer=ISSUER,
        _env_file=None,
    )
    app = create_app(settings, key_provider=StaticKeyProvider(keys))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, keys
    await app.state.database.dispose()


def h(keys: Any, user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(keys, claims(user_id))}"}


async def test_accepting_the_notice_is_recorded_for_the_caller_only(
    api: tuple[httpx.AsyncClient, Any], make_user: MakeUser, admin: Admin
) -> None:
    client, keys = api
    a, b = await make_user(), await make_user()
    before = (await client.get("/api/v1/me", headers=h(keys, a.user_id))).json()
    assert "consented_at" not in before

    r = await client.post(
        "/api/v1/me/consent", json={"version": "prototype-2026-10"}, headers=h(keys, a.user_id)
    )
    assert (
        r.status_code == 200
        and r.json()["consent_version"] == "prototype-2026-10"
        and r.json()["consented_at"]
    )
    first = r.json()["consented_at"]
    # Same version again: the original time is kept.
    again = await client.post(
        "/api/v1/me/consent", json={"version": "prototype-2026-10"}, headers=h(keys, a.user_id)
    )
    assert again.json()["consented_at"] == first
    # B is untouched.
    assert "consented_at" not in (await client.get("/api/v1/me", headers=h(keys, b.user_id))).json()
    rows = await admin("select consent_version from public.profiles where user_id = :u", {"u": b.user_id})
    assert rows[0]["consent_version"] is None


@pytest.mark.parametrize(
    "body",
    [{}, {"version": ""}, {"version": "has space"}, {"version": "x" * 41}, {"version": "v", "user_id": "x"}],
)
async def test_invalid_consent_bodies_are_rejected(
    api: tuple[httpx.AsyncClient, Any], make_user: MakeUser, body: dict[str, Any]
) -> None:
    client, keys = api
    user = await make_user()
    r = await client.post("/api/v1/me/consent", json=body, headers=h(keys, user.user_id))
    assert r.status_code == 422


async def test_consent_requires_a_token(api: tuple[httpx.AsyncClient, Any]) -> None:
    client, _ = api
    assert (await client.post("/api/v1/me/consent", json={"version": "v1"})).status_code == 401
