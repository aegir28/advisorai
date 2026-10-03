"""Starting a run. The caller's ownership is proven under RLS first; the run itself is then enqueued on the
SYSTEM path (users cannot write runs). This is the foundation `POST /cases/{id}/analysis` will use; that
endpoint is not exposed until the AI phase has nodes to run.
"""

import uuid

from sqlalchemy import text

from app.auth.dependencies import CurrentUser
from app.core.errors import AppError
from app.db import cases as case_repo
from app.db.database import Database
from app.schemas.errors import ErrorCode
from app.services.cases import case_not_found
from app.workflow.definitions import DefinitionRegistry
from app.workflow.repository import WorkflowRepository


class WorkflowService:
    def __init__(
        self, database: Database, repository: WorkflowRepository, definitions: DefinitionRegistry
    ) -> None:
        self._database = database
        self._repo = repository
        self._definitions = definitions

    async def enqueue_analysis(
        self, user: CurrentUser, case_id: uuid.UUID, definition_id: str, version: int
    ) -> uuid.UUID:
        definition = self._definitions.get(definition_id, version)
        if definition is None:
            raise AppError(
                ErrorCode.SERVICE_UNAVAILABLE, "Analysis is not available right now.", status_code=503
            )

        async with self._database.user_session(user) as connection:
            if await case_repo.get_case(connection, user.user_id, case_id) is None:
                raise case_not_found()
            ready = (
                await connection.execute(
                    text(
                        "select count(*) from public.documents"
                        " where case_id = :c and owner_user_id = :o and status = 'ready'"
                    ),
                    {"c": case_id, "o": user.user_id},
                )
            ).scalar_one()
            if ready < 1:
                raise AppError(
                    ErrorCode.CONFLICT, "Add at least one document before starting.", status_code=409
                )
            active = (
                await connection.execute(
                    text(
                        "select 1 from public.workflow_runs where case_id = :c and owner_user_id = :o"
                        " and status in ('queued', 'running') limit 1"
                    ),
                    {"c": case_id, "o": user.user_id},
                )
            ).first()
            if active is not None:
                raise AppError(
                    ErrorCode.CONFLICT, "An analysis is already running for this case.", status_code=409
                )

        run_id = await self._repo.enqueue(
            user.user_id,
            case_id,
            definition.id,
            definition.version,
            [n.id for n in definition.ordered_nodes()],
        )
        async with self._database.user_session(user) as connection:
            await connection.execute(
                text(
                    "update public.cases set status = 'processing', updated_at = now()"
                    " where id = :c and owner_user_id = :o"
                ),
                {"c": case_id, "o": user.user_id},
            )
        return run_id
