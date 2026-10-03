"""Starting and cancelling an n8n-orchestrated analysis (the user-facing half).

Ownership is proven under RLS first (a person can only start a run for their own case). The run row is then
created on the system path, idempotently per (case, Idempotency-Key): a retried request returns the same run
and does not trigger n8n a second time. If n8n cannot be reached the run is failed with a person-safe reason.
"""

import uuid

from sqlalchemy import text

from app.auth.dependencies import CurrentUser
from app.core.errors import AppError
from app.db import cases as case_repo
from app.db.database import Database
from app.orchestration.contracts import OrchestrationStart
from app.orchestration.n8n_client import N8nClient, OrchestratorUnavailableError
from app.orchestration.stages import DEFINITION_ID
from app.orchestration.store import OrchestrationStore
from app.schemas.errors import ErrorCode
from app.services.cases import case_not_found


class AnalysisStarter:
    def __init__(self, database: Database, store: OrchestrationStore, n8n: N8nClient) -> None:
        self._db, self._store, self._n8n = database, store, n8n

    async def start(
        self, user: CurrentUser, case_id: uuid.UUID, idempotency_key: str
    ) -> tuple[uuid.UUID, bool]:
        async with self._db.user_session(user) as conn:
            if await case_repo.get_case(conn, user.user_id, case_id) is None:
                raise case_not_found()
            ready = (
                await conn.execute(
                    text(
                        "select count(*) from public.documents"
                        " where case_id = :c and owner_user_id = :o and status = 'ready'"
                    ),
                    {"c": case_id, "o": user.user_id},
                )
            ).scalar_one()
            active = (
                await conn.execute(
                    text(
                        "select id from public.workflow_runs where case_id = :c and owner_user_id = :o"
                        " and status in ('queued', 'running') limit 1"
                    ),
                    {"c": case_id, "o": user.user_id},
                )
            ).first()
        if ready < 1:
            raise AppError(ErrorCode.CONFLICT, "Add at least one document before starting.", status_code=409)
        run_id, created = await self._store.create_run(user.user_id, case_id, idempotency_key, DEFINITION_ID)
        if not created:
            return run_id, False  # a retry of the same request: same run, no second trigger
        if active is not None:
            await self._store.finish_run(
                run_id,
                "failed",
                {
                    "code": "already_running",
                    "title": "Already running",
                    "body": "An analysis is already running for this case.",
                },
                [],
            )
            raise AppError(
                ErrorCode.CONFLICT, "An analysis is already running for this case.", status_code=409
            )
        try:
            await self._n8n.start(
                OrchestrationStart(
                    schema_version="orchestration_start.v1",
                    run_id=str(run_id),
                    case_id=str(case_id),
                    workflow="case_analysis",
                    resume=False,
                )
            )
        except OrchestratorUnavailableError:
            await self._store.finish_run(
                run_id,
                "failed",
                {
                    "code": "orchestrator_unavailable",
                    "title": "We could not start the analysis",
                    "body": "The analysis service is not available right now. Please try again in a few minutes.",
                },
                [],
            )
            raise AppError(
                ErrorCode.SERVICE_UNAVAILABLE,
                "The analysis service is not available right now.",
                status_code=503,
            ) from None
        return run_id, True

    async def resume(self, user: CurrentUser, run_id: uuid.UUID) -> None:
        """Re-send the start message for a run that is still active (n8n restarted mid-run). The master
        workflow skips completed stages and the backend returns stored results, so nothing is redone or re-billed."""
        async with self._db.user_session(user) as conn:
            row = (
                await conn.execute(
                    text(
                        "select case_id, status from public.workflow_runs where id = :r and owner_user_id = :o"
                    ),
                    {"r": run_id, "o": user.user_id},
                )
            ).first()
        if row is None:
            raise AppError(ErrorCode.RUN_NOT_FOUND, "Run could not be found.", status_code=404)
        if row[1] not in ("queued", "running"):
            raise AppError(ErrorCode.CONFLICT, "This analysis has already ended.", status_code=409)
        try:
            await self._n8n.start(
                OrchestrationStart(
                    schema_version="orchestration_start.v1",
                    run_id=str(run_id),
                    case_id=str(row[0]),
                    workflow="case_analysis",
                    resume=True,
                )
            )
        except OrchestratorUnavailableError:
            raise AppError(
                ErrorCode.SERVICE_UNAVAILABLE,
                "The analysis service is not available right now.",
                status_code=503,
            ) from None

    async def cancel(self, user: CurrentUser, run_id: uuid.UUID) -> None:
        async with self._db.user_session(user) as conn:
            owned = (
                await conn.execute(
                    text("select 1 from public.workflow_runs where id = :r and owner_user_id = :o"),
                    {"r": run_id, "o": user.user_id},
                )
            ).first()
        if owned is None:
            raise AppError(ErrorCode.RUN_NOT_FOUND, "Run could not be found.", status_code=404)
        await self._store.request_cancel(run_id)

    async def report(self, user: CurrentUser, run_id: uuid.UUID, kind: str) -> dict[str, object] | None:
        """One artifact of the caller's own run (RLS: the owner reads their own, nothing else)."""
        async with self._db.user_session(user) as conn:
            row = (
                await conn.execute(
                    text(
                        "select payload from public.analysis_artifacts"
                        " where run_id = :r and owner_user_id = :o and kind = :k and key = '-'"
                    ),
                    {"r": run_id, "o": user.user_id, "k": kind},
                )
            ).first()
        return None if row is None else dict(row[0])
