"""Document metadata persistence (user-scoped connections only; see `app.db.cases`).

`pending_upload` is an internal state (ADR 0004): `list_documents` never returns it and the API never
shows it. A document's storage path is derived from its IDs (`StoragePath`), never taken from a client.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

_COLUMNS = (
    "id, case_id, owner_user_id, type, title, status, mime_type, size_bytes, sha256, pages,"
    " ocr_confidence, note, uploaded_at, created_at"
)


@dataclass(frozen=True, slots=True)
class DocumentRow:
    id: uuid.UUID
    case_id: uuid.UUID
    owner_user_id: uuid.UUID
    type: str
    title: str
    status: str
    mime_type: str | None
    size_bytes: int | None
    sha256: str | None
    pages: int | None
    ocr_confidence: float | None
    note: str | None
    uploaded_at: datetime | None
    created_at: datetime


def _row(m: Any) -> DocumentRow:
    return DocumentRow(
        id=m["id"],
        case_id=m["case_id"],
        owner_user_id=m["owner_user_id"],
        type=m["type"],
        title=m["title"],
        status=m["status"],
        mime_type=m["mime_type"],
        size_bytes=m["size_bytes"],
        sha256=m["sha256"],
        pages=m["pages"],
        ocr_confidence=float(m["ocr_confidence"]) if m["ocr_confidence"] is not None else None,
        note=m["note"],
        uploaded_at=m["uploaded_at"],
        created_at=m["created_at"],
    )


async def case_is_open(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> bool:
    """The caller's case exists and is not being deleted."""
    result = await connection.execute(
        text(
            "select 1 from public.cases"
            " where id = :id and owner_user_id = :owner and deletion_requested_at is null"
        ),
        {"id": case_id, "owner": owner},
    )
    return result.first() is not None


async def count_documents(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> int:
    result = await connection.execute(
        text("select count(*) from public.documents where case_id = :case and owner_user_id = :owner"),
        {"case": case_id, "owner": owner},
    )
    return int(result.scalar_one())


async def insert_pending(
    connection: AsyncConnection,
    owner: uuid.UUID,
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    type_: str,
    title: str,
    mime_type: str,
    size_bytes: int,
    storage_path: str,
) -> None:
    await connection.execute(
        text(
            "insert into public.documents (id, owner_user_id, case_id, type, title, status, mime_type,"
            " size_bytes, storage_path)"
            " values (:id, :owner, :case, :type, :title, 'pending_upload', :mime, :size, :path)"
        ),
        {
            "id": document_id,
            "owner": owner,
            "case": case_id,
            "type": type_,
            "title": title,
            "mime": mime_type,
            "size": size_bytes,
            "path": storage_path,
        },
    )


async def get_document(
    connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentRow | None:
    result = await connection.execute(
        text(
            f"select {_COLUMNS} from public.documents"
            " where id = :id and case_id = :case and owner_user_id = :owner"
        ),
        {"id": document_id, "case": case_id, "owner": owner},
    )
    m = result.mappings().first()
    return _row(m) if m else None


async def list_documents(
    connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID
) -> list[DocumentRow]:
    result = await connection.execute(
        text(
            f"select {_COLUMNS} from public.documents"
            " where case_id = :case and owner_user_id = :owner and status <> 'pending_upload'"
            " order by coalesce(uploaded_at, created_at), id"
        ),
        {"case": case_id, "owner": owner},
    )
    return [_row(m) for m in result.mappings()]


async def all_document_ids(
    connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every document of the case, pending ones included: all their files must go on delete."""
    result = await connection.execute(
        text("select id from public.documents where case_id = :case and owner_user_id = :owner"),
        {"case": case_id, "owner": owner},
    )
    return [r[0] for r in result]


async def has_ready_duplicate(
    connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID, document_id: uuid.UUID, sha256: str
) -> bool:
    result = await connection.execute(
        text(
            "select 1 from public.documents where case_id = :case and owner_user_id = :owner"
            " and sha256 = :sha and status = 'ready' and id <> :id"
        ),
        {"case": case_id, "owner": owner, "sha": sha256, "id": document_id},
    )
    return result.first() is not None


async def finish_upload(
    connection: AsyncConnection,
    owner: uuid.UUID,
    document_id: uuid.UUID,
    *,
    status: str,
    size_bytes: int | None,
    sha256: str | None,
    mime_type: str | None,
    pages: int | None,
    note: str | None,
) -> str:
    """Record the validation result. Returns the status actually stored: if two uploads of the same file
    finish together, the unique index lets only one become 'ready' and this one becomes 'duplicate'."""
    params = {
        "id": document_id,
        "owner": owner,
        "size": size_bytes,
        "sha": sha256,
        "mime": mime_type,
        "pages": pages,
        "note": note,
    }
    sql = text(
        "update public.documents set status = :status, size_bytes = :size, sha256 = :sha,"
        " mime_type = coalesce(:mime, mime_type), pages = :pages, note = :note, uploaded_at = now()"
        " where id = :id and owner_user_id = :owner and status = 'pending_upload'"
    )
    try:
        async with connection.begin_nested():
            await connection.execute(sql, {**params, "status": status})
        return status
    except IntegrityError:
        if status != "ready":
            raise
    async with connection.begin_nested():
        await connection.execute(
            sql,
            {**params, "status": "duplicate", "note": "This looks the same as a document you already added."},
        )
    return "duplicate"


async def delete_document(connection: AsyncConnection, owner: uuid.UUID, document_id: uuid.UUID) -> None:
    await connection.execute(
        text("delete from public.documents where id = :id and owner_user_id = :owner"),
        {"id": document_id, "owner": owner},
    )
