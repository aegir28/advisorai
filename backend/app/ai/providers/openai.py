"""OpenAI adapter over plain HTTPS (httpx): no vendor SDK, so no new dependency and no import the repo guard
has to special-case. It uses the Responses API with `store: false` (nothing is retained for the provider's
own use) and JSON-Schema structured output.

IMPORTANT: this adapter has been exercised only against a mocked transport
(tests/unit/test_ai_openai_adapter.py). It has NOT been run against the live API, because no key existed
when it was written. The first real call is the smoke test in docs/handoff-ai-phase.md ("Enabling real
calls"); treat the request and response field names as the thing to check.

The key is a SecretStr read from ADVISORAI_OPENAI_API_KEY in the BACKEND environment. It is put in the
Authorization header at call time and is never logged, stored, or included in an exception.
"""

from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.types import (
    ModelRequest,
    ModelResponse,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    Usage,
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: SecretStr,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        strict_schema: bool = False,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("an API key is required to build the OpenAI adapter")
        self._key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()
        self._strict = strict_schema

    def __repr__(self) -> str:  # never show the key, even by accident
        return f"OpenAIProvider(base_url={self._base_url!r}, key=[redacted])"

    def build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if request.response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": dict(request.response_schema),
                    "strict": self._strict,
                }
            }
        return payload

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            response = await self._client.post(
                f"{self._base_url}/responses",
                json=self.build_payload(request),
                headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                timeout=request.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError() from exc
        return self._parse(response, request)

    def _parse(self, response: httpx.Response, request: ModelRequest) -> ModelResponse:
        status = response.status_code
        if status == 429:
            retry_after = response.headers.get("retry-after")
            raise ProviderRateLimitedError(
                float(retry_after) if retry_after and retry_after.isdigit() else None
            )
        if status >= 500:
            raise ProviderUnavailableError()
        if status in (401, 403):
            raise ProviderRejectedError("provider_auth_failed")
        if status >= 400:
            raise ProviderRejectedError("provider_bad_request")
        try:
            body = response.json()
            text = "".join(
                part["text"]
                for item in body.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            usage = body.get("usage") or {}
            finish = (
                "length"
                if (body.get("incomplete_details") or {}).get("reason") == "max_output_tokens"
                else "stop"
            )
            return ModelResponse(
                text=text,
                usage=Usage(int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))),
                model=str(body.get("model", request.model)),
                provider=self.name,
                finish_reason=finish,
                provider_request_id=body.get("id"),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderRejectedError("provider_bad_response") from exc
