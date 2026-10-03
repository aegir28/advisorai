"""The generic AI workflow node: gateway errors become engine errors, correlation is complete, nothing registered."""

import uuid

import pytest

from app.ai.gateway import GatewayRequest, GatewayResult, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.ai.types import GatewayError, ProviderRejectedError, ProviderUnavailableError
from app.core.config import Settings
from app.main import create_app
from app.workflow.ai_node import AINode, to_node_error
from app.workflow.engine import NodeError, RetryableError, RunContext, StepResult
from tests.ai_support import GOOD, Summary, make_gateway

pytestmark = pytest.mark.anyio

CTX = RunContext(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "def", 1, node_id="step_x")


class Node(AINode[Summary]):
    purpose = "test.unit"

    def __init__(self, gateway) -> None:  # type: ignore[no-untyped-def]
        super().__init__(gateway)
        self.outputs: list[Summary] = []

    async def build_request(self, ctx: RunContext) -> GatewayRequest[Summary]:
        return GatewayRequest(schema=Summary, system="s", segments=[PromptSegment("synthetic", "free_text")])

    async def handle_output(self, ctx: RunContext, result: GatewayResult[Summary]) -> StepResult:
        self.outputs.append(result.output)
        return StepResult(status="warning", note="fixed note")


async def test_success_hands_the_validated_output_to_the_node_and_correlates_the_usage_row() -> None:
    gateway, _, sink, _ = make_gateway(FakeProvider([FakeStep(text=GOOD)]))
    node = Node(gateway)
    result = await node.run(CTX)
    assert result == StepResult(status="warning", note="fixed note") and node.outputs[0].headline == "ok"
    record = sink.records[0]
    assert (record.run_id, record.case_id, record.owner_user_id, record.node_id, record.purpose) == (
        str(CTX.run_id),
        str(CTX.case_id),
        str(CTX.owner_user_id),
        "step_x",
        "test.unit",
    )


@pytest.mark.parametrize(
    ("code", "retryable", "expected_type"),
    [
        ("retries_exhausted", True, RetryableError),
        ("provider_auth_failed", False, NodeError),
        ("pii_blocked", False, NodeError),
        ("budget_exceeded", False, NodeError),
        ("schema_validation_failed", False, NodeError),
        ("model_not_configured", False, NodeError),
    ],
)
def test_gateway_errors_map_to_engine_errors_with_fixed_person_safe_notes(
    code: str, retryable: bool, expected_type: type[NodeError]
) -> None:
    error = to_node_error(GatewayError(code, retryable=retryable))
    assert type(error) is expected_type and error.code == code
    assert error.note and "provider" not in error.note.lower() and code not in error.note


async def test_a_failing_call_raises_the_engine_error_not_the_gateway_error() -> None:
    gateway, _, _, _ = make_gateway(
        FakeProvider([FakeStep(error=ProviderRejectedError("provider_bad_request"))])
    )
    with pytest.raises(NodeError) as exc:
        await Node(gateway).run(CTX)
    assert exc.value.code == "provider_bad_request" and not isinstance(exc.value, RetryableError)


async def test_exhausted_retries_surface_as_retryable_so_the_engine_can_retry_the_step() -> None:
    from app.ai.gateway import GatewayConfig

    gateway, _, _, _ = make_gateway(
        FakeProvider([FakeStep(error=ProviderUnavailableError())]), config=GatewayConfig(max_attempts=1)
    )
    with pytest.raises(RetryableError):
        await Node(gateway).run(CTX)


def test_the_fingerprint_changes_with_the_provider_so_fake_results_are_never_reused_for_real_calls() -> None:
    gateway, _, _, _ = make_gateway()
    node = Node(gateway)
    assert node.input_fingerprint(CTX) == "test.unit|fake|"


def test_the_app_builds_a_gateway_but_registers_no_node_types_and_keeps_the_worker_off() -> None:
    app = create_app(Settings(environment="test", _env_file=None))
    assert app.state.ai_gateway.provider_name == "fake"
    assert app.state.node_registry.get("anything") is None
    assert Settings(environment="test", _env_file=None).worker_enabled is False


async def test_the_documented_demo_runs_offline_and_is_deterministic() -> None:
    from app.ai.demo import run_demo

    first = await run_demo()
    assert first == await run_demo()
    text = "\n".join(first)
    assert "refused: pii_blocked" in text and "attempts=2" in text and "[EMAIL]" in text
    assert "asha.verma@example.org" not in text.split("prompt the provider received:")[1].split("\n")[0]
    assert "no_implementation" in text


async def test_status_lists_every_open_item_for_real_calls_and_never_prints_a_key() -> None:
    from app.ai.status import activation_checklist

    checks = {c.name: c for c in activation_checklist(Settings(environment="test", _env_file=None))}
    assert not checks["provider"].ok and not checks["api key"].ok and not checks["openai tier 1 model"].ok
    assert not checks["agent cardiology"].ok and not checks["worker"].ok
    keyed = activation_checklist(
        Settings(
            environment="test", _env_file=None, ai_provider="openai", openai_api_key="sk-test-" + "z" * 32
        )
    )
    assert next(c for c in keyed if c.name == "api key").ok
    assert all("sk-test" not in c.detail for c in keyed)


async def test_the_smoke_check_runs_offline_with_the_fake_provider() -> None:
    from app.ai.smoke import smoke

    lines = await smoke(Settings(environment="test", _env_file=None))
    assert lines[0].startswith("ok: provider=fake model=fake-small") and "cost=" in lines[1]
