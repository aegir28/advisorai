"""Shared route dependencies: the services built in `create_app`, or `503` when one is not configured."""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.errors import AppError
from app.db.database import Database
from app.schemas.errors import ErrorCode
from app.services.cases import CaseService
from app.services.documents import DocumentService


def _service[T](value: T | None) -> T:
    if value is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "The service is not ready.", status_code=503)
    return value


def get_database(request: Request) -> Database:
    return cast(Database, _service(request.app.state.database))


def get_case_service(request: Request) -> CaseService:
    return cast(CaseService, _service(request.app.state.cases))


def get_document_service(request: Request) -> DocumentService:
    return cast(DocumentService, _service(request.app.state.documents))


def client_ip(request: Request) -> str | None:
    """The peer address, for the audit log's HMAC only. Behind a proxy, run uvicorn with
    `--proxy-headers --forwarded-allow-ips=<proxy>` so this is the real client."""
    return request.client.host if request.client else None


DatabaseDep = Annotated[Database, Depends(get_database)]
CaseServiceDep = Annotated[CaseService, Depends(get_case_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
