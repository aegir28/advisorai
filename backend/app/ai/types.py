"""Provider-neutral request/response types and the error taxonomy of the AI gateway."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """What an adapter receives. Already de-identified and already routed to a concrete model."""

    model: str
    messages: tuple[ChatMessage, ...]
    # JSON Schema the output must follow (structured output), if any.
    response_schema: Mapping[str, Any] | None = None
    schema_name: str = "output"
    max_output_tokens: int = 1024
    timeout_s: float = 60.0


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    usage: Usage
    model: str
    provider: str
    finish_reason: str = "stop"
    provider_request_id: str | None = None


# ── errors ─────────────────────────────────────────────────────────────────────────────────────────
class AIError(Exception):
    """Base. `code` is a short machine code; the message never contains prompt or document content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProviderError(AIError):
    """A provider call failed. `retryable` decides whether the gateway tries again."""

    retryable = False


class ProviderRateLimitedError(ProviderError):
    retryable = True

    def __init__(self, retry_after_s: float | None = None):
        super().__init__("provider_rate_limited")
        self.retry_after_s = retry_after_s


class ProviderTimeoutError(ProviderError):
    retryable = True

    def __init__(self) -> None:
        super().__init__("provider_timeout")


class ProviderUnavailableError(ProviderError):
    retryable = True

    def __init__(self) -> None:
        super().__init__("provider_unavailable")


class ProviderRejectedError(ProviderError):
    """Bad request, auth failure, content refusal: trying again will not help."""

    retryable = False


class AIConfigError(AIError):
    """The gateway is not configured to make this call (missing key, model not set)."""


class GatewayError(AIError):
    """The gateway refused or could not complete a call. Codes: pii_blocked, budget_exceeded,
    model_not_configured, provider_failed, schema_validation_failed, retries_exhausted."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.retryable = retryable


@dataclass(slots=True)
class CallContext:
    """Correlation for one call: who/what/where, never what was said."""

    request_id: str | None = None
    run_id: str | None = None
    case_id: str | None = None
    owner_user_id: str | None = None
    node_id: str | None = None
    purpose: str = "unspecified"
    extra: dict[str, str] = field(default_factory=dict)
