"""The AI gateway: the only way to reach a model.

    invoke(): de-identify -> residual-PII check -> route (tier -> model) -> budget -> call
              (timeout, retries with backoff) -> parse + validate against the output schema
              (bounded re-asks) -> meter (tokens, cost) -> usage row + audit + metrics

Guarantees, each tested with the fake provider (tests/unit/test_ai_gateway.py):

* Nothing identifying leaves: free text is de-identified, and a prompt that still matches an identifier
  pattern is refused (`pii_blocked`) before any provider is called.
* Output is a validated pydantic object or an error. Raw model text is never returned and never logged.
* Provider failures retry only when retryable, with bounded exponential backoff; every call has a timeout.
* Every call (success or failure) leaves a usage record and an audit row with ids and counts only.
* No prompt, response, document text or exception message is logged. Logs carry codes, ids and numbers.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.ai.provider import Provider
from app.ai.registry import ModelRegistry, ModelSpec
from app.ai.types import (
    CallContext,
    ChatMessage,
    GatewayError,
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    Usage,
)
from app.ai.usage import AIMetrics, RunBudget, UsageRecord, UsageSink
from app.audit.writer import AuditAction, AuditRecorder
from app.core.request_id import get_request_id
from app.safety.deidentify import deidentify, find_residual

logger = logging.getLogger("advisorai.ai")

MAX_BACKOFF_S = 30.0


@dataclass(frozen=True, slots=True)
class PromptSegment:
    """One part of the user turn. `template` text is developer-authored (trusted, but still checked for
    residual identifiers). `free_text` is anything a person typed or a document contained: always scrubbed."""

    text: str
    kind: Literal["template", "free_text"] = "free_text"


@dataclass(slots=True)
class GatewayRequest[T: BaseModel]:
    schema: type[T]
    system: str
    segments: Sequence[PromptSegment]
    tier: int = 1
    max_output_tokens: int = 1024
    context: CallContext = field(default_factory=CallContext)
    # Exact strings the system already knows are identity (the person's name, email, phone).
    known_identifiers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GatewayResult[T: BaseModel]:
    output: T
    usage: Usage
    cost_micro_usd: int | None
    model: str
    provider: str
    attempts: int
    latency_ms: int
    redactions: dict[str, int]
    request_id: str | None


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    request_timeout_s: float = 60.0
    max_attempts: int = 3  # provider calls per invoke() for retryable failures
    schema_retries: int = 1  # extra provider calls when the output fails validation
    backoff_base_s: float = 1.0
    run_budget_micro_usd: int = 0  # 0 = no cap


class AIGateway:
    def __init__(
        self,
        provider: Provider,
        registry: ModelRegistry,
        *,
        config: GatewayConfig | None = None,
        sink: UsageSink | None = None,
        audit: AuditRecorder | None = None,
        metrics: AIMetrics | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._config = config or GatewayConfig()
        self._sink = sink
        self._audit = audit
        self.metrics = metrics or AIMetrics()
        self._budget = RunBudget(self._config.run_budget_micro_usd)
        self._sleep = sleep

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def invoke[T: BaseModel](self, request: GatewayRequest[T]) -> GatewayResult[T]:
        ctx = request.context
        ctx.request_id = ctx.request_id or get_request_id()
        started = time.monotonic()
        spec: ModelSpec | None = None
        usage_total = Usage()
        attempts = 0
        outcome = "success"
        try:
            spec = self._registry.resolve(self._provider.name, request.tier)
            if self._budget.exceeded(ctx.run_id):
                raise GatewayError("budget_exceeded")
            messages, redactions = self._prepare(request)
            model_request = ModelRequest(
                model=spec.id,
                messages=messages,
                response_schema=request.schema.model_json_schema(),
                schema_name=request.schema.__name__,
                max_output_tokens=min(request.max_output_tokens, spec.max_output_tokens),
                timeout_s=self._config.request_timeout_s,
            )

            output: T | None = None
            schema_failures = 0
            while output is None:
                response, used_attempts = await self._call_with_retries(model_request)
                attempts += used_attempts
                usage_total = usage_total + response.usage
                self._budget.charge(ctx.run_id, spec.cost_micro_usd(response.usage))
                output = self._parse(request.schema, response)
                if output is None:
                    schema_failures += 1
                    self.metrics.incr("schema_failures")
                    if schema_failures > self._config.schema_retries:
                        raise GatewayError("schema_validation_failed")
                    if self._budget.exceeded(ctx.run_id):
                        raise GatewayError("budget_exceeded")
        except GatewayError as exc:
            outcome = exc.code
            self.metrics.incr(f"failed.{exc.code}")
            await self._finish(request, spec, usage_total, attempts, started, outcome)
            raise

        latency_ms = await self._finish(request, spec, usage_total, attempts, started, outcome)
        self.metrics.incr("calls_ok")
        return GatewayResult(
            output=output,
            usage=usage_total,
            cost_micro_usd=spec.cost_micro_usd(usage_total),
            model=spec.id,
            provider=spec.provider,
            attempts=attempts,
            latency_ms=latency_ms,
            redactions=redactions,
            request_id=ctx.request_id,
        )

    # ── steps ──────────────────────────────────────────────────────────────────────────────────
    def _prepare(self, request: GatewayRequest[Any]) -> tuple[tuple[ChatMessage, ...], dict[str, int]]:
        redactions: dict[str, int] = {}
        parts: list[str] = []
        for segment in request.segments:
            if segment.kind == "free_text":
                result = deidentify(segment.text, known_identifiers=request.known_identifiers)
                for category, n in result.counts.items():
                    redactions[category] = redactions.get(category, 0) + n
                parts.append(result.text)
            else:
                parts.append(segment.text)
        user = "\n\n".join(parts)
        residual = find_residual(request.system + "\n" + user)
        if residual:
            # Categories only: the identifying text itself is never logged or stored.
            logger.warning("prompt blocked by the PII boundary (%s)", ",".join(residual))
            self.metrics.incr("pii_blocked")
            raise GatewayError("pii_blocked")
        if redactions:
            self.metrics.incr("redactions", sum(redactions.values()))
        return (ChatMessage("system", request.system), ChatMessage("user", user)), redactions

    async def _call_with_retries(self, model_request: ModelRequest) -> tuple[ModelResponse, int]:
        last: ProviderError | None = None
        for attempt in range(1, self._config.max_attempts + 1):
            try:
                async with asyncio.timeout(model_request.timeout_s):
                    response = await self._provider.complete(model_request)
                self.metrics.incr("provider_calls")
                return response, attempt
            except TimeoutError:
                last = ProviderTimeoutError()
            except ProviderError as exc:
                last = exc
            self.metrics.incr("provider_errors")
            if not last.retryable:
                raise GatewayError(last.code)
            if attempt < self._config.max_attempts:
                self.metrics.incr("retries")
                await self._sleep(self._delay(attempt, last))
        raise GatewayError("retries_exhausted", retryable=True)

    def _delay(self, attempt: int, error: ProviderError) -> float:
        if isinstance(error, ProviderRateLimitedError) and error.retry_after_s is not None:
            return min(error.retry_after_s, MAX_BACKOFF_S)
        return min(float(self._config.backoff_base_s * 2 ** (attempt - 1)), MAX_BACKOFF_S)

    @staticmethod
    def _parse[T: BaseModel](schema: type[T], response: ModelResponse) -> T | None:
        if response.finish_reason == "length":
            return None  # truncated output is never trusted, even if it happens to parse
        try:
            return schema.model_validate(json.loads(response.text))
        except (ValueError, ValidationError):
            return None

    async def _finish(
        self,
        request: GatewayRequest[Any],
        spec: ModelSpec | None,
        usage: Usage,
        attempts: int,
        started: float,
        outcome: str,
    ) -> int:
        latency_ms = int((time.monotonic() - started) * 1000)
        ctx = request.context
        model = spec.id if spec else "unresolved"
        provider = spec.provider if spec else self._provider.name
        cost = spec.cost_micro_usd(usage) if spec else None
        self.metrics.incr("input_tokens", usage.input_tokens)
        self.metrics.incr("output_tokens", usage.output_tokens)
        if cost:
            self.metrics.incr("cost_micro_usd", cost)
        logger.info(
            "ai call %s model=%s tier=%d attempts=%d in=%d out=%d ms=%d request=%s run=%s node=%s",
            outcome,
            model,
            request.tier,
            attempts,
            usage.input_tokens,
            usage.output_tokens,
            latency_ms,
            ctx.request_id,
            ctx.run_id,
            ctx.node_id,
        )
        if spec is not None and self._sink is not None:
            await self._sink.record(
                UsageRecord(
                    purpose=ctx.purpose,
                    provider=provider,
                    model=model,
                    tier=request.tier,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_micro_usd=cost,
                    latency_ms=latency_ms,
                    attempts=max(attempts, 1),
                    outcome=outcome,
                    request_id=ctx.request_id,
                    run_id=ctx.run_id,
                    case_id=ctx.case_id,
                    owner_user_id=ctx.owner_user_id,
                    node_id=ctx.node_id,
                )
            )
        if self._audit is not None and ctx.owner_user_id is not None:
            await self._audit.record_completed(
                AuditAction.AI_CALL,
                actor=uuid.UUID(ctx.owner_user_id),
                target_type="workflow_run" if ctx.run_id else "case",
                target_id=ctx.run_id or ctx.case_id,
                metadata={
                    "result": "ok" if outcome == "success" else outcome,
                    "model": model,
                    "provider": provider,
                    "tier": request.tier,
                    "count": max(attempts, 1),
                    **({"step": ctx.node_id} if ctx.node_id else {}),
                },
            )
        return latency_ms
