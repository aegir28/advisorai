"""Liveness and readiness. Neither returns personal data or any connection detail."""

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, settings_from_request
from app.core.errors import AppError
from app.schemas.common import WireModel
from app.schemas.errors import ErrorCode

router = APIRouter(tags=["system"])
logger = logging.getLogger("advisorai.health")


class HealthResponse(WireModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadyResponse(WireModel):
    status: Literal["ready"]
    checks: dict[str, str]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    operation_id="getHealth",
)
async def get_health(settings: Annotated[Settings, Depends(settings_from_request)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness check (database reachable)",
    operation_id="getHealthReady",
    responses={503: {"description": "A dependency is not available."}},
)
async def get_ready(request: Request) -> ReadyResponse:
    database = request.app.state.database
    if database is None:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The service is not ready.",
            status_code=503,
            details={"checks": {"database": "not_configured"}},
        )
    try:
        await asyncio.wait_for(database.ping(), timeout=3.0)
    except Exception as exc:
        # Type only: the exception text can contain the connection string.
        logger.warning("readiness check failed: database (%s)", type(exc).__name__)
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The service is not ready.",
            status_code=503,
            details={"checks": {"database": "unavailable"}},
        ) from None
    return ReadyResponse(status="ready", checks={"database": "ok"})
