"""Audit writer, signed-URL gateway, document URL service and log redaction (no database needed)."""

import io
import json
import logging
import uuid
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.audit.writer import ALLOWED_METADATA_KEYS, AuditAction, AuditError, AuditWriter, validate_metadata
from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import RedactingFormatter, redact
from app.core.request_id import RequestIdFilter
from app.db.database import Database, SystemOperation, SystemPathUnavailableError
from app.storage.gateway import SignedUrl, StorageError, StoragePath, SupabaseStorageGateway
from app.storage.service import DocumentUrlService
from tests.support import FakeDatabase

pytestmark = pytest.mark.anyio

SECRET = SecretStr("0123456789abcdef0123456789abcdef-test-hmac")
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
CASE = uuid.UUID("22222222-2222-4222-8222-222222222222")
DOC = uuid.UUID("33333333-3333-4333-8333-333333333333")


# ── Audit writer ────────────────────────────────────────────────────────────────────────────────
def test_metadata_must_use_the_allow_list_and_short_scalars() -> None:
    assert validate_metadata({"result": "success", "count": 3, "ttl_seconds": 300}) == {
        "result": "success",
        "count": 3,
        "ttl_seconds": 300,
    }
    for bad in (
        {"snippet": "HbA1c 8.9"},
        {"email": "a@b.c"},
        {"name": "Someone"},
        {"url": "https://x"},
        {"result": "x" * 500},
        {"result": {"nested": "object"}},
        {"result": ["a"]},
        {"result": None},
    ):
        with pytest.raises(AuditError):
            validate_metadata(bad)


def test_the_allow_list_contains_nothing_that_could_carry_content_or_identity() -> None:
    risky = {
        "text",
        "content",
        "snippet",
        "value",
        "concern",
        "title",
        "note",
        "prompt",
        "response",
        "name",
        "display_name",
        "email",
        "phone",
        "address",
        "ip",
        "token",
        "jwt",
        "url",
        "signed_url",
    }
    assert ALLOWED_METADATA_KEYS.isdisjoint(risky)


def test_the_client_ip_is_stored_only_as_an_hmac() -> None:
    writer = AuditWriter(FakeDatabase(), SECRET)  # type: ignore[arg-type]
    digest = writer.hash_ip("203.0.113.9")
    assert digest is not None and len(digest) == 64 and "203" not in digest
    assert digest == writer.hash_ip("203.0.113.9")  # deterministic, so it can be correlated
    assert digest != writer.hash_ip("203.0.113.10")
    other = AuditWriter(FakeDatabase(), SecretStr("another-secret-another-secret-0000000"))  # type: ignore[arg-type]
    assert other.hash_ip("203.0.113.9") != digest  # depends on the server-side secret


def test_ip_hashing_canonicalises_and_degrades_safely() -> None:
    writer = AuditWriter(FakeDatabase(), SECRET)  # type: ignore[arg-type]
    assert writer.hash_ip("2001:DB8::1") == writer.hash_ip("2001:0db8:0000:0000:0000:0000:0000:0001")
    assert writer.hash_ip(None) is None
    assert writer.hash_ip("not-an-ip") is None
    assert AuditWriter(FakeDatabase(), None).hash_ip("203.0.113.9") is None  # type: ignore[arg-type]


async def test_record_uses_the_system_path_and_writes_no_raw_ip_or_content() -> None:
    database = FakeDatabase()
    writer = AuditWriter(database, SECRET)  # type: ignore[arg-type]
    await writer.record(
        AuditAction.CASE_CREATE,
        actor=USER,
        target_type="case",
        target_id=str(CASE),
        client_ip="203.0.113.9",
        metadata={"result": "success"},
    )
    assert database.system_operations == [SystemOperation.AUDIT_APPEND]
    assert database.users == []  # never the user path: the audit row must not depend on user grants
    statement, params = database.executed[0]
    assert "audit_logs" in statement
    assert params["action"] == "case.create" and params["actor"] == USER
    assert params["request_id"].startswith("req_")
    assert "203.0.113.9" not in json.dumps(params, default=str)
    assert len(params["ip_hash"]) == 64
    assert json.loads(params["metadata"]) == {"result": "success"}


async def test_record_rejects_content_before_touching_the_database() -> None:
    database = FakeDatabase()
    writer = AuditWriter(database, SECRET)  # type: ignore[arg-type]
    with pytest.raises(AuditError):
        await writer.record(AuditAction.CASE_UPDATE, actor=USER, metadata={"snippet": "HbA1c 8.9 %"})
    assert database.executed == [] and database.system_operations == []


async def test_system_session_accepts_only_an_enumerated_operation() -> None:
    database = Database(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        async with database.system_session("audit.append"):  # type: ignore[arg-type]
            pass


async def test_without_a_system_connection_the_system_path_fails_closed() -> None:
    """No fallback to the user connection: the audit writer errors rather than borrowing app_backend."""
    database = Database(None)  # type: ignore[arg-type]
    with pytest.raises(SystemPathUnavailableError):
        async with database.system_session(SystemOperation.AUDIT_APPEND):
            pass
    writer = AuditWriter(database, SECRET)
    with pytest.raises(SystemPathUnavailableError):
        await writer.record(AuditAction.CASE_CREATE, actor=USER)


# ── Signed-URL gateway ──────────────────────────────────────────────────────────────────────────
KEY = "service-role-key-for-tests"


def gateway(handler: Any, **overrides: Any) -> tuple[SupabaseStorageGateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[no-any-return]

    settings = Settings(
        environment="test",
        supabase_url="http://127.0.0.1:54321",
        supabase_service_role_key=SecretStr(KEY),
        _env_file=None,
        **overrides,
    )
    return SupabaseStorageGateway(settings, httpx.AsyncClient(transport=httpx.MockTransport(record))), seen


PATH = StoragePath(USER, CASE, DOC)


def test_the_storage_path_is_owner_case_document() -> None:
    assert str(PATH) == f"{USER}/{CASE}/{DOC}"


async def test_download_urls_are_signed_for_five_minutes_with_the_service_key_in_headers_only() -> None:
    gw, seen = gateway(
        lambda r: httpx.Response(200, json={"signedURL": "/object/sign/case-documents/x?token=SECRETTOKEN"})
    )
    url = await gw.create_download_url(PATH)
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"http://127.0.0.1:54321/storage/v1/object/sign/case-documents/{PATH}"
    assert json.loads(request.content) == {"expiresIn": 300}
    assert request.headers["authorization"] == f"Bearer {KEY}" and request.headers["apikey"] == KEY
    assert KEY not in str(request.url)
    assert url.expires_in == 300
    assert url.reveal() == "http://127.0.0.1:54321/storage/v1/object/sign/case-documents/x?token=SECRETTOKEN"


async def test_a_signed_url_can_never_outlive_five_minutes() -> None:
    with pytest.raises(ValueError):
        Settings(environment="test", signed_url_ttl_seconds=3600, _env_file=None)
    gw, seen = gateway(
        lambda r: httpx.Response(200, json={"signedURL": "/x?token=t"}), signed_url_ttl_seconds=120
    )
    await gw.create_download_url(PATH)
    assert json.loads(seen[0].content) == {"expiresIn": 120}


async def test_a_signed_url_redacts_itself_everywhere() -> None:
    url = SignedUrl("http://host/storage/v1/object/sign/b/p?token=SECRETTOKEN", 300)
    for rendering in (repr(url), str(url), f"{url}", f"{url!r}", "%s" % url, str([url])):  # noqa: UP031
        assert "SECRETTOKEN" not in rendering and "http" not in rendering
    assert "expires_in=300" in repr(url)


async def test_upload_and_delete_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "upload/sign" in str(request.url):
            return httpx.Response(
                200, json={"url": "/object/upload/sign/case-documents/x?token=UP", "token": "UP"}
            )
        return httpx.Response(200, json=[])

    gw, seen = gateway(handler)
    upload = await gw.create_upload_url(PATH)
    assert "UP" not in repr(upload)
    await gw.delete_objects([PATH])
    assert seen[1].method == "DELETE" and json.loads(seen[1].content) == {"prefixes": [str(PATH)]}
    await gw.delete_objects([])
    assert len(seen) == 2  # nothing sent for an empty list


async def test_errors_never_contain_urls_tokens_or_keys() -> None:
    gw, _ = gateway(lambda r: httpx.Response(500, json={"message": f"failed for {KEY} token=ABC {r.url}"}))
    with pytest.raises(StorageError) as caught:
        await gw.create_download_url(PATH)
    assert (
        KEY not in str(caught.value) and "token=" not in str(caught.value) and "http" not in str(caught.value)
    )

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    gw2, _ = gateway(boom)
    with pytest.raises(StorageError) as caught2:
        await gw2.create_download_url(PATH)
    assert "http" not in str(caught2.value)


async def test_an_unexpected_response_is_an_error_not_a_url() -> None:
    gw, _ = gateway(lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(StorageError):
        await gw.create_download_url(PATH)


def test_the_gateway_needs_its_configuration() -> None:
    with pytest.raises(ValueError):
        SupabaseStorageGateway(Settings(environment="test", _env_file=None), httpx.AsyncClient())


# ── DocumentUrlService: ownership (RLS), then sign, then audit ──────────────────────────────────
class FakeStorage:
    def __init__(self) -> None:
        self.paths: list[StoragePath] = []

    async def create_download_url(self, path: StoragePath) -> SignedUrl:
        self.paths.append(path)
        return SignedUrl("http://signed.example/?token=TOPSECRET", 300)

    async def create_upload_url(self, path: StoragePath) -> SignedUrl:
        raise NotImplementedError

    async def delete_objects(self, paths: list[StoragePath]) -> None:
        raise NotImplementedError


def service(row: dict[str, Any] | None) -> tuple[DocumentUrlService, FakeDatabase, FakeStorage]:
    database, storage = FakeDatabase(row=row), FakeStorage()
    audit = AuditWriter(database, SECRET)  # type: ignore[arg-type]
    return DocumentUrlService(database, audit, storage), database, storage  # type: ignore[arg-type]


async def test_issuing_a_url_checks_ownership_signs_and_audits_without_the_url() -> None:
    svc, database, storage = service({"id": DOC, "owner_user_id": USER, "case_id": CASE, "status": "ready"})
    url = await svc.issue_download_url(CurrentUser(USER), DOC, client_ip="203.0.113.9")
    assert url.reveal().endswith("TOPSECRET")
    assert [u.user_id for u in database.users] == [USER]  # the lookup ran under the user's RLS context
    assert storage.paths == [PATH]
    assert database.system_operations == [SystemOperation.AUDIT_APPEND]
    audit_statement, audit_params = database.executed[-1]
    assert "audit_logs" in audit_statement
    assert audit_params["action"] == "document.signed_url_issued"
    assert "TOPSECRET" not in json.dumps(audit_params, default=str)
    assert json.loads(audit_params["metadata"]) == {"ttl_seconds": 300}


@pytest.mark.parametrize(
    "row", [None, {"id": DOC, "owner_user_id": USER, "case_id": CASE, "status": "pending_upload"}]
)
async def test_missing_foreign_and_incomplete_documents_look_identical(row: dict[str, Any] | None) -> None:
    svc, database, storage = service(row)
    with pytest.raises(AppError) as caught:
        await svc.issue_download_url(CurrentUser(USER), DOC)
    assert caught.value.status_code == 404 and caught.value.code.value == "DOCUMENT_NOT_FOUND"
    assert storage.paths == [] and database.system_operations == []  # nothing signed, nothing audited


# ── Redaction ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "gone"),
    [
        ("token eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl end", "eyJhbGci"),
        ("Authorization: Bearer abc.def.ghi-123", "abc.def.ghi-123"),
        ("GET /object/sign/b/p?token=SECRETTOKEN&x=1", "SECRETTOKEN"),
        ("apikey=KEYKEYKEY", "KEYKEYKEY"),
        ("connect postgresql://app_backend:hunter2@db:5432/postgres failed", "hunter2"),
    ],
)
def test_redaction_removes_secrets(raw: str, gone: str) -> None:
    assert gone not in redact(raw)


def test_the_log_formatter_redacts_whatever_slips_into_a_message() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(request_id)s %(message)s"))
    handler.addFilter(RequestIdFilter())
    log = logging.getLogger("advisorai.test_redaction")
    log.handlers, log.propagate = [handler], False
    log.setLevel(logging.INFO)
    log.info("signed %s", "http://h/storage/v1/object/sign/b/p?token=LEAKYTOKEN")
    log.info("user sent Bearer eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln")
    log.info("url object: %s", SignedUrl("http://h/?token=ANOTHERSECRET", 300))
    output = stream.getvalue()
    assert "LEAKYTOKEN" not in output and "eyJhbGci" not in output and "ANOTHERSECRET" not in output


def test_httpx_request_logging_is_silenced() -> None:
    from app.core.logging import configure_logging

    configure_logging("INFO")
    assert logging.getLogger("httpx").level >= logging.WARNING


# ── read_object (used to validate an upload) ────────────────────────────────────────────────────
async def test_read_object_returns_the_bytes_from_the_authenticated_object_route() -> None:
    gw, seen = gateway(lambda request: httpx.Response(200, content=b"%PDF-1.7 data"))
    assert await gw.read_object(PATH, max_bytes=100) == b"%PDF-1.7 data"
    assert seen[0].method == "GET"
    assert str(seen[0].url).endswith(f"/storage/v1/object/authenticated/case-documents/{PATH}")
    assert seen[0].headers["Authorization"].startswith("Bearer ")  # the service key, backend-only


@pytest.mark.parametrize("status", [400, 404])
async def test_read_object_maps_a_missing_object_to_not_found(status: int) -> None:
    from app.storage.gateway import ObjectNotFoundError

    gw, _ = gateway(lambda request: httpx.Response(status, json={"error": "not_found"}))
    with pytest.raises(ObjectNotFoundError):
        await gw.read_object(PATH, max_bytes=100)


async def test_read_object_stops_at_the_size_limit() -> None:
    from app.storage.gateway import ObjectTooLargeError

    gw, _ = gateway(lambda request: httpx.Response(200, content=b"x" * 101))
    with pytest.raises(ObjectTooLargeError):
        await gw.read_object(PATH, max_bytes=100)
    gw2, _ = gateway(lambda request: httpx.Response(200, content=b"x" * 100))
    assert len(await gw2.read_object(PATH, max_bytes=100)) == 100


async def test_read_object_errors_never_contain_the_url_or_key() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("could not connect to http://127.0.0.1:54321/?token=SECRET-TOKEN")

    gw, _ = gateway(boom)
    with pytest.raises(StorageError) as network:
        await gw.read_object(PATH, max_bytes=100)
    gw2, _ = gateway(lambda request: httpx.Response(500, text="internal"))
    with pytest.raises(StorageError) as server:
        await gw2.read_object(PATH, max_bytes=100)
    for exc in (network.value, server.value):
        assert "SECRET" not in str(exc) and "127.0.0.1" not in str(exc) and str(PATH) not in str(exc)
    assert "500" in str(server.value)
