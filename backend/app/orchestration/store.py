"""Run state, artifacts and case inputs for the orchestrated pipeline.

`OrchestrationStore` is the only door the orchestration layer has to the database. The Postgres implementation
works on the SYSTEM path (login `app_system`): it can read the case being analysed only while its run is active
(column-level, migration 20261007000002), append artifacts (insert-only, one row per run/kind/key) and update the
run/step state. The in-memory implementation has the same semantics for tests.

Idempotency lives here: `put_artifact` for an existing (run, kind, key) returns the stored one and reports
`created=False`, so a retried stage or a resumed run never recomputes or re-bills.
"""

import copy
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text

from app.db.database import Database, SystemOperation

STEP_OF_STAGE_STATUS = {
    "ok": "done",
    "skipped": "skipped",
    "unavailable": "warning",
    "failed": "failed",
    "cancelled": "skipped",
}
_TERMINAL_STEP = {"done", "warning", "failed", "skipped"}


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: uuid.UUID
    case_id: uuid.UUID
    owner_user_id: uuid.UUID
    status: str
    orchestrator: str
    definition: str
    cancel_requested: bool


@dataclass(frozen=True, slots=True)
class DocInfo:
    id: str
    type: str
    status: str
    storage_path: str
    mime_type: str | None
    size_bytes: int | None
    pages: int | None


@dataclass(frozen=True, slots=True)
class CaseInputs:
    case_id: uuid.UUID
    owner_user_id: uuid.UUID
    concern: str
    proposed_treatment: str | None
    intent: str | None
    age_years: int
    sex: str
    documents: list[DocInfo]


@dataclass(frozen=True, slots=True)
class Artifact:
    kind: str
    key: str
    schema_version: str
    status: str
    reason_code: str | None
    payload: dict[str, Any]


class OrchestrationStore(Protocol):
    async def create_run(
        self,
        owner: uuid.UUID,
        case_id: uuid.UUID,
        idempotency_key: str,
        workflow: str,
        stage_ids: Sequence[str],
        version: int = 1,
    ) -> tuple[uuid.UUID, bool]:
        """(run id, created). One step row per stage id, in order (`n` = position). The same (case, key)
        returns the existing run with created=False."""
        ...

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None: ...
    async def mark_running(self, run_id: uuid.UUID, execution_id: str | None) -> None: ...
    async def set_step(
        self,
        run_id: uuid.UUID,
        stage_id: str,
        status: str,
        *,
        note: str | None = None,
        error_code: str | None = None,
    ) -> None: ...
    async def step_statuses(self, run_id: uuid.UUID) -> dict[str, tuple[str, str | None, str | None]]:
        """stage id -> (status, note, error_code)."""
        ...

    async def put_artifact(
        self,
        run_id: uuid.UUID,
        kind: str,
        key: str,
        schema_version: str,
        status: str,
        payload: dict[str, Any],
        reason_code: str | None = None,
    ) -> tuple[Artifact, bool]: ...
    async def get_artifact(self, run_id: uuid.UUID, kind: str, key: str = "-") -> Artifact | None: ...
    async def list_artifacts(self, run_id: uuid.UUID, kind: str) -> list[Artifact]: ...
    async def load_case_inputs(self, run_id: uuid.UUID) -> CaseInputs | None: ...
    async def finish_run(
        self, run_id: uuid.UUID, status: str, failure: dict[str, str] | None, warnings: list[str]
    ) -> None: ...
    async def request_cancel(self, run_id: uuid.UUID) -> None: ...
    async def run_by_execution(self, execution_id: str) -> RunRecord | None:
        """The active run n8n execution `execution_id` is driving (error recovery looks it up by this)."""
        ...


# ═══ in-memory (tests, demos) ════════════════════════════════════════════════════════════════════════
@dataclass(slots=True)
class _MemRun:
    record: RunRecord
    key: str
    steps: dict[str, tuple[str, str | None, str | None]] = field(default_factory=dict)
    failure: dict[str, str] | None = None
    warnings: list[str] = field(default_factory=list)
    execution_id: str | None = None


class InMemoryOrchestrationStore:
    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, _MemRun] = {}
        self.artifacts: dict[tuple[uuid.UUID, str, str], Artifact] = {}
        self.inputs: dict[uuid.UUID, CaseInputs] = {}  # case id -> inputs (seeded by tests)

    async def create_run(
        self,
        owner: uuid.UUID,
        case_id: uuid.UUID,
        idempotency_key: str,
        workflow: str,
        stage_ids: Sequence[str],
        version: int = 1,
    ) -> tuple[uuid.UUID, bool]:
        for run_id, run in self.runs.items():
            if run.record.case_id == case_id and run.key == idempotency_key:
                return run_id, False
        run_id = uuid.uuid4()
        record = RunRecord(run_id, case_id, owner, "queued", "n8n", workflow, False)
        self.runs[run_id] = _MemRun(record, idempotency_key, {s: ("pending", None, None) for s in stage_ids})
        return run_id, True

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None:
        run = self.runs.get(run_id)
        return run.record if run else None

    def _set(self, run_id: uuid.UUID, **changes: Any) -> None:
        run = self.runs[run_id]
        r = run.record
        run.record = RunRecord(
            r.id,
            r.case_id,
            r.owner_user_id,
            changes.get("status", r.status),
            r.orchestrator,
            r.definition,
            changes.get("cancel_requested", r.cancel_requested),
        )

    async def mark_running(self, run_id: uuid.UUID, execution_id: str | None) -> None:
        run = self.runs[run_id]
        if run.record.status == "queued":
            self._set(run_id, status="running")
        run.execution_id = execution_id or run.execution_id

    async def set_step(
        self,
        run_id: uuid.UUID,
        stage_id: str,
        status: str,
        *,
        note: str | None = None,
        error_code: str | None = None,
    ) -> None:
        self.runs[run_id].steps[stage_id] = (status, note, error_code)

    async def step_statuses(self, run_id: uuid.UUID) -> dict[str, tuple[str, str | None, str | None]]:
        return dict(self.runs[run_id].steps)

    async def put_artifact(
        self,
        run_id: uuid.UUID,
        kind: str,
        key: str,
        schema_version: str,
        status: str,
        payload: dict[str, Any],
        reason_code: str | None = None,
    ) -> tuple[Artifact, bool]:
        existing = self.artifacts.get((run_id, kind, key))
        if existing is not None:
            return existing, False
        if self.runs[run_id].record.status not in ("queued", "running"):
            raise PermissionError("run_not_active")  # mirrors the RLS policy
        artifact = Artifact(kind, key, schema_version, status, reason_code, copy.deepcopy(payload))
        self.artifacts[(run_id, kind, key)] = artifact
        return artifact, True

    async def get_artifact(self, run_id: uuid.UUID, kind: str, key: str = "-") -> Artifact | None:
        return self.artifacts.get((run_id, kind, key))

    async def list_artifacts(self, run_id: uuid.UUID, kind: str) -> list[Artifact]:
        return [
            a
            for (r, k, _), a in sorted(self.artifacts.items(), key=lambda i: i[0][2])
            if r == run_id and k == kind
        ]

    async def load_case_inputs(self, run_id: uuid.UUID) -> CaseInputs | None:
        run = self.runs.get(run_id)
        if run is None or run.record.status not in ("queued", "running"):
            return None  # mirrors the RLS policies: no read once the run is not active
        return self.inputs.get(run.record.case_id)

    async def finish_run(
        self, run_id: uuid.UUID, status: str, failure: dict[str, str] | None, warnings: list[str]
    ) -> None:
        run = self.runs[run_id]
        self._set(run_id, status=status)
        run.failure, run.warnings = failure, list(warnings)

    async def request_cancel(self, run_id: uuid.UUID) -> None:
        self._set(run_id, cancel_requested=True)

    async def run_by_execution(self, execution_id: str) -> RunRecord | None:
        return next(
            (
                r.record
                for r in self.runs.values()
                if r.execution_id == execution_id and r.record.status in ("queued", "running")
            ),
            None,
        )


# ═══ Postgres, system path ═══════════════════════════════════════════════════════════════════════════
class PostgresOrchestrationStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create_run(
        self,
        owner: uuid.UUID,
        case_id: uuid.UUID,
        idempotency_key: str,
        workflow: str,
        stage_ids: Sequence[str],
        version: int = 1,
    ) -> tuple[uuid.UUID, bool]:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            run_id = (
                await conn.execute(
                    text(
                        "insert into public.workflow_runs (owner_user_id, case_id, definition, definition_version,"
                        " orchestrator, idempotency_key) values (:o, :c, :d, :v, 'n8n', :k)"
                        " on conflict (case_id, idempotency_key) where idempotency_key is not null do nothing"
                        " returning id"
                    ),
                    {
                        "o": owner,
                        "c": case_id,
                        "d": workflow,
                        "v": str(version),
                        "k": idempotency_key,
                    },
                )
            ).scalar()
            if run_id is None:
                existing = (
                    await conn.execute(
                        text(
                            "select id from public.workflow_runs where case_id = :c and idempotency_key = :k"
                        ),
                        {"c": case_id, "k": idempotency_key},
                    )
                ).scalar_one()
                return existing, False
            for n, stage_id in enumerate(stage_ids, start=1):
                await conn.execute(
                    text(
                        "insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)"
                        " values (:o, :c, :r, :n, :node)"
                    ),
                    {"o": owner, "c": case_id, "r": run_id, "n": n, "node": stage_id},
                )
            return run_id, True

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None:
        return await self._run_where("id = :r", {"r": run_id})

    async def run_by_execution(self, execution_id: str) -> RunRecord | None:
        return await self._run_where(
            "external_execution_id = :e and status in ('queued', 'running')", {"e": execution_id}
        )

    async def _run_where(self, where: str, params: dict[str, Any]) -> RunRecord | None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "select id, case_id, owner_user_id, status, orchestrator, definition,"
                            " cancel_requested_at is not null as cancel from public.workflow_runs"
                            f" where {where} limit 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return RunRecord(
            row["id"],
            row["case_id"],
            row["owner_user_id"],
            row["status"],
            row["orchestrator"],
            row["definition"],
            row["cancel"],
        )

    async def mark_running(self, run_id: uuid.UUID, execution_id: str | None) -> None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            await conn.execute(
                text(
                    "update public.workflow_runs set status = case when status = 'queued' then 'running' else status end,"
                    " started_at = coalesce(started_at, now()),"
                    " external_execution_id = coalesce(:e, external_execution_id) where id = :r"
                ),
                {"r": run_id, "e": execution_id},
            )

    async def set_step(
        self,
        run_id: uuid.UUID,
        stage_id: str,
        status: str,
        *,
        note: str | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            await conn.execute(
                text(
                    "update public.workflow_steps set status = :s, note = :n, error_code = :e,"
                    " started_at = coalesce(started_at, now()),"
                    " finished_at = case when :s in ('done', 'warning', 'failed', 'skipped') then now() else null end,"
                    " attempts = attempts + case when :s = 'running' then 1 else 0 end"
                    " where run_id = :r and node = :node"
                ),
                {"r": run_id, "node": stage_id, "s": status, "n": note, "e": error_code},
            )
            await conn.execute(
                text(
                    "update public.workflow_runs set progress = least(1, (select count(*) filter"
                    " (where status in ('done', 'warning', 'skipped'))::numeric / greatest(count(*), 1)"
                    " from public.workflow_steps where run_id = :r)) where id = :r"
                ),
                {"r": run_id},
            )

    async def step_statuses(self, run_id: uuid.UUID) -> dict[str, tuple[str, str | None, str | None]]:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            rows = (
                await conn.execute(
                    text(
                        "select node, status, note, error_code from public.workflow_steps where run_id = :r"
                    ),
                    {"r": run_id},
                )
            ).all()
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

    async def put_artifact(
        self,
        run_id: uuid.UUID,
        kind: str,
        key: str,
        schema_version: str,
        status: str,
        payload: dict[str, Any],
        reason_code: str | None = None,
    ) -> tuple[Artifact, bool]:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            inserted = (
                await conn.execute(
                    text(
                        "insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key,"
                        " schema_version, status, reason_code, payload)"
                        " select r.owner_user_id, r.case_id, r.id, :k, :key, :sv, :st, :rc, cast(:p as jsonb)"
                        " from public.workflow_runs r where r.id = :r"
                        " on conflict (run_id, kind, key) do nothing returning 1"
                    ),
                    {
                        "r": run_id,
                        "k": kind,
                        "key": key,
                        "sv": schema_version,
                        "st": status,
                        "rc": reason_code,
                        "p": json.dumps(payload),
                    },
                )
            ).first()
            row = (
                (
                    await conn.execute(
                        text(
                            "select kind, key, schema_version, status, reason_code, payload"
                            " from public.analysis_artifacts where run_id = :r and kind = :k and key = :key"
                        ),
                        {"r": run_id, "k": kind, "key": key},
                    )
                )
                .mappings()
                .one()
            )
        return _artifact(row), inserted is not None

    async def get_artifact(self, run_id: uuid.UUID, kind: str, key: str = "-") -> Artifact | None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "select kind, key, schema_version, status, reason_code, payload"
                            " from public.analysis_artifacts where run_id = :r and kind = :k and key = :key"
                        ),
                        {"r": run_id, "k": kind, "key": key},
                    )
                )
                .mappings()
                .first()
            )
        return _artifact(row) if row else None

    async def list_artifacts(self, run_id: uuid.UUID, kind: str) -> list[Artifact]:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "select kind, key, schema_version, status, reason_code, payload"
                            " from public.analysis_artifacts where run_id = :r and kind = :k order by key"
                        ),
                        {"r": run_id, "k": kind},
                    )
                )
                .mappings()
                .all()
            )
        return [_artifact(r) for r in rows]

    async def load_case_inputs(self, run_id: uuid.UUID) -> CaseInputs | None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "select c.id as case_id, c.owner_user_id, c.concern, c.proposed_treatment, c.intent,"
                            " p.age_years, p.sex from public.workflow_runs r"
                            " join public.cases c on c.id = r.case_id and c.owner_user_id = r.owner_user_id"
                            " join public.patients p on p.id = c.patient_id and p.owner_user_id = c.owner_user_id"
                            " where r.id = :r"
                        ),
                        {"r": run_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            docs = (
                await conn.execute(
                    text(
                        "select id, type, status, storage_path, mime_type, size_bytes, pages"
                        " from public.documents where case_id = :c and status = 'ready' order by id"
                    ),
                    {"c": row["case_id"]},
                )
            ).all()
        return CaseInputs(
            row["case_id"],
            row["owner_user_id"],
            row["concern"],
            row["proposed_treatment"],
            row["intent"],
            int(row["age_years"]),
            row["sex"],
            [DocInfo(str(d[0]), d[1], d[2], d[3], d[4], d[5], d[6]) for d in docs],
        )

    async def finish_run(
        self, run_id: uuid.UUID, status: str, failure: dict[str, str] | None, warnings: list[str]
    ) -> None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            await conn.execute(
                text(
                    "update public.workflow_runs set status = :s, failure = cast(:f as jsonb), warnings = :w,"
                    " finished_at = now(), progress = case when :s = 'failed' then progress else 1 end where id = :r"
                ),
                {"r": run_id, "s": status, "f": json.dumps(failure) if failure else None, "w": warnings},
            )

    async def request_cancel(self, run_id: uuid.UUID) -> None:
        async with self._db.system_session(SystemOperation.ORCHESTRATION) as conn:
            await conn.execute(
                text(
                    "update public.workflow_runs set cancel_requested_at = coalesce(cancel_requested_at, now()) where id = :r"
                ),
                {"r": run_id},
            )


def _artifact(row: Any) -> Artifact:
    payload = row["payload"]
    return Artifact(
        row["kind"],
        row["key"],
        row["schema_version"],
        row["status"],
        row["reason_code"],
        payload if isinstance(payload, dict) else json.loads(payload),
    )
