"""Request ID / correlation ID foundation.

Every request gets a request ID. A caller may supply one in `X-Request-ID` (so a browser, a proxy
and this service can share one ID); an unsafe or missing value is replaced by a generated
`req_<uuid4 hex>`. The ID is:

* stored in a context variable, so any code (logging, error handlers) can read it,
* echoed in the `X-Request-ID` response header on every response,
* placed in the `request_id` field of every error envelope.

Implemented as a pure ASGI middleware (not `BaseHTTPMiddleware`) so it also covers responses
produced by exception handlers and keeps context variables intact.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

# Letters, digits, `_`, `.`, `-`; 1..128 chars. Keeps the value safe for headers and log lines.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("advisorai.request")


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def get_request_id() -> str:
    """The current request's ID, or a fresh one when called outside a request."""
    return _request_id.get() or new_request_id()


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every log record so log lines can be joined to a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or "-"
        return True


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = MutableHeaders(scope=scope).get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and _SAFE_REQUEST_ID.match(incoming) else new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)

        status_code = 0
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # Path only: query strings can carry personal data and are never logged.
            logger.info(
                "%s %s -> %s in %.1f ms",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
            )
            _request_id.reset(token)
