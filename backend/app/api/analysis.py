"""GET /analysis/{run_id}: the status and steps of one run, never its content (`run.v1`)."""

import uuid

from fastapi import APIRouter

from app.api.dependencies import DatabaseDep
from app.auth.dependencies import CurrentUserDep
from app.core.errors import AppError
from app.db.runs import get_run
from app.schemas.errors import ErrorCode
from app.schemas.run import RUN_SCHEMA_VERSION, AnalysisRun
from app.workflow.repository import RunView

router = APIRouter(prefix="/analysis", tags=["analysis"])


def to_wire(run: RunView) -> AnalysisRun:
    """DB row -> `run.v1`. The internal `queued` state is presented as `running` with progress 0: from the
    person's side the analysis has started and is waiting its turn; the UI polls the same way."""
    started = run.started_at or run.created_at
    body: dict[str, object] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "id": str(run.id),
        "case_id": str(run.case_id),
        "status": "running" if run.status == "queued" else run.status,
        "progress": run.progress,
        "steps": [{"n": n, "status": s} | ({"note": note} if note else {}) for n, s, note in run.steps],
        "started_at": started.isoformat(),
        "warnings": run.warnings,
    }
    if run.finished_at is not None:
        body["finished_at"] = run.finished_at.isoformat()
    if run.failure is not None:
        # The machine `code` stays server-side; the wire contract carries the person-safe text only.
        body["failure"] = {"title": run.failure["title"], "body": run.failure["body"]}
    return AnalysisRun.model_validate(body)


@router.get(
    "/{run_id}",
    response_model=AnalysisRun,
    response_model_exclude_none=True,
    summary="Status and steps of an analysis run (no content)",
    operation_id="getRun",
    responses={
        401: {"description": "Missing, invalid or expired token."},
        404: {"description": "No such run."},
    },
)
async def get_analysis(run_id: uuid.UUID, user: CurrentUserDep, database: DatabaseDep) -> AnalysisRun:
    async with database.user_session(user) as connection:
        run = await get_run(connection, user.user_id, run_id)
    if run is None:
        raise AppError(ErrorCode.RUN_NOT_FOUND, "Run could not be found.", status_code=404)
    return to_wire(run)
