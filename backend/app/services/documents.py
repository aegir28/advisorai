"""Document lifecycle: a signed upload URL, completion with server-side validation, listing, removal.

The upload is two steps so the file never passes through this API on the way in:

  1. `create_upload`   a `pending_upload` row (internal) + a signed upload URL; the client PUTs the file
                       straight to private storage.
  2. `complete_upload` the backend reads the object back, checks size, REAL type, hash and page count
                       (`docintel.validate`, no AI or OCR), and sets the status: `ready`, `duplicate` or
                       `needs_attention`. Files that fail are deleted from storage; the row stays so the
                       person sees why.

Ownership: every query is filtered by the verified caller and RLS-scoped; the storage path is built from
IDs, never from client input.
"""

import logging
import uuid

from app.audit.writer import AuditAction, AuditWriter
from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.core.errors import AppError
from app.db import cases as case_repo
from app.db import documents as repo
from app.db.database import Database
from app.docintel.validate import MAX_BYTES, validate_upload
from app.schemas.case_api import DocumentItem, UploadUrlRequest, UploadUrlResponse
from app.schemas.errors import ErrorCode
from app.services.cases import case_not_found
from app.storage.gateway import (
    ObjectNotFoundError,
    ObjectTooLargeError,
    StorageError,
    StorageGateway,
    StoragePath,
)

logger = logging.getLogger("advisorai.documents")


def document_not_found() -> AppError:
    return AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document could not be found.", status_code=404)


def _storage_unavailable() -> AppError:
    return AppError(
        ErrorCode.STORAGE_UNAVAILABLE,
        "We could not reach file storage right now. Please try again.",
        status_code=503,
    )


def to_item(row: repo.DocumentRow) -> DocumentItem:
    when = row.uploaded_at or row.created_at
    body: dict[str, object] = {
        "id": str(row.id),
        "name": row.title,
        "type": row.type,
        "size_kb": round((row.size_bytes or 0) / 1024, 1),
        "status": row.status,
        "uploaded_at": when.isoformat(),
    }
    optional = {"pages": row.pages, "ocr_confidence": row.ocr_confidence, "note": row.note}
    body.update({k: v for k, v in optional.items() if v is not None})
    return DocumentItem.model_validate(body)


class DocumentService:
    def __init__(
        self, database: Database, audit: AuditWriter, storage: StorageGateway, settings: Settings
    ) -> None:
        self._database = database
        self._audit = audit
        self._storage = storage
        self._max_documents = settings.max_documents_per_case

    async def list(self, user: CurrentUser, case_id: uuid.UUID) -> list[DocumentItem]:
        async with self._database.user_session(user) as connection:
            if not await repo.case_is_open(connection, user.user_id, case_id):
                raise case_not_found()
            return [to_item(r) for r in await repo.list_documents(connection, user.user_id, case_id)]

    async def create_upload(
        self, user: CurrentUser, case_id: uuid.UUID, data: UploadUrlRequest
    ) -> UploadUrlResponse:
        document_id = uuid.uuid4()
        path = StoragePath(user.user_id, case_id, document_id)
        async with self._database.user_session(user) as connection:
            if not await repo.case_is_open(connection, user.user_id, case_id):
                raise case_not_found()
            if await repo.count_documents(connection, user.user_id, case_id) >= self._max_documents:
                raise AppError(
                    ErrorCode.DOCUMENT_LIMIT_REACHED,
                    "This case has reached the maximum number of documents.",
                    status_code=409,
                )
            await repo.insert_pending(
                connection,
                user.user_id,
                case_id,
                document_id,
                type_=data.type,
                title=data.name,
                mime_type=data.mime_type,
                size_bytes=data.size_bytes,
                storage_path=str(path),
            )
        try:
            url = await self._storage.create_upload_url(path)
        except StorageError:
            await self._drop_row(user, document_id)
            raise _storage_unavailable() from None
        return UploadUrlResponse(
            document_id=str(document_id), upload_url=url.reveal(), expires_in=url.expires_in
        )

    async def complete_upload(
        self, user: CurrentUser, case_id: uuid.UUID, document_id: uuid.UUID, *, client_ip: str | None
    ) -> DocumentItem:
        async with self._database.user_session(user) as connection:
            row = await repo.get_document(connection, user.user_id, case_id, document_id)
            if row is None or not await repo.case_is_open(connection, user.user_id, case_id):
                raise document_not_found()
        if row.status != "pending_upload":
            return to_item(row)  # completing twice is harmless

        path = StoragePath(user.user_id, case_id, document_id)
        declared = row.mime_type or ""
        try:
            data = await self._storage.read_object(path, max_bytes=MAX_BYTES)
            result = await validate_upload(data, declared)
        except ObjectNotFoundError:
            raise AppError(
                ErrorCode.UPLOAD_NOT_RECEIVED,
                "We have not received this file yet. Please upload it again.",
                status_code=409,
            ) from None
        except ObjectTooLargeError:
            result = None
        except StorageError:
            raise _storage_unavailable() from None

        if result is None or result.verdict == "rejected":
            status, size, sha, mime, pages = "needs_attention", None, None, None, None
            note = "This file is larger than 20 MB." if result is None else result.note
            if result is not None:
                size = result.size_bytes if 1 <= result.size_bytes <= MAX_BYTES else None
                sha = result.sha256
            await self._discard_object(path)
        else:
            status, size, sha, mime, pages, note = (
                "ready",
                result.size_bytes,
                result.sha256,
                result.mime_type,
                result.pages,
                None,
            )

        async with self._database.user_session(user) as connection:
            if (
                status == "ready"
                and sha is not None
                and await repo.has_ready_duplicate(connection, user.user_id, case_id, document_id, sha)
            ):
                status, note = "duplicate", "This looks the same as a document you already added."
            stored = await repo.finish_upload(
                connection,
                user.user_id,
                document_id,
                status=status,
                size_bytes=size,
                sha256=sha,
                mime_type=mime,
                pages=pages,
                note=note,
            )
            await case_repo.touch_case(connection, user.user_id, case_id)
            final = await repo.get_document(connection, user.user_id, case_id, document_id)
        assert final is not None
        if stored == "duplicate":
            await self._discard_object(path)  # keep one copy of identical content

        await self._audit.record_completed(
            AuditAction.DOCUMENT_UPLOAD,
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
            client_ip=client_ip,
            metadata={"status": stored},
        )
        return to_item(final)

    async def remove(
        self, user: CurrentUser, case_id: uuid.UUID, document_id: uuid.UUID, *, client_ip: str | None
    ) -> None:
        async with self._database.user_session(user) as connection:
            if await repo.get_document(connection, user.user_id, case_id, document_id) is None:
                raise document_not_found()
        try:
            await self._storage.delete_objects([StoragePath(user.user_id, case_id, document_id)])
        except StorageError:
            raise _storage_unavailable() from None
        async with self._database.user_session(user) as connection:
            await repo.delete_document(connection, user.user_id, document_id)
            await case_repo.touch_case(connection, user.user_id, case_id)
        await self._audit.record_completed(
            AuditAction.DOCUMENT_DELETE,
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
            client_ip=client_ip,
        )

    async def _drop_row(self, user: CurrentUser, document_id: uuid.UUID) -> None:
        try:
            async with self._database.user_session(user) as connection:
                await repo.delete_document(connection, user.user_id, document_id)
        except Exception:
            logger.warning("could not remove a pending document row", exc_info=True)

    async def _discard_object(self, path: StoragePath) -> None:
        """Rejected or duplicate content is not kept. Best effort: a leftover is also removed when the
        document or its case is deleted."""
        try:
            await self._storage.delete_objects([path])
        except StorageError:
            logger.warning("could not discard a rejected upload object")
