"""Backend -> n8n: start a run. Ids only; the request is HMAC-signed; n8n answers 2xx when it has accepted it.

The client is a Protocol so tests inject a recorder, and the real one (httpx) refuses to run unless a webhook
URL and secret are configured. A failure to reach n8n is reported to the caller as `OrchestratorUnavailable`;
the run is then failed with a person-safe reason, never left "running" with nothing behind it.
"""

import json
from typing import Protocol

import httpx

from app.orchestration.contracts import OrchestrationStart
from app.orchestration.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign


class OrchestratorUnavailableError(Exception):
    """n8n did not accept the start request. The message is a fixed code."""


class N8nClient(Protocol):
    async def start(self, message: OrchestrationStart) -> None: ...


class HttpN8nClient:
    def __init__(self, http: httpx.AsyncClient, webhook_url: str, secret: bytes, timeout_s: float) -> None:
        self._http, self._url, self._secret, self._timeout = http, webhook_url, secret, timeout_s

    async def start(self, message: OrchestrationStart) -> None:
        body = json.dumps(message.model_dump(mode="json"), separators=(",", ":")).encode()
        path = httpx.URL(self._url).path
        ts, signature = sign(self._secret, "POST", path, body)
        try:
            response = await self._http.post(
                self._url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    TIMESTAMP_HEADER: ts,
                    SIGNATURE_HEADER: signature,
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError:
            raise OrchestratorUnavailableError("n8n_unreachable") from None
        if response.status_code >= 300:
            raise OrchestratorUnavailableError("n8n_rejected")


class RecordingN8nClient:
    """For tests and local dev without n8n: remembers what it was asked to start."""

    def __init__(self, *, fail: bool = False) -> None:
        self.started: list[OrchestrationStart] = []
        self._fail = fail

    async def start(self, message: OrchestrationStart) -> None:
        if self._fail:
            raise OrchestratorUnavailableError("n8n_unreachable")
        self.started.append(message)
