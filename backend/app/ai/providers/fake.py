"""Deterministic fake provider: free, offline, repeatable. Every test and the demo use it.

It is scripted, not clever: it returns what it was told to return, in order, and records what it received
(in memory only) so tests can assert on the de-identified prompt that reached the "model".
"""

import asyncio
import json
import math
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.ai.types import ModelRequest, ModelResponse, ProviderError, Usage


@dataclass(frozen=True, slots=True)
class FakeStep:
    """One scripted outcome: text to return, or an error to raise, optionally after a delay."""

    text: str | None = None
    error: ProviderError | None = None
    delay_s: float = 0.0
    usage: Usage | None = None
    finish_reason: str = "stop"


def tokens_of(text: str) -> int:
    """Stable stand-in for a tokenizer: ceil(chars / 4)."""
    return max(1, math.ceil(len(text) / 4))


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        script: Sequence[FakeStep] | None = None,
        *,
        responder: Callable[[ModelRequest], str] | None = None,
        canned: Mapping[str, Any] | None = None,
    ) -> None:
        self._script: deque[FakeStep] = deque(script or ())
        self._responder = responder
        # schema_name -> JSON-able value returned when nothing is scripted.
        self._canned = dict(canned or {})
        self.requests: list[ModelRequest] = []

    def push(self, *steps: FakeStep) -> None:
        self._script.extend(steps)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        step = self._script.popleft() if self._script else None
        if step is not None:
            if step.delay_s:
                await asyncio.sleep(step.delay_s)
            if step.error is not None:
                raise step.error
        text = self._text_for(request, step)
        prompt = "".join(m.content for m in request.messages)
        usage = (step.usage if step else None) or Usage(tokens_of(prompt), tokens_of(text))
        return ModelResponse(
            text=text,
            usage=usage,
            model=request.model,
            provider=self.name,
            finish_reason=step.finish_reason if step else "stop",
            provider_request_id=f"fake-{len(self.requests):04d}",
        )

    def _text_for(self, request: ModelRequest, step: FakeStep | None) -> str:
        if step is not None and step.text is not None:
            return step.text
        if self._responder is not None:
            return self._responder(request)
        if request.schema_name in self._canned:
            return json.dumps(self._canned[request.schema_name])
        return json.dumps({})
