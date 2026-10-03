"""The AI gateway, driven only by the deterministic fake provider (no network, no key, no cost)."""

import json
import uuid

import pytest

from app.ai.gateway import GatewayConfig, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.ai.types import (
    CallContext,
    GatewayError,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderUnavailableError,
    Usage,
)
from app.audit.writer import AuditAction
from tests.ai_support import GOOD, RecordingAudit, Summary, make_gateway, request, step

pytestmark = pytest.mark.anyio


async def test_success_returns_a_validated_object_with_usage_and_cost() -> None:
    gateway, provider, sink, _ = make_gateway(FakeProvider([step(usage=Usage(1000, 500))]))
    result = await gateway.invoke(request())
    assert isinstance(result.output, Summary) and result.output.items == ["a", "b"]
    assert (result.provider, result.model, result.attempts) == ("fake", "fake-small", 1)
    # fake-small: $0.10 / Mtok in, $0.40 / Mtok out -> (1000*0.10 + 500*0.40) / 1e6 USD = 0.0003 USD = 300 micro-USD
    assert result.cost_micro_usd == 300
    assert sink.records[0].cost_micro_usd == 300 and sink.records[0].outcome == "success"
    assert len(provider.requests) == 1


async def test_the_request_carries_the_json_schema_and_the_routed_model() -> None:
    gateway, provider, _, _ = make_gateway(FakeProvider([step()]))
    await gateway.invoke(request(tier=2))
    sent = provider.requests[0]
    assert sent.model == "fake-medium"
    assert sent.schema_name == "Summary"
    assert sent.response_schema is not None and "headline" in sent.response_schema["properties"]


async def test_free_text_is_deidentified_before_the_provider_sees_it() -> None:
    gateway, provider, _, _ = make_gateway(FakeProvider([step()]))
    result = await gateway.invoke(
        request(
            PromptSegment(
                "Patient name: Asha Rao, mail asha@example.com, phone +91 98765 43210.", "free_text"
            ),
            known=("Asha Rao",),
        )
    )
    seen = provider.requests[0].messages[1].content
    assert "asha@example.com" not in seen and "98765" not in seen and "Asha Rao" not in seen
    assert "[EMAIL]" in seen and "[PHONE]" in seen
    assert result.redactions["email"] == 1 and result.redactions["phone"] == 1


async def test_a_prompt_that_still_contains_an_identifier_is_blocked_before_any_call() -> None:
    gateway, provider, sink, _ = make_gateway()
    # Template text is trusted but still checked: an email in it must not leave.
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request(PromptSegment("Contact me at someone@example.com", "template")))
    assert exc.value.code == "pii_blocked"
    assert provider.requests == []
    assert gateway.metrics.snapshot()["pii_blocked"] == 1
    assert sink.records[0].outcome == "pii_blocked"


async def test_retryable_provider_errors_are_retried_with_backoff() -> None:
    script = [
        FakeStep(error=ProviderUnavailableError()),
        FakeStep(error=ProviderRateLimitedError(retry_after_s=7)),
        step(),
    ]
    gateway, provider, sink, sleeper = make_gateway(
        FakeProvider(script), config=GatewayConfig(backoff_base_s=2.0)
    )
    result = await gateway.invoke(request())
    assert result.attempts == 3 and len(provider.requests) == 3
    assert sleeper.delays == [2.0, 7.0]  # exponential base, then the provider's retry-after
    assert gateway.metrics.snapshot()["retries"] == 2
    assert sink.records[0].attempts == 3


async def test_backoff_is_capped() -> None:
    script = [FakeStep(error=ProviderRateLimitedError(retry_after_s=9999)), step()]
    gateway, _, _, sleeper = make_gateway(FakeProvider(script))
    await gateway.invoke(request())
    assert sleeper.delays == [30.0]


async def test_a_non_retryable_error_fails_at_once_without_retrying() -> None:
    gateway, provider, sink, sleeper = make_gateway(
        FakeProvider([FakeStep(error=ProviderRejectedError("provider_auth_failed"))])
    )
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request())
    assert exc.value.code == "provider_auth_failed" and not exc.value.retryable
    assert len(provider.requests) == 1 and sleeper.delays == []
    assert sink.records[0].outcome == "provider_auth_failed"


async def test_retries_run_out_and_the_failure_is_marked_retryable_for_the_workflow_engine() -> None:
    script = [FakeStep(error=ProviderUnavailableError()) for _ in range(3)]
    gateway, provider, _, _ = make_gateway(FakeProvider(script))
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request())
    assert exc.value.code == "retries_exhausted" and exc.value.retryable
    assert len(provider.requests) == 3


async def test_a_slow_provider_times_out_and_is_retried() -> None:
    script = [FakeStep(text=GOOD, delay_s=1.0), step()]
    gateway, provider, _, _ = make_gateway(FakeProvider(script), config=GatewayConfig(request_timeout_s=0.05))
    result = await gateway.invoke(request())
    assert result.attempts == 2 and len(provider.requests) == 2
    assert gateway.metrics.snapshot()["provider_errors"] == 1


async def test_invalid_output_is_re_asked_once_then_succeeds() -> None:
    gateway, provider, sink, _ = make_gateway(FakeProvider([step("not json"), step()]))
    result = await gateway.invoke(request())
    assert result.output.headline == "ok" and len(provider.requests) == 2
    assert gateway.metrics.snapshot()["schema_failures"] == 1
    assert sink.records[0].attempts == 2


async def test_output_that_never_validates_raises_and_the_model_text_is_never_returned() -> None:
    wrong_shape = json.dumps({"headline": 5, "items": "nope"})
    gateway, _, sink, _ = make_gateway(FakeProvider([step(wrong_shape), step("{}")]))
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request())
    assert exc.value.code == "schema_validation_failed"
    assert wrong_shape not in str(exc.value)
    assert sink.records[0].outcome == "schema_validation_failed"


async def test_truncated_output_is_not_trusted_even_if_it_parses() -> None:
    gateway, _, _, _ = make_gateway(
        FakeProvider([step(finish_reason="length"), step(finish_reason="length")])
    )
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request())
    assert exc.value.code == "schema_validation_failed"


async def test_extra_fields_in_output_are_rejected_by_a_strict_schema() -> None:
    from pydantic import ConfigDict

    from app.ai.gateway import GatewayRequest

    class Strict(Summary):
        model_config = ConfigDict(extra="forbid")

    gateway, _, _, _ = make_gateway(
        FakeProvider([step(json.dumps({"headline": "x", "items": [], "oops": 1}))] * 2)
    )
    req = GatewayRequest(schema=Strict, system="s", segments=[PromptSegment("t", "free_text")])
    with pytest.raises(GatewayError):
        await gateway.invoke(req)


async def test_an_unconfigured_model_is_refused_not_guessed() -> None:
    # The registry's openai routes are placeholders until real model ids are entered.
    from app.ai.registry import ModelRegistry
    from tests.ai_support import REGISTRY_FILE

    registry = ModelRegistry.from_file(REGISTRY_FILE)
    with pytest.raises(GatewayError) as exc:
        registry.resolve("openai", 1)
    assert exc.value.code == "model_not_configured"


async def test_usage_is_recorded_for_every_outcome_with_correlation_ids_and_no_content() -> None:
    audit = RecordingAudit()
    gateway, _, sink, _ = make_gateway(FakeProvider([step()]), audit=audit)
    owner, case, run = (str(uuid.uuid4()) for _ in range(3))
    ctx = CallContext(
        request_id="req-1",
        run_id=run,
        case_id=case,
        owner_user_id=owner,
        node_id="step_a",
        purpose="test.step",
    )
    await gateway.invoke(request(context=ctx))
    record = sink.records[0]
    assert (record.request_id, record.run_id, record.case_id, record.node_id) == (
        "req-1",
        run,
        case,
        "step_a",
    )
    assert audit.events[0][0] is AuditAction.AI_CALL
    metadata = audit.events[0][1]["metadata"]
    assert metadata["result"] == "ok" and metadata["model"] == "fake-small" and metadata["step"] == "step_a"
    # No field of the record or the audit row can carry what was said.
    assert "synthetic text" not in repr(record) and "synthetic text" not in repr(audit.events)


async def test_the_run_budget_stops_further_calls_once_spent() -> None:
    # fake-large costs $5 / $20 per Mtok. 1M input tokens = 5,000,000 micro-USD, over a 1,000,000 cap.
    gateway, provider, _, _ = make_gateway(
        FakeProvider([step(usage=Usage(1_000_000, 0)), step()]),
        config=GatewayConfig(run_budget_micro_usd=1_000_000),
    )
    run = str(uuid.uuid4())

    def ctx() -> CallContext:
        return CallContext(run_id=run, purpose="test.step")

    await gateway.invoke(request(tier=3, context=ctx()))
    with pytest.raises(GatewayError) as exc:
        await gateway.invoke(request(tier=3, context=ctx()))
    assert exc.value.code == "budget_exceeded" and len(provider.requests) == 1
    # A different run has its own budget.
    other = CallContext(run_id=str(uuid.uuid4()), purpose="test.step")
    assert (await gateway.invoke(request(context=other))).output.headline == "ok"


async def test_metrics_count_calls_tokens_and_cost() -> None:
    gateway, _, _, _ = make_gateway(FakeProvider([step(usage=Usage(10, 20))]))
    await gateway.invoke(request())
    snap = gateway.metrics.snapshot()
    assert snap["calls_ok"] == 1 and snap["input_tokens"] == 10 and snap["output_tokens"] == 20
    assert "cost_micro_usd" in snap
