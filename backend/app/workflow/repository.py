"""Job-queue and step persistence on the SYSTEM path (login `app_system`, ADR 0005).

Every call opens its own short system transaction. There is no user context here: the run's owner is a data
column, and the composite foreign keys guarantee it is the real owner of the run's case.

What is stored is status and timing only: ids, node names, counts, short machine error codes and fixed
person-safe text. Never document text, extracted values, prompts or model output.

Lease protocol (a crashed worker must not strand a run):
  * `claim_next` takes a queued run, or a running run whose lease has expired, with `FOR UPDATE SKIP LOCKED`,
    so two workers never take the same run.
  * the worker renews the lease while it works (`extend_lease`); losing it means another worker owns the run.
  * every write that finishes a run requires `locked_by = worker`, so a worker that lost its lease cannot
    overwrite the new owner's result.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.db.database import Database, SystemOperation

STEP_COUNT = 14
MAX_RUN_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    id: uuid.UUID
    case_id: uuid.UUID
    owner_user_id: uuid.UUID
    definition: str
    definition_version: int
    attempts: int


@dataclass(frozen=True, slots=True)
class StepRow:
    id: uuid.UUID
    n: int
    node: str
    status: str
    attempts: int


@dataclass(frozen=True, slots=True)
class RunView:
    """What the status endpoint needs: no owner, no lock details."""

    id: uuid.UUID
    case_id: uuid.UUID
    status: str
    progress: float
    failure: dict[str, Any] | None
    warnings: list[str]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    steps: list[tuple[int, str, str | None]]  # (n, status, note)


class WorkflowRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    # ── enqueue ─────────────────────────────────────────────────────────────────────────────────
    async def enqueue(
        self,
        owner: uuid.UUID,
        case_id: uuid.UUID,
        definition: str,
        version: int,
        node_ids: list[str],
    ) -> uuid.UUID:
        """A queued run plus ALL its steps, in one transaction (`run.v1` always has exactly 14)."""
        if len(node_ids) != STEP_COUNT:
            raise ValueError(f"a run has exactly {STEP_COUNT} steps")
        run_id = uuid.uuid4()
        async with self._db.system_session(SystemOperation.WORKFLOW_ENQUEUE) as c:
            await c.execute(
                text(
                    "insert into public.workflow_runs (id, owner_user_id, case_id, definition,"
                    " definition_version) values (:id, :owner, :case, :definition, :version)"
                ),
                {
                    "id": run_id,
                    "owner": owner,
                    "case": case_id,
                    "definition": definition,
                    "version": str(version),
                },
            )
            for n, node in enumerate(node_ids, start=1):
                await c.execute(
                    text(
                        "insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)"
                        " values (:owner, :case, :run, :n, :node)"
                    ),
                    {"owner": owner, "case": case_id, "run": run_id, "n": n, "node": node},
                )
        return run_id

    # ── lease ───────────────────────────────────────────────────────────────────────────────────
    async def claim_next(self, worker: str, lease_seconds: int) -> ClaimedRun | None:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            row = (
                (
                    await c.execute(
                        text(
                            "update public.workflow_runs r set status = 'running', locked_by = :worker,"
                            " locked_until = now() + make_interval(secs => :lease),"
                            " attempts = r.attempts + 1, started_at = coalesce(r.started_at, now())"
                            " where r.id = (select id from public.workflow_runs"
                            "   where (status = 'queued' or (status = 'running' and locked_until < now()))"
                            "     and attempts < :max"
                            "   order by created_at for update skip locked limit 1)"
                            " returning r.id, r.case_id, r.owner_user_id, r.definition,"
                            " r.definition_version, r.attempts"
                        ),
                        {"worker": worker, "lease": lease_seconds, "max": MAX_RUN_ATTEMPTS},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return ClaimedRun(
            id=row["id"],
            case_id=row["case_id"],
            owner_user_id=row["owner_user_id"],
            definition=row["definition"],
            definition_version=int(row["definition_version"]),
            attempts=row["attempts"],
        )

    async def extend_lease(self, run_id: uuid.UUID, worker: str, lease_seconds: int) -> bool:
        """False when the lease is no longer ours."""
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            result = await c.execute(
                text(
                    "update public.workflow_runs set locked_until = now() + make_interval(secs => :lease)"
                    " where id = :id and locked_by = :worker and status = 'running' returning id"
                ),
                {"id": run_id, "worker": worker, "lease": lease_seconds},
            )
            return result.first() is not None

    async def fail_exhausted(self) -> int:
        """Runs whose lease expired too many times are failed (never left running, never silent)."""
        failure = json.dumps(
            {
                "title": "We couldn't finish reading your records",
                "body": "The work was interrupted too many times, so we stopped. Please try again.",
                "code": "max_attempts_exceeded",
            }
        )
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            result = await c.execute(
                text(
                    "update public.workflow_runs set status = 'failed', failure = cast(:failure as jsonb),"
                    " finished_at = now(), locked_by = null, locked_until = null"
                    " where status = 'running' and locked_until < now() and attempts >= :max returning id"
                ),
                {"failure": failure, "max": MAX_RUN_ATTEMPTS},
            )
            return len(result.all())

    async def release(self, run_id: uuid.UUID, worker: str) -> None:
        """Give the run back (clean shutdown): another worker can take it immediately."""
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            await c.execute(
                text(
                    "update public.workflow_runs set locked_until = now() - interval '1 second'"
                    " where id = :id and locked_by = :worker and status = 'running'"
                ),
                {"id": run_id, "worker": worker},
            )

    # ── steps ───────────────────────────────────────────────────────────────────────────────────
    async def load_steps(self, run_id: uuid.UUID) -> list[StepRow]:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            rows = (
                await c.execute(
                    text(
                        "select id, n, node, status, attempts from public.workflow_steps"
                        " where run_id = :r order by n"
                    ),
                    {"r": run_id},
                )
            ).mappings()
            return [StepRow(r["id"], r["n"], r["node"], r["status"], r["attempts"]) for r in rows]

    async def has_reusable_result(self, case_id: uuid.UUID, node: str, input_hash: str) -> bool:
        """A step for this case, node and input hash already succeeded: its work need not be redone."""
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            result = await c.execute(
                text(
                    "select 1 from public.workflow_steps where case_id = :case and node = :node"
                    " and input_hash = :hash and status in ('done', 'warning') limit 1"
                ),
                {"case": case_id, "node": node, "hash": input_hash},
            )
            return result.first() is not None

    async def warning_notes(self, run_id: uuid.UUID) -> list[str]:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            rows = await c.execute(
                text(
                    "select note from public.workflow_steps where run_id = :r"
                    " and status in ('warning', 'failed') and note is not null order by n"
                ),
                {"r": run_id},
            )
            return [r[0] for r in rows]

    async def start_step(self, step_id: uuid.UUID, input_hash: str) -> None:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            await c.execute(
                text(
                    "update public.workflow_steps set status = 'running', attempts = attempts + 1,"
                    " input_hash = :hash, started_at = coalesce(started_at, now()), finished_at = null,"
                    " error_code = null where id = :id"
                ),
                {"id": step_id, "hash": input_hash},
            )

    async def finish_step(
        self, step_id: uuid.UUID, status: str, *, note: str | None = None, error_code: str | None = None
    ) -> None:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            await c.execute(
                text(
                    "update public.workflow_steps set status = :status, note = :note,"
                    " error_code = :code, finished_at = now() where id = :id"
                ),
                {"id": step_id, "status": status, "note": note, "code": error_code},
            )

    # ── run ─────────────────────────────────────────────────────────────────────────────────────
    async def set_progress(self, run_id: uuid.UUID, worker: str, progress: float) -> None:
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            await c.execute(
                text("update public.workflow_runs set progress = :p where id = :id and locked_by = :worker"),
                {"id": run_id, "worker": worker, "p": round(min(max(progress, 0.0), 1.0), 3)},
            )

    async def finish_run(
        self,
        run_id: uuid.UUID,
        worker: str,
        status: str,
        *,
        failure: dict[str, str] | None = None,
        warnings: list[str] | None = None,
    ) -> bool:
        """Complete / partial / failed. Refused (False) when the lease is no longer ours."""
        async with self._db.system_session(SystemOperation.WORKFLOW_RUN) as c:
            result = await c.execute(
                text(
                    "update public.workflow_runs set status = :status, failure = cast(:failure as jsonb),"
                    " warnings = :warnings, progress = case when :status = 'failed' then progress else 1 end,"
                    " finished_at = now(), locked_by = null, locked_until = null"
                    " where id = :id and locked_by = :worker and status = 'running' returning id"
                ),
                {
                    "id": run_id,
                    "worker": worker,
                    "status": status,
                    "failure": json.dumps(failure) if failure else None,
                    "warnings": warnings or [],
                },
            )
            return result.first() is not None
