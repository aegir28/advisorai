"""PostgresOrchestrationStore against the real roles: steps come from the definition, idempotency, the system
path's active-run-only access, and the owner's RLS read of artifacts."""

from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.dependencies import CurrentUser
from app.db.database import Database
from app.orchestration.store import PostgresOrchestrationStore
from tests.integration.conftest import Admin, insert_case

pytestmark = pytest.mark.anyio
MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]


async def test_steps_are_created_from_the_given_stage_list_whatever_its_length(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    store = PostgresOrchestrationStore(database)
    user = await make_user()
    case_id = (await insert_case(database, user))["case"]
    stages = [f"stage_{n:02d}" for n in range(1, 18)]  # 17: not 14
    run_id, created = await store.create_run(
        user.user_id, case_id, "key-integration-1", "case_analysis", stages, 3
    )
    again, created2 = await store.create_run(
        user.user_id, case_id, "key-integration-1", "case_analysis", stages, 3
    )
    assert (created, created2, run_id == again) == (True, False, True)
    rows = await admin(
        "select n, node, status from public.workflow_steps where run_id = :r order by n", {"r": run_id}
    )
    assert [r["node"] for r in rows] == stages and [r["n"] for r in rows] == list(range(1, 18))
    run = (
        await admin(
            "select definition, definition_version, orchestrator from public.workflow_runs where id = :r",
            {"r": run_id},
        )
    )[0]
    assert (run["definition"], run["definition_version"], run["orchestrator"]) == (
        "case_analysis",
        "3",
        "n8n",
    )
    # progress follows the actual number of steps, not a constant
    await store.set_step(run_id, "stage_01", "done")
    progress = (await admin("select progress from public.workflow_runs where id = :r", {"r": run_id}))[0][
        "progress"
    ]
    assert abs(float(progress) - 1 / 17) < 1e-3


async def test_artifacts_are_append_only_idempotent_and_closed_when_the_run_ends(
    database: Database, make_user: MakeUser
) -> None:
    store = PostgresOrchestrationStore(database)
    user = await make_user()
    case_id = (await insert_case(database, user))["case"]
    run_id, _ = await store.create_run(
        user.user_id, case_id, "key-integration-2", "second_opinion", ["only_stage"]
    )
    first, new = await store.put_artifact(run_id, "stage", "only_stage", "stage_result.v1", "ok", {"n": 1})
    second, new2 = await store.put_artifact(run_id, "stage", "only_stage", "stage_result.v1", "ok", {"n": 2})
    assert new and not new2 and second.payload == {"n": 1} and first.key == "only_stage"
    assert (
        await store.load_case_inputs(run_id) is not None
    )  # the system path can read the case while it is active
    await store.finish_run(run_id, "complete", None, [])
    assert await store.load_case_inputs(run_id) is None  # ... and loses that access when the run ends
    with pytest.raises(Exception):  # noqa: B017  (RLS refuses the insert: the run is no longer active)
        await store.put_artifact(run_id, "other", "-", "x.v1", "ok", {})


async def test_the_owner_reads_their_artifacts_and_another_user_does_not(
    database: Database, make_user: MakeUser
) -> None:
    store = PostgresOrchestrationStore(database)
    owner, other = await make_user(), await make_user()
    case_id = (await insert_case(database, owner))["case"]
    run_id, _ = await store.create_run(
        owner.user_id, case_id, "key-integration-3", "case_analysis", ["s_one"]
    )
    await store.put_artifact(run_id, "report", "-", "report.v1", "ok", {"hello": "world"})
    sql = text("select count(*) from public.analysis_artifacts where run_id = :r")
    async with database.user_session(owner) as conn:
        assert (await conn.execute(sql, {"r": run_id})).scalar_one() == 1
    async with database.user_session(other) as conn:
        assert (await conn.execute(sql, {"r": run_id})).scalar_one() == 0
