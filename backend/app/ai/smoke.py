"""`uv run python -m app.ai.smoke [tier]`: make ONE small call through the real gateway and print the outcome.

With the default `ai_provider=fake` it is a free offline check. With `ADVISORAI_AI_PROVIDER=openai`, a key
and a configured model it is the first live call: it sends one fixed, fictional sentence (no patient data),
prints the model, tokens and cost (micro-USD; "unknown" if no price is entered), and never prints the key
or the response text.
"""

import asyncio
import json
import sys

from pydantic import BaseModel

from app.ai.factory import build_gateway
from app.ai.gateway import GatewayRequest, PromptSegment
from app.ai.providers.fake import FakeProvider
from app.ai.types import CallContext, GatewayError
from app.ai.usage import InMemoryUsageSink
from app.core.config import Settings, get_settings


class Pong(BaseModel):
    reply: str


async def smoke(settings: Settings, tier: int = 1) -> list[str]:
    provider = FakeProvider(canned={"Pong": {"reply": "pong"}}) if settings.ai_provider == "fake" else None
    sink = InMemoryUsageSink()
    gateway = build_gateway(settings, provider=provider, sink=sink)
    request = GatewayRequest(
        schema=Pong,
        system='Reply with JSON {"reply": "pong"}. This is a connectivity check.',
        segments=[PromptSegment("ping (synthetic connectivity check, no patient data)", "template")],
        tier=tier,
        max_output_tokens=64,
        context=CallContext(purpose="smoke.ping"),
    )
    try:
        result = await gateway.invoke(request)
    except GatewayError as exc:
        return [f"FAILED: {exc.code}", f"usage rows: {json.dumps([r.outcome for r in sink.records])}"]
    cost = (
        "unknown (no price entered)"
        if result.cost_micro_usd is None
        else f"{result.cost_micro_usd} micro-USD"
    )
    return [
        f"ok: provider={result.provider} model={result.model} attempts={result.attempts} "
        f"latency={result.latency_ms} ms",
        f"tokens in/out={result.usage.input_tokens}/{result.usage.output_tokens} cost={cost}",
    ]


def main() -> None:
    tier = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("\n".join(asyncio.run(smoke(get_settings(), tier))))


if __name__ == "__main__":
    main()
