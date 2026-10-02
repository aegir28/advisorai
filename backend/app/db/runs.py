"""Run status reads on the USER path (RLS). Status and steps only, never content."""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.workflow.repository import RunView


async def get_run(connection: AsyncConnection, owner: uuid.UUID, run_id: uuid.UUID) -> RunView | None:
    run = (
        (
            await connection.execute(
                text(
                    "select id, case_id, status, progress, failure, warnings, started_at, finished_at,"
                    " created_at from public.workflow_runs where id = :id and owner_user_id = :owner"
                ),
                {"id": run_id, "owner": owner},
            )
        )
        .mappings()
        .first()
    )
    if run is None:
        return None
    steps = (
        await connection.execute(
            text(
                "select n, status, note from public.workflow_steps"
                " where run_id = :id and owner_user_id = :owner order by n"
            ),
            {"id": run_id, "owner": owner},
        )
    ).all()
    failure: Any = run["failure"]
    return RunView(
        id=run["id"],
        case_id=run["case_id"],
        status=run["status"],
        progress=float(run["progress"]),
        failure=failure if isinstance(failure, dict) else None,
        warnings=list(run["warnings"] or []),
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        created_at=run["created_at"],
        steps=[(r[0], r[1], r[2]) for r in steps],
    )
