"""Issuing a download URL: ownership under RLS, then audit, then sign. The order matters.

This is the foundation a future "view document" endpoint will call. There is no endpoint in this
phase and nothing here uploads or validates files.
"""

import uuid

from sqlalchemy import text

from app.audit.writer import AuditAction, AuditWriter
from app.auth.dependencies import CurrentUser
from app.core.errors import AppError
from app.db.database import Database
from app.schemas.errors import ErrorCode

from .gateway import SignedUrl, StorageGateway, StoragePath

_FIND = text("select id, owner_user_id, case_id, status from public.documents where id = :document_id")


class DocumentUrlService:
    def __init__(self, database: Database, audit: AuditWriter, storage: StorageGateway) -> None:
        self._database = database
        self._audit = audit
        self._storage = storage

    async def issue_download_url(
        self, user: CurrentUser, document_id: uuid.UUID, *, client_ip: str | None = None
    ) -> SignedUrl:
        async with self._database.user_session(user) as connection:
            row = (await connection.execute(_FIND, {"document_id": document_id})).mappings().first()

        # RLS hides other people's documents, so "not yours" and "does not exist" look identical.
        # An upload that never completed is internal state and is not exposed either.
        if row is None or row["status"] == "pending_upload":
            raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document could not be found.", status_code=404)

        path = StoragePath(row["owner_user_id"], row["case_id"], row["id"])
        url = await self._storage.create_download_url(path)

        # Audit that a URL was issued (never the URL itself).
        await self._audit.record(
            AuditAction.DOCUMENT_SIGNED_URL_ISSUED,
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
            client_ip=client_ip,
            metadata={"ttl_seconds": url.expires_in},
        )
        return url
