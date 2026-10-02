"""Liveness endpoint. Reports that the process is up; it checks no dependency and returns no PHI."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.core.config import Settings, settings_from_request
from app.schemas.common import WireModel

router = APIRouter(tags=["system"])


class HealthResponse(WireModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


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
