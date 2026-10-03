"""The signed internal API n8n calls, the n8n client, signing, and the starter's failure handling."""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.orchestration.contracts import OrchestrationStart
from app.orchestration.n8n_client import HttpN8nClient, OrchestratorUnavailableError, RecordingN8nClient
from app.orchestration.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign, verify
from tests.orch_support import make_rig

SECRET = "s" * 40
PREFIX = "/internal/orchestrator/v1"


def settings(**kw: object) -> Settings:
    return Settings(  # type: ignore[arg-type]
        environment="test",
        _env_file=None,
        n8n_enabled=True,
        n8n_webhook_url="http://n8n.local/webhook/advisorai-case-analysis",
        n8n_hmac_secret=SECRET,
        **kw,
    )


def signed(
    method: str, path: str, body: bytes = b"", *, secret: str = SECRET, ts: int | None = None
) -> dict[str, str]:
    stamp, signature = sign(secret.encode(), method, path, body, ts)
    return {TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: signature}


# ── signing ──────────────────────────────────────────────────────────────────────────────────────
def test_a_valid_signature_verifies_and_any_change_breaks_it() -> None:
    ts, sig = sign(b"k" * 32, "POST", "/a/b", b'{"x":1}')
    ok = lambda **kw: verify(  # noqa: E731
        kw.get("secret", b"k" * 32),
        kw.get("method", "POST"),
        kw.get("path", "/a/b"),
        kw.get("body", b'{"x":1}'),
        ts,
        kw.get("sig", sig),
        max_skew_seconds=300,
    )
    assert ok()
    assert not ok(body=b'{"x":2}') and not ok(path="/a/c") and not ok(method="GET")
    assert not ok(secret=b"z" * 32) and not ok(sig="0" * 64) and not ok(sig="")


def test_a_stale_or_future_timestamp_is_refused() -> None:
    old = int(time.time()) - 3600
    ts, sig = sign(b"k" * 32, "POST", "/p", b"", old)
    assert not verify(b"k" * 32, "POST", "/p", b"", ts, sig, max_skew_seconds=300)
    assert not verify(b"k" * 32, "POST", "/p", b"", "abc", sig, max_skew_seconds=300)


# ── internal API ─────────────────────────────────────────────────────────────────────────────────
async def client_for_rig() -> tuple[TestClient, object]:
    rig = await make_rig()
    app = create_app(settings())
    app.state.orchestration = rig.service
    return TestClient(app), rig


@pytest.mark.anyio
async def test_the_internal_api_refuses_unsigned_and_wrongly_signed_calls() -> None:
    client, rig = await client_for_rig()
    path = f"{PREFIX}/runs/{rig.run_id}/begin"  # type: ignore[attr-defined]
    assert client.post(path).status_code == 401
    assert client.post(path, headers=signed("POST", path, secret="x" * 40)).status_code == 401
    assert client.post(path, headers=signed("POST", path + "x")).status_code == 401


@pytest.mark.anyio
async def test_the_internal_api_is_absent_when_n8n_is_disabled_and_hidden_from_openapi() -> None:
    off = TestClient(create_app(Settings(environment="test", _env_file=None)))
    assert off.post(f"{PREFIX}/runs/{uuid.uuid4()}/begin").status_code == 404
    spec = create_app(settings()).openapi()
    assert not any("internal" in p for p in spec["paths"])


@pytest.mark.anyio
async def test_a_signed_call_drives_a_stage_and_returns_only_ids_statuses_and_counts() -> None:
    client, rig = await client_for_rig()
    rid = rig.run_id  # type: ignore[attr-defined]
    for path in (f"{PREFIX}/runs/{rid}/begin", f"{PREFIX}/runs/{rid}/stages/intake_safety"):
        response = client.post(path, headers=signed("POST", path))
        assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok" and body["stage"] == "intake_safety" and body["counts"]["documents"] == 1
    flat = json.dumps(body).lower()
    assert "metformin" not in flat and "diabetes" not in flat
    # a retry returns the stored result
    again = client.post(path, headers=signed("POST", path)).json()
    assert again["cached"] is True


@pytest.mark.anyio
async def test_unknown_run_and_unknown_stage_are_clean_errors() -> None:
    client, rig = await client_for_rig()
    p = f"{PREFIX}/runs/{uuid.uuid4()}/begin"
    assert client.post(p, headers=signed("POST", p)).status_code == 404
    p = f"{PREFIX}/runs/{rig.run_id}/stages/not_a_stage"  # type: ignore[attr-defined]
    assert client.post(p, headers=signed("POST", p)).status_code == 400


# ── n8n client ───────────────────────────────────────────────────────────────────────────────────
START = OrchestrationStart(
    schema_version="orchestration_start.v1", run_id="r1", case_id="c1", workflow="case_analysis", resume=False
)


@pytest.mark.anyio
async def test_the_http_client_signs_the_start_request_and_sends_ids_only() -> None:
    import httpx

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["headers"], seen["path"] = request.content, request.headers, request.url.path
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await HttpN8nClient(http, "http://n8n.local/webhook/x", SECRET.encode(), 5).start(START)
    headers = seen["headers"]
    assert verify(
        SECRET.encode(),
        "POST",
        str(seen["path"]),
        seen["body"],
        headers[TIMESTAMP_HEADER],
        headers[SIGNATURE_HEADER],  # type: ignore[arg-type, index]
        max_skew_seconds=60,
    )
    assert set(json.loads(seen["body"])) == {"schema_version", "run_id", "case_id", "workflow", "resume"}  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize("status", [500, 404])
async def test_a_rejecting_or_unreachable_n8n_is_a_coded_error(status: int) -> None:
    import httpx

    def reject(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    for handler in (reject, down):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(OrchestratorUnavailableError):
                await HttpN8nClient(http, "http://n8n.local/webhook/x", SECRET.encode(), 5).start(START)


@pytest.mark.anyio
async def test_the_recording_client_can_simulate_an_outage() -> None:
    with pytest.raises(OrchestratorUnavailableError):
        await RecordingN8nClient(fail=True).start(START)
