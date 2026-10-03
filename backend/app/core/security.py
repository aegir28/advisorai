"""HTTP hardening that applies to every response and request.

* Security headers: this API returns personal health information, so nothing is cacheable (`no-store`),
  type sniffing and framing are off, and the referrer is never sent. HSTS only in production (it is sticky,
  and meaningless over plain-HTTP local development). The interactive docs (`/api/v1/docs`, `/redoc`) load
  their own scripts, so the strict CSP is not applied to them; turn the docs off in production
  (`DOCS_ENABLED=false`).
* Request size: bodies are small JSON. Files never pass through this API on the way in (they go straight to
  private storage via a signed URL), so a body over the limit is refused with `413` before it is read.
"""

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.schemas.errors import ErrorCode

MAX_BODY_BYTES = 1024 * 1024
_DOC_PREFIXES = ("/api/v1/docs", "/api/v1/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"].startswith(_DOC_PREFIXES)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cross-Origin-Resource-Policy"] = "same-site"
                if not is_docs:
                    headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                if self._hsts:
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max:
            await self._refuse(scope, receive, send)
            return

        received = 0
        started = False
        refused = False

        async def counting_receive() -> Message:
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request" and not refused and not started:
                received += len(message.get("body", b""))
                if received > self._max:
                    # Answer now, then tell the app the client is gone. The framework would otherwise
                    # turn a read failure into its own 400, so whatever it tries to send is dropped.
                    refused = True
                    await self._refuse(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if refused:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = error_response(
            413, ErrorCode.PAYLOAD_TOO_LARGE, "This request is too large.", {"max_bytes": self._max}
        )
        await response(scope, receive, send)
