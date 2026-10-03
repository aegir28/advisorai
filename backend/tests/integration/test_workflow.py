"""The job queue, step persistence and engine against real PostgreSQL, through the real `app_system` login.

Only test nodes exist: there is no AI in this phase. What is proved: the lease protocol (two workers never
take the same run, a crashed worker's run is taken over, a stale worker cannot overwrite the new owner),
idempotent resume and reuse, retry/timeout/critical/non-critical outcomes, that nothing sensitive is stored or
logged, and that users can read only their own runs.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.audit.writer import AuditWriter
from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.core.errors import AppError
from app.db.database import Database
from app.main import create_app
from app.services.workflows import WorkflowService
from app.workflow.definitions import DefinitionRegistry, WorkflowDefinition, load_definition
from app.workflow.engine import Engine, NodeError, NodeRegistry, RetryableError, RunContext, StepResult
from app.workflow.repository import MAX_RUN_ATTEMPTS, WorkflowRepository
from app.workflow.worker import Worker
from tests.integration.conftest import Admin, insert_case
from tests.support import ISSUER, StaticKeyProvider, claims, make_keypair, mint

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]
HMAC = SecretStr("0123456789abcdef0123456789abcdef-integration")
FIXTURE = Path(__file__).parent.parent / "fixtures" / "workflows" / "foundation_smoke.v1.yaml"


class RecordingNode:
    """Counts its runs; `behaviour` can raise or sleep. Returns `result`."""

    def __init__(
        self, result: StepResult | None = None, behaviour: Callable[[int], Any] | None = None
    ) -> None:
        self.calls = 0
        self.order: list[str] = []
        self.result = result or StepResult()
        self.behaviour = behaviour

    async def run(self, ctx: RunContext) -> StepResult:
        self.calls += 1
        if self.behaviour is not None:
            outcome = self.behaviour(self.calls)
            if asyncio.iscoroutine(outcome):
                await outcome
        return self.result


def definition() -> WorkflowDefinition:
    return load_definition(FIXTURE)


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
def repo(database: Database) -> WorkflowRepository:
    return WorkflowRepository(database)


def build_engine(repo: WorkflowRepository, node: Any, database: Database | None = None, **kw: Any) -> Engine:
    registry = NodeRegistry()
    registry.register("test.noop", node)
    audit = AuditWriter(database, HMAC) if database is not None else None
    return Engine(repo, DefinitionRegistry([definition()]), registry, audit=audit, sleep=no_sleep, **kw)


async def enqueue(repo: WorkflowRepository, user: CurrentUser, case_id: uuid.UUID) -> uuid.UUID:
    d = definition()
    return await repo.enqueue(user.user_id, case_id, d.id, d.version, [n.id for n in d.ordered_nodes()])


async def run_state(admin: Admin, run_id: uuid.UUID) -> dict[str, Any]:
    run = (await admin("select * from public.workflow_runs where id = :r", {"r": run_id}))[0]
    steps = await admin(
        "select n, node, status, attempts, error_code, note, input_hash from public.workflow_steps where run_id = :r order by n",
        {"r": run_id},
    )
    return {"run": run, "steps": steps}


async def drive(repo: WorkflowRepository, engine: Engine, worker: str = "w1") -> str:
    claimed = await repo.claim_next(worker, 60)
    assert claimed is not None

    async def renew() -> bool:
        return await repo.extend_lease(claimed.id, worker, 60)

    return await engine.execute(claimed, worker, renew)


async def one_case(database: Database, make_user: MakeUser) -> tuple[CurrentUser, uuid.UUID]:
    user = await make_user()
    return user, (await insert_case(database, user))["case"]


# ── Enqueue ─────────────────────────────────────────────────────────────────────────────────────
async def test_enqueue_creates_a_queued_run_with_exactly_14_pending_steps(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "queued" and state["run"]["owner_user_id"] == user.user_id
    assert [s["n"] for s in state["steps"]] == list(range(1, 15))
    assert {s["status"] for s in state["steps"]} == {"pending"}
    assert [s["node"] for s in state["steps"]][:2] == ["n01", "n02"]


async def test_a_run_cannot_pair_one_owner_with_anothers_case(
    repo: WorkflowRepository, database: Database, make_user: MakeUser
) -> None:
    a, case_a = await one_case(database, make_user)
    b = await make_user()
    with pytest.raises(Exception, match="foreign key"):
        await enqueue(repo, b, case_a)
    assert a.user_id != b.user_id


async def test_a_run_must_have_14_steps(
    repo: WorkflowRepository, database: Database, make_user: MakeUser
) -> None:
    user, case_id = await one_case(database, make_user)
    with pytest.raises(ValueError, match="14"):
        await repo.enqueue(user.user_id, case_id, "x", 1, ["a", "b"])


# ── Engine outcomes ─────────────────────────────────────────────────────────────────────────────
async def test_a_run_completes_and_every_step_is_persisted_and_audited(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    node = RecordingNode()
    assert await drive(repo, build_engine(repo, node, database)) == "complete"
    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "complete" and float(state["run"]["progress"]) == 1
    assert state["run"]["finished_at"] is not None and state["run"]["locked_by"] is None
    assert {s["status"] for s in state["steps"]} == {"done"} and node.calls == 14
    assert all(len(s["input_hash"]) == 64 and s["attempts"] == 1 for s in state["steps"])
    events = await admin(
        "select action, metadata::text m from public.audit_logs where target_id = :r order by at",
        {"r": str(run_id)},
    )
    assert [e["action"] for e in events] == ["workflow.start", "workflow.finish"]
    assert '"status": "complete"' in events[1]["m"]


async def test_layers_run_in_parallel(
    repo: WorkflowRepository, database: Database, make_user: MakeUser
) -> None:
    user, case_id = await one_case(database, make_user)
    await enqueue(repo, user, case_id)
    live, peak = 0, 0

    async def slow(_: int) -> None:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        live -= 1

    await drive(repo, build_engine(repo, RecordingNode(behaviour=slow)))
    assert peak == 4  # the widest layer has four independent nodes


async def test_a_non_critical_failure_makes_the_run_partial_not_failed(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)

    class Flaky(RecordingNode):
        async def run(self, ctx: RunContext) -> StepResult:
            await super().run(ctx)
            if self.calls == 10:  # one of the non-critical nodes (n10..n13)
                raise NodeError("ocr_empty", note="One document could not be read.")
            return StepResult()

    assert await drive(repo, build_engine(repo, Flaky())) == "partial"
    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "partial" and state["run"]["warnings"] == [
        "One document could not be read."
    ]
    failed = [s for s in state["steps"] if s["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["error_code"] == "ocr_empty"
    assert state["steps"][13]["status"] == "done"  # the run carried on to the last step


async def test_a_warning_result_makes_the_run_partial(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    node = RecordingNode(StepResult("warning", "Some values were unclear."))
    assert await drive(repo, build_engine(repo, node)) == "partial"
    assert (await run_state(admin, run_id))["run"]["warnings"][0] == "Some values were unclear."


async def test_a_critical_failure_stops_the_run_and_says_why(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)

    def boom(call: int) -> None:
        if call == 3:  # the third node of the second layer
            raise NodeError(
                "document_unreadable", title="One document is too blurry", body="Please add a clearer copy."
            )

    assert await drive(repo, build_engine(repo, RecordingNode(behaviour=boom))) == "failed"
    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "failed" and state["run"]["finished_at"] is not None
    assert state["run"]["failure"] == {
        "title": "One document is too blurry",
        "body": "Please add a clearer copy.",
        "code": "document_unreadable",
    }
    statuses = [s["status"] for s in state["steps"]]
    assert "failed" in statuses and statuses[-1] == "pending"  # later layers never started
    assert state["run"]["locked_by"] is None


async def test_retry_then_success_and_retry_exhaustion(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    delays: list[float] = []

    async def record(d: float) -> None:
        delays.append(d)

    # n06..n09 allow one retry. Fail the FIRST attempt of exactly one of them.
    first_attempt_failed = False

    def fail_first_retryable(call: int) -> None:
        nonlocal first_attempt_failed
        if call == 6 and not first_attempt_failed:  # the 6th call is the first node of the n06..n09 layer
            first_attempt_failed = True
            raise RetryableError("provider_down")

    run_id = await enqueue(repo, user, case_id)
    engine = build_engine(repo, RecordingNode(behaviour=fail_first_retryable))
    engine._sleep = record
    assert await drive(repo, engine) == "complete"
    state = await run_state(admin, run_id)
    assert [s["attempts"] for s in state["steps"]].count(2) == 1 and len(delays) == 1 and delays[0] == 1.0

    # Exhaustion: node n06 fails every time, retries=1 -> two attempts, then the (critical) run fails.
    user2, case2 = await one_case(database, make_user)
    run2 = await enqueue(repo, user2, case2)

    def always_fail(call: int) -> None:
        if call >= 6:
            raise RetryableError(
                "provider_down", body="Our reading service was unavailable. Please try again."
            )

    assert await drive(repo, build_engine(repo, RecordingNode(behaviour=always_fail))) == "failed"
    failed = [s for s in (await run_state(admin, run2))["steps"] if s["status"] == "failed"]
    assert failed and all(s["attempts"] == 2 and s["error_code"] == "provider_down" for s in failed)


async def test_a_node_timeout_is_retried_then_fails_with_code_timeout(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    d = load_definition(FIXTURE)
    short = WorkflowDefinition.model_validate(
        {**d.model_dump(), "nodes": [{**n.model_dump(), "timeout_s": 1} for n in d.nodes]}
    )
    run_id = await repo.enqueue(
        user.user_id, case_id, short.id, short.version, [n.id for n in short.ordered_nodes()]
    )
    registry = NodeRegistry()
    registry.register(
        "test.noop", RecordingNode(behaviour=lambda call: asyncio.sleep(5) if call == 1 else None)
    )
    engine = Engine(repo, DefinitionRegistry([short]), registry, sleep=no_sleep)
    assert await drive(repo, engine) == "failed"
    state = await run_state(admin, run_id)
    assert state["steps"][0]["error_code"] == "timeout" and state["steps"][0]["status"] == "failed"


async def test_a_node_bug_fails_the_step_and_its_message_is_never_stored_or_logged(
    repo: WorkflowRepository,
    database: Database,
    make_user: MakeUser,
    admin: Admin,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)

    def leak(call: int) -> None:
        if call == 1:
            raise RuntimeError("PATIENT-SECRET-TEXT from the document")

    assert await drive(repo, build_engine(repo, RecordingNode(behaviour=leak))) == "failed"
    state = await run_state(admin, run_id)
    assert state["steps"][0]["error_code"] == "internal_error"
    assert "PATIENT-SECRET" not in str(state) and "PATIENT-SECRET" not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_unregistered_node_types_and_unknown_definitions_fail_cleanly_before_any_step_runs(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    engine = Engine(repo, DefinitionRegistry([definition()]), NodeRegistry(), sleep=no_sleep)
    assert await drive(repo, engine) == "failed"
    state = await run_state(admin, run_id)
    assert state["run"]["failure"]["code"] == "node_type_unavailable" and "title" in state["run"]["failure"]
    assert {s["status"] for s in state["steps"]} == {"pending"}

    run2 = await enqueue(repo, user, case_id)
    assert await drive(repo, Engine(repo, DefinitionRegistry(), NodeRegistry(), sleep=no_sleep)) == "failed"
    assert (await run_state(admin, run2))["run"]["failure"]["code"] == "definition_unavailable"


async def test_a_resumed_run_skips_steps_that_already_finished(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    await admin(
        "update public.workflow_steps set status = 'done' where run_id = :r and n <= 5", {"r": run_id}
    )
    node = RecordingNode()
    assert await drive(repo, build_engine(repo, node)) == "complete"
    assert node.calls == 9  # only n06..n14 ran


async def test_an_identical_step_in_a_later_run_of_the_same_case_is_reused(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    await enqueue(repo, user, case_id)
    first = RecordingNode()
    await drive(repo, build_engine(repo, first))
    second_run = await enqueue(repo, user, case_id)
    second = RecordingNode()
    assert await drive(repo, build_engine(repo, second)) == "complete"
    assert first.calls == 14 and second.calls == 0
    assert {s["status"] for s in (await run_state(admin, second_run))["steps"]} == {"done"}
    # A different case never reuses it.
    other_user, other_case = await one_case(database, make_user)
    await enqueue(repo, other_user, other_case)
    third = RecordingNode()
    await drive(repo, build_engine(repo, third))
    assert third.calls == 14


# ── Lease protocol ──────────────────────────────────────────────────────────────────────────────
async def test_two_workers_never_take_the_same_run(
    repo: WorkflowRepository, database: Database, make_user: MakeUser
) -> None:
    user, case_id = await one_case(database, make_user)
    ids = {await enqueue(repo, user, case_id), await enqueue(repo, user, case_id)}
    claims_ = await asyncio.gather(*[repo.claim_next(f"w{i}", 60) for i in range(5)])
    got = [c.id for c in claims_ if c is not None]
    assert len(got) == 2 and set(got) == ids  # each run claimed exactly once; the other 3 got nothing


async def test_a_crashed_workers_run_is_taken_over_after_its_lease_expires(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    first = await repo.claim_next("dead-worker", 60)
    assert first is not None and first.attempts == 1
    assert await repo.claim_next("w2", 60) is None  # leased: nobody else may take it
    await admin(
        "update public.workflow_runs set locked_until = now() - interval '1 second' where id = :r",
        {"r": run_id},
    )
    second = await repo.claim_next("w2", 60)
    assert second is not None and second.id == run_id and second.attempts == 2
    # The stale worker can neither extend nor finish the run any more.
    assert await repo.extend_lease(run_id, "dead-worker", 60) is False
    assert await repo.finish_run(run_id, "dead-worker", "complete") is False
    assert (await run_state(admin, run_id))["run"]["status"] == "running"
    assert await repo.finish_run(run_id, "w2", "complete") is True


async def test_runs_that_keep_expiring_are_failed_not_left_running(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    for _ in range(MAX_RUN_ATTEMPTS):
        assert await repo.claim_next("w", 60) is not None
        await admin(
            "update public.workflow_runs set locked_until = now() - interval '1 second' where id = :r",
            {"r": run_id},
        )
    assert await repo.claim_next("w", 60) is None  # out of attempts
    assert await repo.fail_exhausted() == 1
    run = (await run_state(admin, run_id))["run"]
    assert run["status"] == "failed" and run["failure"]["code"] == "max_attempts_exceeded"


async def test_a_run_that_lost_its_lease_writes_no_result(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    gate = asyncio.Event()

    async def hold(_: int) -> None:
        await gate.wait()

    engine = build_engine(repo, RecordingNode(behaviour=hold))
    claimed = await repo.claim_next("slow", 60)
    assert claimed is not None

    async def renew() -> bool:
        return await repo.extend_lease(claimed.id, "slow", 60)

    task = asyncio.ensure_future(engine.execute(claimed, "slow", renew))
    await asyncio.sleep(0.2)
    # Another worker takes the run over (lease expired), then the slow one wakes up.
    await admin(
        "update public.workflow_runs set locked_until = now() - interval '1 second', locked_by = 'fast' where id = :r",
        {"r": run_id},
    )
    gate.set()
    from app.workflow.engine import LeaseLostError

    with pytest.raises(LeaseLostError):
        await task
    run = (await run_state(admin, run_id))["run"]
    assert run["status"] == "running" and run["locked_by"] == "fast"  # untouched by the stale worker


async def test_the_worker_runs_a_queued_run_end_to_end_and_returns_false_when_idle(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    worker = Worker(repo, build_engine(repo, RecordingNode()), worker_id="test-worker", lease_seconds=30)
    assert await worker.run_once() is True
    assert (await run_state(admin, run_id))["run"]["status"] == "complete"
    assert await worker.run_once() is False


async def test_shutting_the_worker_down_hands_the_run_back(
    repo: WorkflowRepository, database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)

    async def hang(_: int) -> None:
        await asyncio.sleep(30)

    worker = Worker(
        repo, build_engine(repo, RecordingNode(behaviour=hang)), worker_id="w-shutdown", lease_seconds=30
    )
    task = asyncio.ensure_future(worker.run_once())
    await asyncio.sleep(0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    run = (await run_state(admin, run_id))["run"]
    assert run["status"] == "running"
    again = await repo.claim_next("next-worker", 60)  # available immediately, no waiting for the lease
    assert again is not None and again.id == run_id


# ── Service + status endpoint ───────────────────────────────────────────────────────────────────
@pytest.fixture
async def api(
    app_database_url: SecretStr, system_database_url: SecretStr, tmp_path: Path
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, Any]]:
    keys = make_keypair("integration-key")
    settings = Settings(
        environment="test",
        database_url=app_database_url,
        system_database_url=system_database_url,
        supabase_jwt_issuer=ISSUER,
        audit_ip_hmac_secret=HMAC,
        workflows_dir=FIXTURE.parent,
        _env_file=None,
    )
    app = create_app(settings, key_provider=StaticKeyProvider(keys))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, keys, app
    await app.state.database.dispose()


def h(keys: Any, user: CurrentUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(keys, claims(user.user_id))}"}


async def test_status_endpoint_presents_queued_as_running_and_follows_the_run_to_completion(
    api: Any, make_user: MakeUser, database: Database
) -> None:
    client, keys, _ = api
    user, case_id = await one_case(database, make_user)
    repo = WorkflowRepository(database)
    run_id = await enqueue(repo, user, case_id)

    queued = (await client.get(f"/api/v1/analysis/{run_id}", headers=h(keys, user))).json()
    assert queued["schema_version"] == "run.v1" and queued["status"] == "running" and queued["progress"] == 0
    assert [s["status"] for s in queued["steps"]] == ["pending"] * 14 and "failure" not in queued

    await drive(repo, build_engine(repo, RecordingNode(StepResult("warning", "Some values were unclear."))))
    done = (await client.get(f"/api/v1/analysis/{run_id}", headers=h(keys, user))).json()
    assert done["status"] == "partial" and done["progress"] == 1 and done["finished_at"]
    assert done["warnings"] == ["Some values were unclear."] and "failure" not in done


async def test_a_failed_run_shows_the_person_safe_text_but_not_the_machine_code(
    api: Any, make_user: MakeUser, database: Database
) -> None:
    client, keys, _ = api
    user, case_id = await one_case(database, make_user)
    repo = WorkflowRepository(database)
    run_id = await enqueue(repo, user, case_id)
    await drive(repo, Engine(repo, DefinitionRegistry([definition()]), NodeRegistry(), sleep=no_sleep))
    body = (await client.get(f"/api/v1/analysis/{run_id}", headers=h(keys, user))).json()
    assert body["status"] == "failed" and set(body["failure"]) == {"title", "body"}


async def test_runs_are_visible_only_to_their_owner(
    api: Any, make_user: MakeUser, database: Database
) -> None:
    client, keys, _ = api
    a, case_id = await one_case(database, make_user)
    b = await make_user()
    run_id = await enqueue(WorkflowRepository(database), a, case_id)
    other = await client.get(f"/api/v1/analysis/{run_id}", headers=h(keys, b))
    assert other.status_code == 404 and other.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert (await client.get(f"/api/v1/analysis/{run_id}", headers=h(keys, a))).status_code == 200
    assert (await client.get(f"/api/v1/analysis/{run_id}")).status_code == 401
    assert (await client.get(f"/api/v1/analysis/{uuid.uuid4()}", headers=h(keys, a))).status_code == 404


async def test_there_is_no_endpoint_that_starts_an_analysis_yet(api: Any) -> None:
    client, _, _ = api
    spec = (await client.get("/api/v1/openapi.json")).json()
    assert not [p for p in spec["paths"] if p.endswith("/analysis") or "/runs/" in p]


async def test_enqueue_analysis_checks_ownership_documents_and_concurrency(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    a = await make_user()
    b = await make_user()
    ids = await insert_case(database, a, with_document=True)  # its document is 'ready'
    empty = (await insert_case(database, a))["case"]
    service = WorkflowService(database, WorkflowRepository(database), DefinitionRegistry([definition()]))

    with pytest.raises(AppError) as not_mine:
        await service.enqueue_analysis(b, ids["case"], "foundation_smoke", 1)
    assert not_mine.value.status_code == 404
    with pytest.raises(AppError) as no_docs:
        await service.enqueue_analysis(a, empty, "foundation_smoke", 1)
    assert no_docs.value.status_code == 409
    with pytest.raises(AppError) as unknown:
        await service.enqueue_analysis(a, ids["case"], "nope", 1)
    assert unknown.value.status_code == 503

    run_id = await service.enqueue_analysis(a, ids["case"], "foundation_smoke", 1)
    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "queued" and len(state["steps"]) == 14
    assert (await admin("select status from public.cases where id = :c", {"c": ids["case"]}))[0][
        "status"
    ] == "processing"
    with pytest.raises(AppError) as busy:
        await service.enqueue_analysis(a, ids["case"], "foundation_smoke", 1)
    assert busy.value.status_code == 409
