"""The provider abstraction. An adapter turns a `ModelRequest` into a `ModelResponse` and nothing else:
no retries, no budgets, no validation, no logging of content. Those belong to the gateway."""

from typing import Protocol, runtime_checkable

from app.ai.types import ModelRequest, ModelResponse


@runtime_checkable
class Provider(Protocol):
    name: str

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Raise a `ProviderError` subclass on failure. Never return partial output as success."""
        ...
