"""Deterministic fake-provider demo: `uv run python -m app.ai.demo` (from backend/).

Shows the infrastructure working end to end with NO key, NO network and NO cost, on a fictional
text: de-identification -> routing to a model tier -> retry on a provider hiccup -> schema validation ->
usage and cost -> the PII block -> what is still missing before a real specialist can run.

The "model" is the scripted fake provider and the output schema is a neutral demo schema. Nothing here is
clinical reasoning or a recommendation; it exists so you can see the plumbing before you plug anything in.
"""

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel

from app.agents.prompts import PromptStore
from app.agents.registry import SpecialtyRegistry
from app.ai.gateway import AIGateway, GatewayConfig, GatewayRequest, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.ai.registry import ModelRegistry
from app.ai.types import CallContext, GatewayError, ProviderUnavailableError, Usage
from app.ai.usage import AIMetrics, InMemoryUsageSink

REGISTRY_FILE = Path(__file__).resolve().parents[3] / "registry" / "models.yaml"

FICTIONAL_TEXT = (
    "Patient name: Asha Verma (fictional). Contact asha.verma@example.org or +91 98765 43210. "
    "MRN: DEMO12345. "
    "Visit on 10 Feb 2026. Synthetic lab line: troponin 182 ng/L, HbA1c 8.9 %."
)


class DemoSummary(BaseModel):
    """A neutral schema for the demo only. Real output schemas live in app/schemas."""

    headline: str
    keywords: list[str]


async def no_wait(_: float) -> None:
    return None


async def run_demo() -> list[str]:
    out: list[str] = []
    say = out.append

    provider = FakeProvider(
        [
            FakeStep(error=ProviderUnavailableError()),  # a hiccup: the gateway retries
            FakeStep(
                text=json.dumps({"headline": "demo summary", "keywords": ["synthetic"]}),
                usage=Usage(1200, 300),
            ),
        ]
    )
    sink, metrics = InMemoryUsageSink(), AIMetrics()
    gateway = AIGateway(
        provider,
        ModelRegistry.from_file(REGISTRY_FILE),
        config=GatewayConfig(backoff_base_s=0),
        sink=sink,
        metrics=metrics,
        sleep=no_wait,
    )

    say("1. A call with free text containing (fictional) identifiers")
    result = await gateway.invoke(
        GatewayRequest(
            schema=DemoSummary,
            system="Return the requested JSON.",
            segments=[PromptSegment(FICTIONAL_TEXT, "free_text")],
            tier=1,
            context=CallContext(request_id="demo-1", purpose="demo.summary"),
            known_identifiers=("Asha Verma",),
        )
    )
    seen = provider.requests[-1].messages[1].content
    say(f"   prompt the provider received: {seen}")
    say(f"   redactions (counts only): {result.redactions}")
    say(f"   validated output: {result.output.model_dump()}")
    say(f"   model={result.model} provider={result.provider} attempts={result.attempts} (1 retry)")
    tokens = f"{result.usage.input_tokens}/{result.usage.output_tokens}"
    say(f"   tokens in/out={tokens} cost={result.cost_micro_usd} micro-USD")

    say("2. A prompt that still contains an identifier is refused before any provider call")
    try:
        await gateway.invoke(
            GatewayRequest(
                schema=DemoSummary,
                system="Write to demo@example.org",
                segments=[PromptSegment("x", "template")],
                context=CallContext(purpose="demo.summary"),
            )
        )
    except GatewayError as exc:
        say(f"   refused: {exc.code}; provider calls so far: {len(provider.requests)}")

    say("3. Usage ledger (what would be written to public.model_usage)")
    for record in sink.records:
        line = f"   {record.purpose} {record.model} outcome={record.outcome}"
        say(f"{line} attempts={record.attempts} cost={record.cost_micro_usd}")
    say(f"   metrics: {metrics.snapshot()}")

    say("4. What still blocks the five specialists (enable, prompt, implementation)")
    for specialty, blockers in SpecialtyRegistry.from_file().readiness(PromptStore()).items():
        say(f"   {specialty}: {', '.join(blockers) or 'ready'}")
    return out


def main() -> None:
    print("\n".join(asyncio.run(run_demo())))


if __name__ == "__main__":
    main()
