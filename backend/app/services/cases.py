"""Case lifecycle: create, read, delete. Ownership is enforced twice, in the SQL filters and by RLS.

Deleting a case follows the blueprint's purge order (workflow WF05): mark the case so it disappears and
takes no new uploads, remove its files from storage, then delete the rows, then audit. If the storage
step fails the rows are kept (still marked), the caller is told to retry, and a retry finishes the job.
"""

import logging
import uuid

from app.audit.writer import AuditAction, AuditWriter
from app.auth.dependencies import CurrentUser
from app.core.errors import AppError
from app.db import cases as case_repo
from app.db import documents as document_repo
from app.db.database import Database
from app.schemas.case_api import CaseSummary, NewCaseInput
from app.schemas.errors import ErrorCode
from app.storage.gateway import StorageError, StorageGateway, StoragePath

logger = logging.getLogger("advisorai.cases")


def case_not_found() -> AppError:
    # Another person's case and a case that does not exist look identical.
    return AppError(ErrorCode.CASE_NOT_FOUND, "Case could not be found.", status_code=404)


def to_summary(row: case_repo.CaseRow) -> CaseSummary:
    body: dict[str, object] = {
        "id": str(row.id),
        "code": row.code,
        "age_years": row.age_years,
        "sex": row.sex,
        "concern": row.concern,
        "status": row.status,
        "document_count": row.document_count,
        "updated_at": row.updated_at.isoformat(),
    }
    optional = {
        "proposed_treatment": row.proposed_treatment,
        "run_id": str(row.run_id) if row.run_id else None,
        "title": row.title,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    return CaseSummary.model_validate(body)


class CaseService:
    def __init__(self, database: Database, audit: AuditWriter, storage: StorageGateway | None) -> None:
        self._database = database
        self._audit = audit
        self._storage = storage

    async def list(self, user: CurrentUser) -> list[CaseSummary]:
        async with self._database.user_session(user) as connection:
            return [to_summary(r) for r in await case_repo.list_cases(connection, user.user_id)]

    async def get(self, user: CurrentUser, case_id: uuid.UUID) -> CaseSummary:
        async with self._database.user_session(user) as connection:
            row = await case_repo.get_case(connection, user.user_id, case_id)
        if row is None:
            raise case_not_found()
        return to_summary(row)

    async def create(self, user: CurrentUser, data: NewCaseInput, *, client_ip: str | None) -> CaseSummary:
        async with self._database.user_session(user) as connection:
            case_id = await case_repo.create_case(
                connection,
                user.user_id,
                age_years=data.age_years,
                sex=data.sex,
                concern=data.concern,
                proposed_treatment=data.proposed_treatment,
                intent=data.intent,
            )
            row = await case_repo.get_case(connection, user.user_id, case_id)
        assert row is not None  # we just created it, as this user, inside RLS
        await self._audit.record_completed(
            AuditAction.CASE_CREATE,
            actor=user.user_id,
            target_type="case",
            target_id=str(case_id),
            client_ip=client_ip,
        )
        return to_summary(row)

    async def delete(self, user: CurrentUser, case_id: uuid.UUID, *, client_ip: str | None) -> None:
        async with self._database.user_session(user) as connection:
            if not await case_repo.mark_deletion_requested(connection, user.user_id, case_id):
                raise case_not_found()
            document_ids = await document_repo.all_document_ids(connection, user.user_id, case_id)

        if document_ids:
            if self._storage is None:
                raise AppError(
                    ErrorCode.STORAGE_UNAVAILABLE,
                    "We could not remove the files right now. Please try again.",
                    status_code=503,
                )
            try:
                await self._storage.delete_objects(
                    [StoragePath(user.user_id, case_id, d) for d in document_ids]
                )
            except StorageError:
                logger.error("storage delete failed for a case; rows kept so the delete can be retried")
                raise AppError(
                    ErrorCode.STORAGE_UNAVAILABLE,
                    "We could not remove the files right now. Please try again.",
                    status_code=503,
                ) from None

        async with self._database.user_session(user) as connection:
            await case_repo.delete_case(connection, user.user_id, case_id)

        for action in (AuditAction.CASE_DELETE, AuditAction.DATA_DELETION):
            await self._audit.record_completed(
                action,
                actor=user.user_id,
                target_type="case",
                target_id=str(case_id),
                client_ip=client_ip,
                metadata={"scope": "case", "count": len(document_ids)},
            )
