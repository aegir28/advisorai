"""Task chains and fallback, the privacy policy, and the cumulative budget guard (all on fake providers)."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.budget import InMemorySpendReader, LedgerBudgetGuard, inr_to_micro_usd
from app.ai.gateway import AIGateway, GatewayConfig, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.ai.registry import ModelRegistry
from app.ai.types import GatewayError, ProviderRejectedError, ProviderUnavailableError, Usage
from app.ai.usage import AIMetrics, InMemoryUsageSink
from tests.ai_support import GOOD, Sleeper, request

pytestmark = pytest.mark.anyio


def model(provider: str, in_price: float = 1.0, out_price: float = 4.0, **kw: object) -> dict[str, object]:
    return {
        "provider": provider,
        "enabled": True,
        "priced": True,
        "input_per_mtok_usd": in_price,
        "output_per_mtok_usd": out_price,
        "max_output_tokens": 2048,
        **kw,
    }


def registry(**extra: object) -> ModelRegistry:
    raw: dict[str, object] = {
        "providers": {
            "alpha": {"data_handling": {"zero_retention": "verified"}},
            "beta": {
                "data_handling": {
                    "zero_retention": "requestable",
                    "source": "https://example.test",
                    "checked_on": "2026-10-03",
                }
            },
            "gamma": {"data_handling": {"zero_retention": "unsuitable"}},
        },
        "tasks": {
            "specialist": [{"provider": "alpha", "tier": 2}, {"provider": "beta", "tier": 2}],
            "only_gamma": [{"provider": "gamma", "tier": 1}],
            "chain_by_model": [{"model": "alpha-big"}, {"model": "alpha-small"}],
        },
        "routes": {
            "alpha": {1: "alpha-small", 2: "alpha-big"},
            "beta": {1: "beta-small", 2: "beta-big"},
            "gamma": {1: "gamma-small"},
        },
        "models": {
            "alpha-small": model("alpha", 0.1, 0.4),
            "alpha-big": model("alpha", 2.0, 8.0),
            "beta-small": model("beta", 0.1, 0.4),
            "beta-big": model("beta", 2.0, 8.0),
            "gamma-small": model("gamma", 0.1, 0.4),
        },
    }
    raw.update(extra)
    return ModelRegistry.from_dict(raw)


def gateway(
    providers: dict[str, FakeProvider],
    reg: ModelRegistry | None = None,
    *,
    default: str = "alpha",
    guard: LedgerBudgetGuard | None = None,
    config: GatewayConfig | None = None,
) -> tuple[AIGateway, InMemoryUsageSink, AIMetrics]:
    sink, metrics = InMemoryUsageSink(), AIMetrics()
    gw = AIGateway(
        providers,
        reg or registry(),
        default_provider=default,
        config=config or GatewayConfig(),
        sink=sink,
        metrics=metrics,
        guard=guard,
        sleep=Sleeper(),
    )
    return gw, sink, metrics


def req(task: str = "specialist", **kw):  # type: ignore[no-untyped-def]
    r = request(PromptSegment("synthetic text", "free_text"), tier=2)
    r.task = task
    for k, v in kw.items():
        setattr(r, k, v)
    return r


# ── fallback ─────────────────────────────────────────────────────────────────────────────────────────
async def test_the_first_candidate_answers_and_the_second_is_never_called() -> None:
    a, b = FakeProvider([FakeStep(text=GOOD)], name="alpha"), FakeProvider([FakeStep(text=GOOD)], name="beta")
    gw, sink, _ = gateway({"alpha": a, "beta": b})
    result = await gw.invoke(req())
    assert (result.provider, result.model) == ("alpha", "alpha-big") and not b.requests
    assert len(sink.records) == 1


async def test_a_provider_that_cannot_answer_falls_back_and_both_calls_are_metered() -> None:
    a = FakeProvider([FakeStep(error=ProviderUnavailableError()) for _ in range(3)], name="alpha")
    b = FakeProvider([FakeStep(text=GOOD)], name="beta")
    gw, sink, metrics = gateway({"alpha": a, "beta": b})
    result = await gw.invoke(req())
    assert (result.provider, result.model) == ("beta", "beta-big")
    assert [r.outcome for r in sink.records] == ["retries_exhausted", "success"]
    assert [r.model for r in sink.records] == ["alpha-big", "beta-big"]
    assert metrics.snapshot()["fallbacks"] == 1


async def test_unusable_output_falls_back_to_the_next_model() -> None:
    a = FakeProvider([FakeStep(text="not json"), FakeStep(text="still not json")], name="alpha")
    b = FakeProvider([FakeStep(text=GOOD)], name="beta")
    gw, sink, _ = gateway({"alpha": a, "beta": b})
    result = await gw.invoke(req())
    assert result.provider == "beta" and [r.outcome for r in sink.records] == [
        "schema_validation_failed",
        "success",
    ]


async def test_a_task_can_chain_models_of_one_provider() -> None:
    a = FakeProvider(
        [FakeStep(error=ProviderUnavailableError()) for _ in range(3)] + [FakeStep(text=GOOD)], name="alpha"
    )
    gw, sink, _ = gateway({"alpha": a})
    result = await gw.invoke(req("chain_by_model"))
    assert result.model == "alpha-small" and [r.model for r in sink.records] == ["alpha-big", "alpha-small"]


async def test_the_last_failure_is_raised_when_every_candidate_fails() -> None:
    a = FakeProvider([FakeStep(error=ProviderUnavailableError()) for _ in range(3)], name="alpha")
    b = FakeProvider([FakeStep(error=ProviderUnavailableError()) for _ in range(3)], name="beta")
    gw, sink, _ = gateway({"alpha": a, "beta": b})
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req())
    assert exc.value.code == "retries_exhausted" and len(sink.records) == 2


async def test_a_privacy_block_is_never_shopped_around_to_another_provider() -> None:
    a, b = FakeProvider(name="alpha"), FakeProvider(name="beta")
    gw, _, _ = gateway({"alpha": a, "beta": b})
    r = req()
    r.segments = [PromptSegment("Contact asha.verma@example.org please.", "template")]
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(r)
    assert exc.value.code == "pii_blocked" and not a.requests and not b.requests


async def test_a_non_retryable_refusal_does_not_fall_back() -> None:
    a = FakeProvider([FakeStep(error=ProviderRejectedError("provider_content_refused"))], name="alpha")
    b = FakeProvider([FakeStep(text=GOOD)], name="beta")
    gw, _, _ = gateway({"alpha": a, "beta": b})
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req())
    assert exc.value.code == "provider_content_refused" and not b.requests


async def test_a_candidate_with_no_provider_configured_is_skipped_not_guessed() -> None:
    b = FakeProvider([FakeStep(text=GOOD)], name="beta")
    gw, _, _ = gateway({"beta": b}, default="beta")
    assert (await gw.invoke(req())).provider == "beta"  # alpha has no adapter/key here
    gw2, _, _ = gateway({"gamma": FakeProvider(name="gamma")}, default="gamma")
    with pytest.raises(GatewayError) as exc:
        await gw2.invoke(req())
    assert exc.value.code == "model_not_configured"


# ── privacy policy ───────────────────────────────────────────────────────────────────────────────────
async def test_an_unsuitable_provider_is_never_used() -> None:
    g = FakeProvider(name="gamma")
    gw, _, metrics = gateway({"gamma": g}, default="gamma")
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req("only_gamma"))
    assert (
        exc.value.code == "privacy_policy_blocked"
        and not g.requests
        and metrics.snapshot()["privacy_policy_blocked"] == 1
    )


async def test_require_verified_refuses_everything_that_is_not_verified() -> None:
    a = FakeProvider([FakeStep(error=ProviderUnavailableError()) for _ in range(3)], name="alpha")
    b = FakeProvider([FakeStep(text=GOOD)], name="beta")  # beta is only `requestable`
    strict = GatewayConfig(privacy_policy="require_verified")
    gw, _, _ = gateway({"alpha": a, "beta": b}, config=strict)
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req())
    assert exc.value.code == "retries_exhausted" and not b.requests  # beta was filtered out of the chain
    only_beta = gateway({"beta": FakeProvider(name="beta")}, default="beta", config=strict)[0]
    with pytest.raises(GatewayError) as exc2:
        await only_beta.invoke(req())
    assert exc2.value.code == "privacy_policy_blocked"


def test_unlisted_providers_are_unverified_and_the_fake_provider_is_not_applicable() -> None:
    reg = ModelRegistry.from_file(Path(__file__).resolve().parents[3] / "registry" / "models.yaml")
    assert reg.provider_policy("nobody").zero_retention == "unverified"
    assert reg.provider_policy("fake").allowed_under("require_verified")
    openai = reg.provider_policy("openai")
    assert openai.zero_retention == "requestable" and not openai.allowed_under("require_verified")
    assert openai.source.startswith("https://") and openai.checked_on == "2026-10-03"


def test_a_bad_retention_state_is_rejected() -> None:
    with pytest.raises(Exception, match="model_registry_invalid"):
        registry(providers={"alpha": {"data_handling": {"zero_retention": "yes_trust_me"}}})


# ── budget guard ─────────────────────────────────────────────────────────────────────────────────────
def budgeted(
    providers: dict[str, FakeProvider], cap: int, *, reserve: float = 0.0, reg: ModelRegistry | None = None
) -> tuple[AIGateway, LedgerBudgetGuard, InMemoryUsageSink, AIMetrics]:
    """A gateway whose guard reads the very ledger the gateway writes."""
    sink, metrics = InMemoryUsageSink(), AIMetrics()
    g = LedgerBudgetGuard(cap, InMemorySpendReader(sink), reserve_fraction=reserve, metrics=metrics)
    gw = AIGateway(
        providers,
        reg or registry(),
        default_provider="alpha",
        sink=sink,
        metrics=metrics,
        guard=g,
        sleep=Sleeper(),
    )
    return gw, g, sink, metrics


async def test_the_budget_converts_rupees_at_an_explicit_rate() -> None:
    assert inr_to_micro_usd(Decimal("5000"), Decimal("95")) == 52_631_578
    with pytest.raises(ValueError):
        inr_to_micro_usd(Decimal("5000"), Decimal("0"))


async def test_the_total_budget_is_a_hard_stop_and_a_reserve_is_kept_back() -> None:
    # alpha-big costs $2/Mtok in and $8/Mtok out. One call here uses 1000 in + 500 out = 6,000 micro-USD, but its
    # WORST case (the input estimate plus 1,024 max output tokens) is about 8.2k, and that is what is reserved.
    a = FakeProvider([FakeStep(text=GOOD, usage=Usage(1000, 500)) for _ in range(5)], name="alpha")
    gw, _, sink, metrics = budgeted({"alpha": a}, 20_000, reserve=0.25)  # usable 15,000
    assert (await gw.invoke(req())).cost_micro_usd == 6_000
    await gw.invoke(req())  # 12,000 spent; the next worst case would take it past the usable 15,000
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req())  # 12,000 + ~8.2k > 15,000
    assert exc.value.code == "total_budget_exceeded"
    assert len(a.requests) == 2 and sink.total_cost_micro_usd() == 12_000
    snapshot = metrics.snapshot()
    assert snapshot["budget_total_refused"] == 1 and snapshot["budget_alert_50"] == 1  # alerts fire once


async def test_parallel_calls_reserve_their_worst_case_so_they_cannot_overshoot_together() -> None:
    a = FakeProvider(
        [FakeStep(text=GOOD, usage=Usage(10, 10), delay_s=0.05) for _ in range(10)], name="alpha"
    )
    gw, _, _, _ = budgeted({"alpha": a}, 20_000)  # room for two worst cases (~8.2k each), not three
    results = await asyncio.gather(*(gw.invoke(req()) for _ in range(4)), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, GatewayError) and r.code == "total_budget_exceeded"]
    assert len(ok) == 2 and len(refused) == 2


async def test_an_unpriced_model_is_refused_while_a_budget_is_active() -> None:
    unpriced = ModelRegistry.from_dict(
        {
            "routes": {"alpha": {1: "alpha-small", 2: "alpha-big"}},
            "models": {
                "alpha-small": model("alpha", priced=False),
                "alpha-big": model("alpha", priced=False),
            },
        }
    )
    a = FakeProvider([FakeStep(text=GOOD)], name="alpha")
    gw, _, _, _ = budgeted({"alpha": a}, 1_000_000, reg=unpriced)
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req("default"))
    assert exc.value.code == "budget_unpriced_model" and not a.requests


async def test_an_agent_can_cap_the_cost_of_one_call() -> None:
    a = FakeProvider([FakeStep(text=GOOD)], name="alpha")
    gw, _, _ = gateway({"alpha": a})
    with pytest.raises(GatewayError) as exc:
        await gw.invoke(req(max_call_cost_micro_usd=100))
    assert exc.value.code == "call_cost_cap_exceeded" and not a.requests
    assert (await gw.invoke(req(max_call_cost_micro_usd=1_000_000))).provider == "alpha"


async def test_a_failed_call_still_releases_its_reservation() -> None:
    a = FakeProvider([FakeStep(error=ProviderUnavailableError()) for _ in range(40)], name="alpha")
    gw, g, _, _ = budgeted({"alpha": a}, 100_000)
    for _ in range(5):  # would exhaust the budget if failures leaked their reservations
        with pytest.raises(GatewayError) as exc:
            await gw.invoke(req("chain_by_model"))
        assert exc.value.code == "retries_exhausted"
    assert (await g.status()).in_flight_micro_usd == 0
