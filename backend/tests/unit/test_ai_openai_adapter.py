"""The OpenAI adapter against a MOCKED transport. No network and no real key are involved; the key used here is
an obviously fake constant. These tests prove request shape, response parsing, error mapping and key hygiene;
they do not prove the live API accepts the request (that is the smoke test in docs/handoff-ai-phase.md)."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.providers.openai import OpenAIProvider
from app.ai.types import (
    ChatMessage,
    ModelRequest,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

pytestmark = pytest.mark.anyio

FAKE_KEY = SecretStr("sk-test-" + "x" * 32)
REQUEST = ModelRequest(
    model="some-model",
    messages=(ChatMessage("system", "sys"), ChatMessage("user", "hello")),
    response_schema={"type": "object", "properties": {"a": {"type": "string"}}},
    schema_name="Out",
    max_output_tokens=321,
    timeout_s=5,
)
OK_BODY = {
    "id": "resp_1",
    "model": "some-model-2026",
    "status": "completed",
    "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": '{"a": "b"}'}]},
    ],
    "usage": {"input_tokens": 11, "output_tokens": 7},
}


def provider(handler: httpx.MockTransport, **kwargs: object) -> OpenAIProvider:
    return OpenAIProvider(FAKE_KEY, client=httpx.AsyncClient(transport=handler), **kwargs)  # type: ignore[arg-type]


async def test_request_shape_store_false_schema_and_bearer_header() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    out = await provider(httpx.MockTransport(handler)).complete(REQUEST)
    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["auth"] == "Bearer " + FAKE_KEY.get_secret_value()
    assert body["store"] is False and body["max_output_tokens"] == 321 and body["model"] == "some-model"
    assert body["input"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["name"] == "Out" and fmt["strict"] is False
    assert (out.text, out.usage.input_tokens, out.usage.output_tokens, out.provider) == (
        '{"a": "b"}',
        11,
        7,
        "openai",
    )
    assert out.provider_request_id == "resp_1" and out.finish_reason == "stop"


async def test_a_custom_base_url_and_strict_schema_are_honoured() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert json.loads(request.content)["text"]["format"]["strict"] is True
        return httpx.Response(200, json=OK_BODY)

    p = OpenAIProvider(
        FAKE_KEY,
        base_url="https://proxy.example/v1/",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        strict_schema=True,
    )
    await p.complete(REQUEST)
    assert seen == ["https://proxy.example/v1/responses"]


async def test_incomplete_output_is_reported_as_length() -> None:
    body = {**OK_BODY, "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}
    out = await provider(httpx.MockTransport(lambda r: httpx.Response(200, json=body))).complete(REQUEST)
    assert out.finish_reason == "length"


@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        (429, {"retry-after": "12"}, ProviderRateLimitedError),
        (500, {}, ProviderUnavailableError),
        (503, {}, ProviderUnavailableError),
        (401, {}, ProviderRejectedError),
        (403, {}, ProviderRejectedError),
        (400, {}, ProviderRejectedError),
    ],
)
async def test_http_errors_map_to_the_gateway_error_taxonomy(
    status: int, headers: dict[str, str], error: type[Exception]
) -> None:
    p = provider(httpx.MockTransport(lambda r: httpx.Response(status, headers=headers, json={"error": "x"})))
    with pytest.raises(error) as exc:
        await p.complete(REQUEST)
    if status == 429:
        assert isinstance(exc.value, ProviderRateLimitedError) and exc.value.retry_after_s == 12.0
    if status in (401, 403):
        assert exc.value.code == "provider_auth_failed"  # type: ignore[attr-defined]


async def test_transport_failures_map_to_timeout_and_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ProviderTimeoutError):
        await provider(httpx.MockTransport(timeout)).complete(REQUEST)
    with pytest.raises(ProviderUnavailableError):
        await provider(httpx.MockTransport(refused)).complete(REQUEST)


async def test_a_malformed_success_body_is_a_rejection_not_a_crash() -> None:
    p = provider(httpx.MockTransport(lambda r: httpx.Response(200, text="<html>not json</html>")))
    with pytest.raises(ProviderRejectedError) as exc:
        await p.complete(REQUEST)
    assert exc.value.code == "provider_bad_response"


async def test_the_key_never_appears_in_repr_or_in_errors() -> None:
    p = provider(
        httpx.MockTransport(lambda r: httpx.Response(401, json={"error": FAKE_KEY.get_secret_value()}))
    )
    assert FAKE_KEY.get_secret_value() not in repr(p) and FAKE_KEY.get_secret_value() not in str(p)
    with pytest.raises(ProviderRejectedError) as exc:
        await p.complete(REQUEST)
    assert FAKE_KEY.get_secret_value() not in str(exc.value) and FAKE_KEY.get_secret_value() not in repr(
        exc.value
    )


def test_an_empty_key_cannot_build_the_adapter() -> None:
    with pytest.raises(ValueError):
        OpenAIProvider(SecretStr(""))
