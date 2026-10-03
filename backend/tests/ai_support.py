"""Shared helpers for the AI tests: a tiny output schema, a gateway wired to the fake provider, a no-wait sleep."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.ai.gateway import AIGateway, GatewayConfig, GatewayRequest, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.ai.registry import ModelRegistry
from app.ai.types import CallContext
from app.ai.usage import AIMetrics, InMemoryUsageSink
from app.audit.writer import AuditAction

REGISTRY_FILE = Path(__file__).resolve().parents[2] / "registry" / "models.yaml"


class Summary(BaseModel):
    """A neutral output schema for infrastructure tests. It is not a clinical contract."""

    headline: str
    items: list[str]


GOOD = json.dumps({"headline": "ok", "items": ["a", "b"]})


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[tuple[AuditAction, dict[str, Any]]] = []

    async def record_completed(self, action: AuditAction, **kwargs: Any) -> None:
        self.events.append((action, kwargs))


class Sleeper:
    """Records requested sleeps instead of waiting, so retry tests are instant and exact."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def make_gateway(
    provider: FakeProvider | None = None,
    *,
    config: GatewayConfig | None = None,
    audit: RecordingAudit | None = None,
) -> tuple[AIGateway, FakeProvider, InMemoryUsageSink, Sleeper]:
    provider = provider or FakeProvider()
    sink = InMemoryUsageSink()
    sleeper = Sleeper()
    gateway = AIGateway(
        provider,
        ModelRegistry.from_file(REGISTRY_FILE),
        config=config or GatewayConfig(),
        sink=sink,
        audit=audit,
        metrics=AIMetrics(),
        sleep=sleeper,
    )
    return gateway, provider, sink, sleeper


def request(
    *segments: PromptSegment,
    tier: int = 1,
    context: CallContext | None = None,
    known: tuple[str, ...] = (),
) -> GatewayRequest[Summary]:
    return GatewayRequest(
        schema=Summary,
        system="Return the requested JSON.",
        segments=segments or (PromptSegment("synthetic text", "free_text"),),
        tier=tier,
        context=context or CallContext(purpose="test.step"),
        known_identifiers=known,
    )


def step(text: str = GOOD, **kwargs: Any) -> FakeStep:
    return FakeStep(text=text, **kwargs)
