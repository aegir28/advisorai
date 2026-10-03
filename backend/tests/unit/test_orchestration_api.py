"""The signed internal API n8n calls, the n8n client, signing, and the starter's failure handling."""

import json
import time
import uuid
from typing import Any

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


def settings(**kw: Any) -> Settings:
    return Settings(
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

    def ok(
        secret: bytes = b"k" * 32,
        method: str = "POST",
        path: str = "/a/b",
        body: bytes = b'{"x":1}',
        signature: str = sig,
    ) -> bool:
        return verify(secret, method, path, body, ts, signature, max_skew_seconds=300)

    assert ok()
    assert not ok(body=b'{"x":2}') and not ok(path="/a/c") and not ok(method="GET")
    assert not ok(secret=b"z" * 32) and not ok(signature="0" * 64) and not ok(signature="")


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
    begin = f"{PREFIX}/runs/{rid}/begin"
    body = b'{"schema_version":"begin_request.v1","execution_id":"exec-1"}'
    assert (
        client.post(
            begin, content=body, headers={**signed("POST", begin, body), "Content-Type": "application/json"}
        ).status_code
        == 200
    )
    path = f"{PREFIX}/runs/{rid}/stages/intake_safety"
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
    p = f"{PREFIX}/runs/{uuid.uuid4()}/stages/intake_safety"
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

    seen: dict[str, Any] = {}

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
        headers[SIGNATURE_HEADER],
        max_skew_seconds=60,
    )
    assert set(json.loads(seen["body"])) == {"schema_version", "run_id", "case_id", "workflow", "resume"}


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


@pytest.mark.anyio
async def test_error_recovery_fails_the_run_of_a_crashed_execution_once_and_only_while_it_is_active() -> None:
    client, rig = await client_for_rig()
    rid = rig.run_id  # type: ignore[attr-defined]
    begin = f"{PREFIX}/runs/{rid}/begin"
    body = b'{"schema_version":"begin_request.v1","execution_id":"exec-9"}'
    client.post(
        begin, content=body, headers={**signed("POST", begin, body), "Content-Type": "application/json"}
    )
    fail = f"{PREFIX}/executions/exec-9/fail"
    first = client.post(fail, headers=signed("POST", fail))
    assert first.status_code == 200 and first.json()["status"] == "failed"
    run = await rig.store.get_run(rid)  # type: ignore[attr-defined]
    assert run is not None and run.status == "failed"
    assert client.post(fail, headers=signed("POST", fail)).status_code == 404  # nothing active any more
    nope = f"{PREFIX}/executions/never-started/fail"
    assert client.post(nope, headers=signed("POST", nope)).status_code == 404


@pytest.mark.anyio
async def test_begin_returns_stage_descriptors_and_a_condition_is_skipped_or_refused_through_the_api() -> (
    None
):
    client, rig = await client_for_rig()
    rid = rig.run_id  # type: ignore[attr-defined]

    def post(path: str, body: bytes = b"") -> Any:
        return client.post(
            path, content=body, headers={**signed("POST", path, body), "Content-Type": "application/json"}
        )

    begin = post(
        f"{PREFIX}/runs/{rid}/begin", b'{"schema_version":"begin_request.v1","execution_id":"exec-2"}'
    ).json()
    by_id = {s["id"]: s for s in begin["stages"]}
    assert begin["workflow"] == "case_analysis" and by_id["specialist_fanout"]["kind"] == "fanout"
    assert (
        by_id["vision_ocr"]["when"] == "needs_ocr" and by_id["cross_review"]["when"] == "enough_specialists"
    )
    assert all(
        {"retries", "backoff_seconds", "timeout_seconds", "critical", "depends_on"} <= set(s)
        for s in begin["stages"]
    )
    for stage in ("intake_safety", "document_text"):
        assert post(f"{PREFIX}/runs/{rid}/stages/{stage}").status_code == 200
    skip = f"{PREFIX}/runs/{rid}/stages/vision_ocr/skip"
    body = b'{"schema_version":"skip_request.v1","reason":"condition_not_met"}'
    done = post(skip, body)
    assert done.status_code == 200 and done.json()["status"] == "skipped"
    assert done.json()["code"] == "condition_not_met" and done.json()["condition"] == "needs_ocr"
    steps = await rig.store.step_statuses(rid)  # type: ignore[attr-defined]
    assert steps["vision_ocr"] == ("skipped", "condition_not_met:needs_ocr", None)
    # A stage without a condition (or whose flag is true) cannot be skipped: the backend is the authority.
    refused = post(f"{PREFIX}/runs/{rid}/stages/fact_extraction/skip", body)
    assert refused.status_code == 409
    # plan is only for fan-out stages
    assert post(f"{PREFIX}/runs/{rid}/stages/routing/plan").status_code == 400
