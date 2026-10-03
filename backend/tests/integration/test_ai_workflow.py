"""AI step integration on real PostgreSQL: the generic AI node + gateway + engine + persistence, driven by the
deterministic fake provider. The 14-node smoke definition is bound to a neutral AI node so every layer, retry and
status path of the engine is exercised. This is NOT a clinical workflow and has no clinical content."""

from collections import Counter
from typing import Any

import pytest
from pydantic import SecretStr

from app.ai.gateway import AIGateway, GatewayConfig, GatewayRequest, GatewayResult, PromptSegment
from app.ai.providers.fake import FakeProvider
from app.ai.registry import ModelRegistry
from app.ai.types import ModelRequest, ModelResponse, ProviderRejectedError, ProviderUnavailableError, Usage
from app.ai.usage import PostgresUsageSink
from app.audit.writer import AuditWriter
from app.db.database import Database
from app.workflow.ai_node import AINode
from app.workflow.definitions import DefinitionRegistry
from app.workflow.engine import Engine, NodeRegistry, RunContext, StepResult
from app.workflow.repository import WorkflowRepository
from tests.ai_support import GOOD, REGISTRY_FILE, Summary
from tests.integration.conftest import Admin
from tests.integration.test_workflow import (
    HMAC,
    MakeUser,
    definition,
    drive,
    enqueue,
    no_sleep,
    one_case,
    run_state,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_ = SecretStr  # (kept for symmetry with the other integration modules)


class NodeAwareProvider:
    """Answers per node (the node id is in the system prompt) and can fail a node a set number of times."""

    name = "fake"

    def __init__(self, fail: dict[str, list[Exception]] | None = None) -> None:
        self.fail = fail or {}
        self.calls: Counter[str] = Counter()
        self.requests: list[ModelRequest] = []
        self._inner = FakeProvider()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        node = request.messages[0].content.split("node=")[1]
        self.requests.append(request)
        self.calls[node] += 1
        queue = self.fail.get(node)
        if queue:
            raise queue.pop(0)
        return ModelResponse(
            text=GOOD, usage=Usage(1000, 500), model=request.model, provider="fake", provider_request_id=node
        )


class EchoNode(AINode[Summary]):
    purpose = "test.ai_step"

    def __init__(self, gateway: AIGateway) -> None:
        super().__init__(gateway)
        self.handled: list[str] = []

    async def build_request(self, ctx: RunContext) -> GatewayRequest[Summary]:
        return GatewayRequest(
            schema=Summary,
            system=f"Neutral test step node={ctx.node_id}",
            segments=[PromptSegment("synthetic text only", "free_text")],
        )

    async def handle_output(self, ctx: RunContext, result: GatewayResult[Summary]) -> StepResult:
        self.handled.append(ctx.node_id)
        return StepResult(status="done")


def build(
    database: Database, repo: WorkflowRepository, provider: NodeAwareProvider, *, max_attempts: int = 1
) -> tuple[Engine, EchoNode]:
    audit = AuditWriter(database, HMAC)
    gateway = AIGateway(
        provider,
        ModelRegistry.from_file(REGISTRY_FILE),
        config=GatewayConfig(max_attempts=max_attempts, backoff_base_s=0),
        sink=PostgresUsageSink(database),
        audit=audit,
        sleep=no_sleep,
    )
    node = EchoNode(gateway)
    registry = NodeRegistry()
    registry.register("test.noop", node)
    return Engine(repo, DefinitionRegistry([definition()]), registry, audit=audit, sleep=no_sleep), node


async def usage_rows(admin: Admin, run_id: Any) -> list[dict[str, Any]]:
    return await admin(
        "select node, purpose, provider, model, tier, input_tokens, output_tokens, cost_micro_usd, attempts, outcome"
        " from public.model_usage where run_id = :r order by node, created_at",
        {"r": run_id},
    )


async def test_every_ai_step_is_persisted_metered_and_audited_against_its_run_and_node(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    repo = WorkflowRepository(database)
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    provider = NodeAwareProvider()
    engine, node = build(database, repo, provider)

    assert await drive(repo, engine) == "complete"

    state = await run_state(admin, run_id)
    assert {s["status"] for s in state["steps"]} == {"done"} and len(node.handled) == 14
    rows = await usage_rows(admin, run_id)
    assert [r["node"] for r in rows] == [f"n{i:02d}" for i in range(1, 15)]
    assert {(r["purpose"], r["provider"], r["model"], r["tier"], r["outcome"]) for r in rows} == {
        ("test.ai_step", "fake", "fake-small", 1, "success")
    }
    assert {(r["input_tokens"], r["output_tokens"], r["cost_micro_usd"]) for r in rows} == {(1000, 500, 300)}
    audit = await admin(
        "select metadata::text m from public.audit_logs where action = 'ai.call' and target_id = :r",
        {"r": str(run_id)},
    )
    assert len(audit) == 14 and all(
        "synthetic text" not in a["m"] and '"model": "fake-small"' in a["m"] for a in audit
    )


async def test_the_owner_can_read_their_usage_and_nobody_else_can(
    database: Database, make_user: MakeUser
) -> None:
    from sqlalchemy import text

    repo = WorkflowRepository(database)
    user, case_id = await one_case(database, make_user)
    other = await make_user()
    await enqueue(repo, user, case_id)
    engine, _ = build(database, repo, NodeAwareProvider())
    await drive(repo, engine)
    async with database.user_session(user) as c:
        assert (await c.execute(text("select count(*) from public.model_usage"))).scalar_one() == 14
    async with database.user_session(other) as c:
        assert (await c.execute(text("select count(*) from public.model_usage"))).scalar_one() == 0


async def test_a_non_retryable_provider_failure_fails_the_run_with_a_fixed_note_and_no_content(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    repo = WorkflowRepository(database)
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    provider = NodeAwareProvider({"n01": [ProviderRejectedError("provider_auth_failed")]})
    engine, _ = build(database, repo, provider)

    assert await drive(repo, engine) == "failed"

    state = await run_state(admin, run_id)
    assert state["run"]["status"] == "failed" and state["run"]["failure"]["code"] == "provider_auth_failed"
    first = state["steps"][0]
    assert first["status"] == "failed" and first["error_code"] == "provider_auth_failed"
    assert first["note"] == "This step could not be completed."
    rows = await usage_rows(admin, run_id)
    assert [(r["node"], r["outcome"]) for r in rows] == [("n01", "provider_auth_failed")]


async def test_a_retryable_outage_is_retried_by_the_engine_and_the_run_still_completes(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    repo = WorkflowRepository(database)
    user, case_id = await one_case(database, make_user)
    run_id = await enqueue(repo, user, case_id)
    # n06 has retries: 1 in the fixture. The gateway gives up after one attempt (retryable), the engine retries the step.
    provider = NodeAwareProvider({"n06": [ProviderUnavailableError()]})
    engine, _ = build(database, repo, provider, max_attempts=1)

    assert await drive(repo, engine) == "complete"

    state = await run_state(admin, run_id)
    n06 = next(s for s in state["steps"] if s["node"] == "n06")
    assert n06["status"] == "done" and n06["attempts"] == 2
    assert provider.calls["n06"] == 2
    outcomes = [r["outcome"] for r in await usage_rows(admin, run_id) if r["node"] == "n06"]
    assert sorted(outcomes) == ["retries_exhausted", "success"]


async def test_a_second_run_for_the_same_case_reuses_results_and_makes_no_new_provider_calls(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    repo = WorkflowRepository(database)
    user, case_id = await one_case(database, make_user)
    provider = NodeAwareProvider()
    engine, _ = build(database, repo, provider)
    await enqueue(repo, user, case_id)
    assert await drive(repo, engine) == "complete"
    first_calls = sum(provider.calls.values())

    second = await enqueue(repo, user, case_id)
    assert await drive(repo, engine, "w2") == "complete"
    assert sum(provider.calls.values()) == first_calls == 14  # idempotent: inputs unchanged
    assert await usage_rows(admin, second) == []
