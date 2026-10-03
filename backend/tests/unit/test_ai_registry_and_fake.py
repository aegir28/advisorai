"""Model registry (tiers, prices, placeholders) and the deterministic fake provider."""

from decimal import Decimal

import pytest

from app.ai.providers.fake import FakeProvider, FakeStep, tokens_of
from app.ai.registry import ModelRegistry
from app.ai.types import AIConfigError, ChatMessage, GatewayError, ModelRequest, ProviderTimeoutError, Usage
from tests.ai_support import REGISTRY_FILE

pytestmark = pytest.mark.anyio


def test_the_shipped_registry_routes_every_tier_for_the_fake_provider() -> None:
    registry = ModelRegistry.from_file(REGISTRY_FILE)
    assert [registry.resolve("fake", t).id for t in (1, 2, 3)] == ["fake-small", "fake-medium", "fake-large"]
    assert [m.id for m in registry.configured("fake")] == ["fake-small", "fake-medium", "fake-large"]


def test_openai_routes_are_placeholders_until_you_fill_them_in() -> None:
    registry = ModelRegistry.from_file(REGISTRY_FILE)
    for tier in (1, 2, 3):
        with pytest.raises(GatewayError) as exc:
            registry.resolve("openai", tier)
        assert exc.value.code == "model_not_configured"
    assert registry.configured("openai") == []


def test_an_enabled_priced_openai_route_resolves_and_costs_in_micro_usd() -> None:
    registry = ModelRegistry.from_dict(
        {
            "routes": {"openai": {1: "m1"}},
            "models": {
                "m1": {
                    "provider": "openai",
                    "enabled": True,
                    "priced": True,
                    "input_per_mtok_usd": 2.5,
                    "output_per_mtok_usd": 10,
                    "max_output_tokens": 2048,
                }
            },
        }
    )
    spec = registry.resolve("openai", 1)
    assert spec.tier == 1 and spec.input_per_mtok_usd == Decimal("2.5")
    assert spec.cost_micro_usd(Usage(1_000_000, 100_000)) == 3_500_000  # $2.50 + $1.00


def test_an_unpriced_model_reports_unknown_cost_instead_of_inventing_one() -> None:
    registry = ModelRegistry.from_dict(
        {
            "routes": {"openai": {1: "m1"}},
            "models": {
                "m1": {
                    "provider": "openai",
                    "enabled": True,
                    "priced": False,
                    "input_per_mtok_usd": 0,
                    "output_per_mtok_usd": 0,
                    "max_output_tokens": 10,
                }
            },
        }
    )
    assert registry.resolve("openai", 1).cost_micro_usd(Usage(5, 5)) is None


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"models": {}, "routes": {"fake": {1: "ghost"}}},  # route to an unknown model
        {
            "models": {
                "m": {
                    "provider": "fake",
                    "enabled": True,
                    "priced": True,
                    "input_per_mtok_usd": 1,
                    "output_per_mtok_usd": 1,
                    "max_output_tokens": 1,
                }
            },
            "routes": {"openai": {1: "m"}},  # model belongs to a different provider
        },
    ],
)
def test_an_invalid_registry_is_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(AIConfigError):
        ModelRegistry.from_dict(raw)


async def test_the_fake_provider_is_scripted_and_deterministic() -> None:
    fake = FakeProvider(
        [FakeStep(text="one"), FakeStep(error=ProviderTimeoutError()), FakeStep(text="three")]
    )
    req = ModelRequest(model="m", messages=(ChatMessage("user", "abcdefgh"),))
    first = await fake.complete(req)
    assert (first.text, first.usage) == ("one", Usage(tokens_of("abcdefgh"), tokens_of("one")))
    with pytest.raises(ProviderTimeoutError):
        await fake.complete(req)
    assert (await fake.complete(req)).text == "three"
    assert [r.messages[0].content for r in fake.requests] == ["abcdefgh"] * 3


async def test_the_fake_provider_can_answer_from_canned_json_by_schema_name() -> None:
    fake = FakeProvider(canned={"Summary": {"headline": "h", "items": []}})
    out = await fake.complete(ModelRequest(model="m", messages=(), schema_name="Summary"))
    assert out.text == '{"headline": "h", "items": []}'
