"""Standard error contract (ADR 0002): every error response uses `ErrorEnvelope`.

Three paths all produce the same envelope with the current request ID:

1. `AppError`: raised deliberately by application code with a domain `ErrorCode`.
2. Framework errors: unknown route (404), wrong method (405), request validation (422).
3. Anything unexpected: caught by `ErrorBoundaryMiddleware` and returned as `INTERNAL_ERROR`.
   The exception text and traceback are logged server-side and never sent to the client.
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.errors import ErrorBody, ErrorCode, ErrorEnvelope

from .request_id import get_request_id

logger = logging.getLogger("advisorai.errors")

_STATUS_TO_CODE: Mapping[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
}

# Fixed, person-safe messages. Framework `detail` text is deliberately not forwarded.
_STATUS_TO_MESSAGE: Mapping[int, str] = {
    400: "The request could not be understood.",
    401: "You need to sign in to do this.",
    403: "You do not have access to this.",
    404: "The requested resource could not be found.",
    405: "This method is not supported for this resource.",
    409: "This request conflicts with the current state.",
}


class AppError(Exception):
    """A deliberate, expected failure. Routes raise this; the handler renders the envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, request_id=get_request_id(), details=details or {})
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=dict(headers) if headers else None,
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.HTTP_ERROR)
    message = _STATUS_TO_MESSAGE.get(exc.status_code) or HTTPStatus(exc.status_code).phrase
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Location, message and type only. Pydantic's `input` is dropped on purpose: it would echo
    # whatever the person submitted, which can be personal health information.
    errors = [
        {"loc": [str(part) for part in e["loc"]], "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return error_response(
        422,
        ErrorCode.VALIDATION_ERROR,
        "The request did not match the expected format.",
        {"errors": errors},
    )


class ErrorBoundaryMiddleware:
    """Turns any unhandled exception into an `INTERNAL_ERROR` envelope.

    Sits inside CORS so the browser can still read the envelope (and its request ID) on a 500.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error")
            if response_started:
                raise
            response = error_response(500, ErrorCode.INTERNAL_ERROR, "Something went wrong on our side.")
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
