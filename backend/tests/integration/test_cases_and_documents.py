"""The case and document API end to end: real app, real JWT verification, real PostgreSQL under RLS, and an
in-memory storage standing in for the browser's upload to private storage.

What these prove: ownership (user B never sees, completes or deletes user A's anything), the upload
validation outcomes, the delete/purge order, and that audit rows carry no content.
"""

import io
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from pypdf import PdfWriter

from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.main import create_app
from tests.integration.conftest import Admin
from tests.support import ISSUER, InMemoryStorage, StaticKeyProvider, claims, make_keypair, mint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]
HMAC = SecretStr("0123456789abcdef0123456789abcdef-integration")

NEW_CASE = {
    "intent": "Understanding my treatment",
    "concern": "Is this procedure necessary now?",
    "proposed_treatment": "A procedure",
    "age_years": 52,
    "sex": "M",
}
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic image bytes"


def pdf(pages: int = 1, *, password: str | None = None, salt: bytes = b"") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "synthetic " + salt.decode()})
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class Api:
    def __init__(self, client: httpx.AsyncClient, keys: Any, storage: InMemoryStorage) -> None:
        self.client, self.keys, self.storage = client, keys, storage

    def h(self, user: CurrentUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {mint(self.keys, claims(user.user_id))}"}

    async def create_case(self, user: CurrentUser, **over: Any) -> dict[str, Any]:
        r = await self.client.post("/api/v1/cases", json={**NEW_CASE, **over}, headers=self.h(user))
        assert r.status_code == 201, r.text
        return r.json()  # type: ignore[no-any-return]

    async def upload(
        self,
        user: CurrentUser,
        case_id: str,
        data: bytes | None,
        *,
        mime: str = "application/pdf",
        name: str = "report.pdf",
    ) -> httpx.Response:
        """upload-url -> (browser PUT) -> complete. `data=None` skips the PUT. The declared size is
        client-controlled, so it is capped here and the real object may be bigger."""
        r = await self.client.post(
            f"/api/v1/cases/{case_id}/documents/upload-url",
            json={"name": name, "type": "lab", "mime_type": mime, "size_bytes": min(len(data or b"x"), 1024)},
            headers=self.h(user),
        )
        assert r.status_code == 200, r.text
        doc_id = r.json()["document_id"]
        if data is not None:
            self.storage.put(f"{user.user_id}/{case_id}/{doc_id}", data)
        done = await self.client.post(
            f"/api/v1/cases/{case_id}/documents/{doc_id}/complete", headers=self.h(user)
        )
        done.request.extensions["doc_id"] = doc_id
        return done


@pytest.fixture
async def api(app_database_url: SecretStr, system_database_url: SecretStr) -> AsyncIterator[Api]:
    keys = make_keypair("integration-key")
    storage = InMemoryStorage()
    settings = Settings(
        environment="test",
        database_url=app_database_url,
        system_database_url=system_database_url,
        supabase_jwt_issuer=ISSUER,
        audit_ip_hmac_secret=HMAC,
        max_documents_per_case=3,
        _env_file=None,
    )
    app = create_app(settings, key_provider=StaticKeyProvider(keys), storage=storage)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Api(client, keys, storage)
    await app.state.database.dispose()


# ── Cases ───────────────────────────────────────────────────────────────────────────────────────
async def test_create_get_and_list_a_case(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    assert case["status"] == "awaiting_upload" and case["document_count"] == 0
    assert case["code"].startswith("AC-") and case["age_years"] == 52 and case["sex"] == "M"
    assert case["title"] == "Understanding my treatment"
    assert not {"owner_user_id", "user_id", "owner_label", "email", "name"} & set(case)

    got = await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(user))
    assert got.status_code == 200 and got.json() == case
    listed = await api.client.get("/api/v1/cases", headers=api.h(user))
    assert [c["id"] for c in listed.json()] == [case["id"]]


async def test_a_user_cannot_see_or_delete_another_users_case(api: Api, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    case = await api.create_case(a)
    for method in ("get", "delete"):
        r = await getattr(api.client, method)(f"/api/v1/cases/{case['id']}", headers=api.h(b))
        assert r.status_code == 404 and r.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert (await api.client.get("/api/v1/cases", headers=api.h(b))).json() == []
    assert (await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(a))).status_code == 200


async def test_requests_without_a_valid_token_are_401(api: Api) -> None:
    for method, path in (("get", "/cases"), ("post", "/cases"), ("get", f"/cases/{uuid.uuid4()}")):
        r = await getattr(api.client, method)(f"/api/v1{path}")
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_the_client_cannot_choose_the_owner(api: Api, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    r = await api.client.post(
        "/api/v1/cases", json={**NEW_CASE, "owner_user_id": str(b.user_id)}, headers=api.h(a)
    )
    assert r.status_code == 422
    assert (await api.client.get("/api/v1/cases", headers=api.h(b))).json() == []


@pytest.mark.parametrize(
    "bad",
    [{"age_years": 121}, {"age_years": -1}, {"concern": "  "}, {"sex": "Q"}, {"age_years": "52"}],
)
async def test_invalid_case_input_is_rejected(api: Api, make_user: MakeUser, bad: dict[str, Any]) -> None:
    user = await make_user()
    r = await api.client.post("/api/v1/cases", json={**NEW_CASE, **bad}, headers=api.h(user))
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_creating_a_case_is_audited_without_any_content(
    api: Api, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    case = await api.create_case(user, concern="my very private concern 12345")
    rows = await admin(
        "select action, target_type, target_id, metadata::text m from public.audit_logs where actor_user_id = :u",
        {"u": user.user_id},
    )
    assert [(r["action"], r["target_id"]) for r in rows] == [("case.create", case["id"])]
    assert "private" not in rows[0]["m"] and rows[0]["m"] == "{}"


async def test_deleting_a_case_removes_rows_files_and_patient_and_audits_it(
    api: Api, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    ok = await api.upload(user, case["id"], pdf())
    assert ok.status_code == 200
    pending = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/upload-url",
        json={"name": "p.pdf", "mime_type": "application/pdf", "size_bytes": 5},
        headers=api.h(user),
    )
    api.storage.put(f"{user.user_id}/{case['id']}/{pending.json()['document_id']}", b"%PDF-x")
    assert len(api.storage.objects) == 2

    r = await api.client.delete(f"/api/v1/cases/{case['id']}", headers=api.h(user))
    assert r.status_code == 204 and api.storage.objects == {}
    assert (await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(user))).status_code == 404
    left = await admin(
        "select (select count(*) from public.cases where id = :c) + (select count(*) from public.documents"
        " where case_id = :c) + (select count(*) from public.patients where owner_user_id = :u) n",
        {"c": uuid.UUID(case["id"]), "u": user.user_id},
    )
    assert left[0]["n"] == 0
    actions = {
        r["action"]
        for r in await admin(
            "select action from public.audit_logs where actor_user_id = :u", {"u": user.user_id}
        )
    }
    assert {"case.create", "document.upload", "case.delete", "data.deletion"} <= actions


async def test_a_failed_storage_purge_keeps_the_case_hidden_and_a_retry_finishes_it(
    api: Api, make_user: MakeUser
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    await api.upload(user, case["id"], pdf())
    api.storage.fail_deletes = True
    r = await api.client.delete(f"/api/v1/cases/{case['id']}", headers=api.h(user))
    assert r.status_code == 503 and r.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    # The case is hidden and takes no new uploads while it is being removed...
    assert (await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(user))).status_code == 404
    assert (await api.client.get("/api/v1/cases", headers=api.h(user))).json() == []
    up = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/upload-url",
        json={"name": "x.pdf", "mime_type": "application/pdf", "size_bytes": 5},
        headers=api.h(user),
    )
    assert up.status_code == 404
    # ...and the same DELETE can simply be retried.
    api.storage.fail_deletes = False
    assert (await api.client.delete(f"/api/v1/cases/{case['id']}", headers=api.h(user))).status_code == 204
    assert api.storage.objects == {}


# ── Documents ───────────────────────────────────────────────────────────────────────────────────
async def test_the_upload_flow_for_a_valid_pdf(api: Api, make_user: MakeUser, admin: Admin) -> None:
    user = await make_user()
    case = await api.create_case(user)
    r = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/upload-url",
        json={"name": "labs.pdf", "type": "lab", "mime_type": "application/pdf", "size_bytes": 100},
        headers=api.h(user),
    )
    assert r.status_code == 200
    body = r.json()
    doc_id = body["document_id"]
    assert body["upload_url"].startswith("https://storage.test/upload/") and body["expires_in"] > 0
    # The path is built from IDs only, in the owner/case/document layout.
    assert api.storage.issued == [f"{user.user_id}/{case['id']}/{doc_id}"]
    # A pending upload is internal: not listed, not counted.
    assert (await api.client.get(f"/api/v1/cases/{case['id']}/documents", headers=api.h(user))).json() == []

    api.storage.put(api.storage.issued[0], pdf(3))
    done = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/{doc_id}/complete", headers=api.h(user)
    )
    assert done.status_code == 200
    item = done.json()
    assert (
        item["status"] == "ready"
        and item["pages"] == 3
        and item["name"] == "labs.pdf"
        and item["type"] == "lab"
    )
    assert "note" not in item and item["size_kb"] > 0
    assert (await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(user))).json()[
        "document_count"
    ] == 1
    row = (
        await admin(
            "select sha256, uploaded_at, mime_type from public.documents where id = :d",
            {"d": uuid.UUID(doc_id)},
        )
    )[0]
    assert len(row["sha256"]) == 64 and row["uploaded_at"] and row["mime_type"] == "application/pdf"


async def test_completing_twice_is_harmless(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    first = await api.upload(user, case["id"], pdf())
    doc_id = first.json()["id"]
    again = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/{doc_id}/complete", headers=api.h(user)
    )
    assert again.status_code == 200 and again.json() == first.json()


async def test_completing_before_the_file_arrived_is_409(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    r = await api.upload(user, case["id"], None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "UPLOAD_NOT_RECEIVED"


@pytest.mark.parametrize(
    ("data", "mime", "note"),
    [
        (b"MZ\x90\x00 definitely an executable", "application/pdf", "Only PDF, JPG and PNG"),
        (PNG, "application/pdf", "does not match"),
        (pdf(), "image/png", "does not match"),
        (b"%PDF-1.4 truncated garbage", "application/pdf", "could not open"),
        (pdf(password="secret"), "application/pdf", "password protected"),
        (b"", "application/pdf", "empty"),
    ],
)
async def test_bad_files_need_attention_and_are_not_kept(
    api: Api, make_user: MakeUser, data: bytes, mime: str, note: str
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    r = await api.upload(user, case["id"], data, mime=mime)
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["status"] == "needs_attention" and note in item["note"]
    assert api.storage.objects == {}  # the unsafe or unreadable file was discarded
    listed = (await api.client.get(f"/api/v1/cases/{case['id']}/documents", headers=api.h(user))).json()
    assert [d["status"] for d in listed] == ["needs_attention"]


async def test_a_png_is_ready_with_one_page(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    r = await api.upload(user, case["id"], PNG, mime="image/png", name="scan.png")
    assert r.json()["status"] == "ready" and r.json()["pages"] == 1


async def test_the_same_file_twice_is_a_duplicate_and_one_copy_is_kept(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    data = pdf(2, salt=b"same")
    first = await api.upload(user, case["id"], data)
    second = await api.upload(user, case["id"], data)
    assert first.json()["status"] == "ready" and second.json()["status"] == "duplicate"
    assert "same as a document you already added" in second.json()["note"]
    assert list(api.storage.objects) == [f"{user.user_id}/{case['id']}/{first.json()['id']}"]
    # Identical content in a DIFFERENT case is not a duplicate.
    other = await api.create_case(user)
    assert (await api.upload(user, other["id"], data)).json()["status"] == "ready"


async def test_a_file_over_20_mb_is_rejected(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    r = await api.upload(user, case["id"], b"%PDF-" + b"0" * (20 * 1024 * 1024 + 1))
    assert r.json()["status"] == "needs_attention" and "20 MB" in r.json()["note"]
    assert api.storage.objects == {}


async def test_declared_size_and_type_are_validated_before_a_url_is_issued(
    api: Api, make_user: MakeUser
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    url = f"/api/v1/cases/{case['id']}/documents/upload-url"
    for bad in (
        {"mime_type": "application/x-msdownload", "size_bytes": 10},
        {"mime_type": "application/pdf", "size_bytes": 20 * 1024 * 1024 + 1},
        {"mime_type": "application/pdf", "size_bytes": 0},
        {"mime_type": "application/pdf", "size_bytes": 10, "name": ""},
        {"mime_type": "application/pdf", "size_bytes": 10, "storage_path": "x/y/z"},
    ):
        r = await api.client.post(url, json={"name": "a.pdf", **bad}, headers=api.h(user))
        assert r.status_code == 422, bad
    assert api.storage.issued == []


async def test_documents_of_another_user_are_invisible_and_untouchable(api: Api, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    case = await api.create_case(a)
    done = await api.upload(a, case["id"], pdf())
    doc_id = done.json()["id"]
    base = f"/api/v1/cases/{case['id']}/documents"
    assert (await api.client.get(base, headers=api.h(b))).status_code == 404
    up = await api.client.post(
        f"{base}/upload-url",
        json={"name": "x.pdf", "mime_type": "application/pdf", "size_bytes": 5},
        headers=api.h(b),
    )
    assert up.status_code == 404
    assert (await api.client.post(f"{base}/{doc_id}/complete", headers=api.h(b))).status_code == 404
    assert (await api.client.delete(f"{base}/{doc_id}", headers=api.h(b))).status_code == 404
    # B's own case cannot be used to reach A's document either.
    mine = await api.create_case(b)
    r = await api.client.delete(f"/api/v1/cases/{mine['id']}/documents/{doc_id}", headers=api.h(b))
    assert r.status_code == 404
    assert len(api.storage.objects) == 1  # A's file is untouched


async def test_the_document_limit_per_case(api: Api, make_user: MakeUser) -> None:
    user = await make_user()
    case = await api.create_case(user)
    for i in range(3):
        assert (await api.upload(user, case["id"], pdf(salt=str(i).encode()))).status_code == 200
    r = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/upload-url",
        json={"name": "x.pdf", "mime_type": "application/pdf", "size_bytes": 5},
        headers=api.h(user),
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "DOCUMENT_LIMIT_REACHED"


async def test_removing_a_document_deletes_its_file_and_row(
    api: Api, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    doc_id = (await api.upload(user, case["id"], pdf())).json()["id"]
    r = await api.client.delete(f"/api/v1/cases/{case['id']}/documents/{doc_id}", headers=api.h(user))
    assert r.status_code == 204 and api.storage.objects == {}
    assert (await api.client.get(f"/api/v1/cases/{case['id']}/documents", headers=api.h(user))).json() == []
    assert (await api.client.get(f"/api/v1/cases/{case['id']}", headers=api.h(user))).json()[
        "document_count"
    ] == 0
    actions = [
        r["action"]
        for r in await admin("select action from public.audit_logs where target_id = :d", {"d": doc_id})
    ]
    assert sorted(actions) == ["document.delete", "document.upload"]


async def test_a_storage_outage_is_a_clean_503_and_leaves_no_pending_row(
    api: Api, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    case = await api.create_case(user)
    api.storage.fail_upload_url = True
    r = await api.client.post(
        f"/api/v1/cases/{case['id']}/documents/upload-url",
        json={"name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 5},
        headers=api.h(user),
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert (
        await admin(
            "select count(*) n from public.documents where case_id = :c", {"c": uuid.UUID(case["id"])}
        )
    )[0]["n"] == 0


async def test_signed_urls_and_file_content_never_reach_logs_or_audit(
    api: Api, make_user: MakeUser, admin: Admin, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    user = await make_user()
    case = await api.create_case(user)
    await api.upload(user, case["id"], pdf(), name="private-name.pdf")
    assert "SECRET-UPLOAD" not in caplog.text and "private-name" not in caplog.text
    audit = await admin(
        "select metadata::text m, target_type, target_id from public.audit_logs where actor_user_id = :u",
        {"u": user.user_id},
    )
    assert audit and all("SECRET" not in str(r) and "private-name" not in str(r) for r in audit)
