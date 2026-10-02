"""The API error contract (ADR 0002). Every error response from /api/v1 has this envelope.

    {"error": {"code": "CASE_NOT_FOUND", "message": "...", "request_id": "req_...", "details": {}}}

The envelope is part of API v1: a backward-incompatible change needs /api/v2 and an ADR.
`message` is safe to show a person; it never contains clinical content or user input.
`details` is machine-readable context and is `{}` when there is none.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field

from .common import WireModel


class ErrorCode(StrEnum):
    # Generic HTTP-level failures
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    # Domain failures (raised by routes once they exist)
    CASE_NOT_FOUND = "CASE_NOT_FOUND"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    TRACE_ITEM_NOT_FOUND = "TRACE_ITEM_NOT_FOUND"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"


class ErrorBody(WireModel):
    # strict=False so a plain JSON string ("CASE_NOT_FOUND") validates as the enum.
    code: Annotated[ErrorCode, Field(strict=False)]
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(WireModel):
    error: ErrorBody
