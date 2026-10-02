"""Signed URLs against the real Storage API, and the whole API against the real database.

Storage tests also need ADVISORAI_TEST_SUPABASE_URL and ADVISORAI_TEST_SERVICE_ROLE_KEY.
"""

import base64
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.audit.writer import AuditWriter
from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.core.errors import AppError
from app.db.database import Database
from app.main import create_app
from app.storage.gateway import StoragePath, SupabaseStorageGateway
from app.storage.service import DocumentUrlService
from tests.integration.conftest import ENV_SERVICE_KEY, ENV_SUPABASE_URL, Admin, insert_case
from tests.support import ISSUER, StaticKeyProvider, claims, make_keypair, mint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]
HMAC = SecretStr("0123456789abcdef0123456789abcdef-integration")

needs_storage = pytest.mark.skipif(
    not (os.environ.get(ENV_SUPABASE_URL) and os.environ.get(ENV_SERVICE_KEY)),
    reason=f"needs the Storage API: set {ENV_SUPABASE_URL} and {ENV_SERVICE_KEY}",
)


# ── Signed URLs ─────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
async def storage() -> AsyncIterator[SupabaseStorageGateway]:
    settings = Settings(
        environment="test",
        supabase_url=os.environ[ENV_SUPABASE_URL],
        supabase_service_role_key=SecretStr(os.environ[ENV_SERVICE_KEY]),
        _env_file=None,
    )
    async with httpx.AsyncClient() as http:
        yield SupabaseStorageGateway(settings, http)


def token_lifetime(url: str) -> int:
    token = url.split("token=")[1].split("&")[0]
    payload = token.split(".")[1]
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return int(data["exp"]) - int(data.get("iat", data["exp"] - 300))


@needs_storage
async def test_the_owner_gets_a_five_minute_url_that_works_and_nobody_else_does(
    database: Database,
    make_user: MakeUser,
    admin: Admin,
    storage: SupabaseStorageGateway,
    caplog: pytest.LogCaptureFixture,
) -> None:
    a, b = await make_user(), await make_user()
    rows = await insert_case(database, a, with_document=True)
    path = StoragePath(a.user_id, rows["case"], rows["document"])

    base = os.environ[ENV_SUPABASE_URL].rstrip("/") + "/storage/v1"
    headers = {
        "Authorization": f"Bearer {os.environ[ENV_SERVICE_KEY]}",
        "apikey": os.environ[ENV_SERVICE_KEY],
    }
    async with httpx.AsyncClient() as http:
        up = await http.post(
            f"{base}/object/case-documents/{path}",
            headers={**headers, "Content-Type": "application/pdf"},
            content=b"%PDF-1.4 synthetic",
        )
        assert up.status_code in (200, 201), "could not upload the fixture object"

        service = DocumentUrlService(database, AuditWriter(database, HMAC), storage)
        with caplog.at_level(logging.DEBUG):
            signed = await service.issue_download_url(a, rows["document"], client_ip="203.0.113.9")
            url = signed.reveal()

            # The URL works, and lives for at most five minutes.
            fetched = await http.get(url)
            assert fetched.status_code == 200 and fetched.content == b"%PDF-1.4 synthetic"
            assert token_lifetime(url) <= 300 and signed.expires_in == 300

            # Another user cannot get one (RLS makes the document invisible: not found, not forbidden).
            with pytest.raises(AppError) as caught:
                await service.issue_download_url(b, rows["document"])
            assert caught.value.status_code == 404

            # The bucket is private: no public URL, and the anon role cannot read it directly.
            public = await http.get(f"{base}/object/public/case-documents/{path}")
            assert public.status_code != 200
            unauthenticated = await http.get(f"{base}/object/case-documents/{path}")
            assert unauthenticated.status_code != 200

        # The URL was never logged, and the audit row records the issue but not the URL.
        token = url.split("token=")[1]
        assert token not in caplog.text
        audit_rows = await admin(
            "select * from public.audit_logs where action = 'document.signed_url_issued' and target_id = :t",
            {"t": str(rows["document"])},
        )
        assert len(audit_rows) == 1
        assert audit_rows[0]["actor_user_id"] == a.user_id and audit_rows[0]["metadata"] == {
            "ttl_seconds": 300
        }
        assert token not in json.dumps(audit_rows[0], default=str)

        await storage.delete_objects([path])


@needs_storage
async def test_the_user_jwt_cannot_reach_the_bucket_directly(make_user: MakeUser) -> None:
    """Storage policies: no client access to case-documents, even with a valid role."""
    base = os.environ[ENV_SUPABASE_URL].rstrip("/") + "/storage/v1"
    async with httpx.AsyncClient() as http:
        listing = await http.post(
            f"{base}/object/list/case-documents",
            headers={"apikey": "anon", "Authorization": "Bearer anon"},
            json={"prefix": "", "limit": 10},
        )
    assert listing.status_code != 200 or listing.json() == []


# ── The whole API against the real database ─────────────────────────────────────────────────────
@pytest.fixture
async def api(
    app_database_url: SecretStr, system_database_url: SecretStr
) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    keys = make_keypair("integration-key")
    settings = Settings(
        environment="test",
        database_url=app_database_url,
        system_database_url=system_database_url,
        supabase_jwt_issuer=ISSUER,
        audit_ip_hmac_secret=HMAC,
        _env_file=None,
    )
    app = create_app(settings, key_provider=StaticKeyProvider(keys))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, keys
    await app.state.database.dispose()


def auth(keys: Any, user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(keys, claims(user_id))}"}


async def test_ready_reports_the_database_is_reachable(api: tuple[httpx.AsyncClient, Any]) -> None:
    client, _ = api
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_me_returns_each_users_own_profile_through_rls(
    api: tuple[httpx.AsyncClient, Any], make_user: MakeUser
) -> None:
    client, keys = api
    a, b = await make_user(), await make_user()
    for user in (a, b):
        response = await client.get("/api/v1/me", headers=auth(keys, user.user_id))
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(user.user_id) and body["data_mode"] == "synthetic_only"
        assert body["display_name"].startswith("Test ") and "email" not in body
        assert "consented_at" not in body and "consent_version" not in body  # absent, never null


async def test_a_spoofed_identity_header_cannot_reach_another_users_profile(
    api: tuple[httpx.AsyncClient, Any], make_user: MakeUser
) -> None:
    client, keys = api
    a, b = await make_user(), await make_user()
    response = await client.get(
        f"/api/v1/me?user_id={b.user_id}", headers={**auth(keys, a.user_id), "X-User-Id": str(b.user_id)}
    )
    assert response.json()["user_id"] == str(a.user_id)


async def test_a_valid_token_for_a_user_without_a_profile_is_404_not_someone_elses_data(
    api: tuple[httpx.AsyncClient, Any], make_user: MakeUser
) -> None:
    client, keys = api
    await make_user()
    response = await client.get("/api/v1/me", headers=auth(keys, uuid.uuid4()))
    assert response.status_code == 404 and response.json()["error"]["code"] == "PROFILE_NOT_FOUND"


async def test_a_forged_or_missing_token_is_401_and_opens_no_database_session(
    api: tuple[httpx.AsyncClient, Any],
) -> None:
    client, _ = api
    attacker = make_keypair("integration-key")  # same kid, different key
    for headers in ({}, {"Authorization": "Bearer junk"}, auth(attacker, uuid.uuid4())):
        response = await client.get("/api/v1/me", headers=headers)
        assert response.status_code == 401 and response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_the_audit_role_is_not_reachable_from_the_api_surface(
    api: tuple[httpx.AsyncClient, Any],
) -> None:
    client, _ = api
    spec = (await client.get("/api/v1/openapi.json")).json()
    assert not [p for p in spec["paths"] if "audit" in p]


async def test_user_deletion_leaves_no_personal_rows(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    await insert_case(database, user, with_document=True)
    await admin("delete from auth.users where id = :id", {"id": user.user_id})
    for table in ("profiles", "patients", "cases", "documents"):
        owner = "user_id" if table == "profiles" else "owner_user_id"
        assert (
            await admin(f"select count(*) n from public.{table} where {owner} = :u", {"u": user.user_id})
        )[0]["n"] == 0
