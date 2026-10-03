"""/internal/orchestrator/v1: the capability API n8n calls. Not part of the public contract.

Every call is HMAC-signed (timestamp window + body hash), so only n8n (holding the shared secret) can drive a
run, and only for a run id it was handed. Responses carry ids, statuses and counts, never case content.
It is excluded from the OpenAPI document and absent entirely unless `n8n_enabled`.
"""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.core.errors import AppError
from app.orchestration.contracts import (
    AgentResult,
    BeginRequest,
    BeginResult,
    FinishResult,
    RunPlan,
    StageResult,
)
from app.orchestration.service import OrchestrationService, StageError
from app.orchestration.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify
from app.schemas.errors import ErrorCode

PREFIX = "/internal/orchestrator/v1"


async def require_signature(request: Request) -> None:
    settings = cast(Settings, request.app.state.settings)
    secret = settings.n8n_hmac_secret
    if not settings.n8n_enabled or secret is None:
        raise AppError(ErrorCode.NOT_FOUND, "Not found.", status_code=404)
    body = await request.body()
    ok = verify(
        secret.get_secret_value().encode(),
        request.method,
        request.url.path,
        body,
        request.headers.get(TIMESTAMP_HEADER),
        request.headers.get(SIGNATURE_HEADER),
        max_skew_seconds=settings.n8n_max_clock_skew_seconds,
    )
    if not ok:
        raise AppError(ErrorCode.UNAUTHENTICATED, "Invalid signature.", status_code=401)


def get_service(request: Request) -> OrchestrationService:
    service = request.app.state.orchestration
    if service is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "The service is not ready.", status_code=503)
    return cast(OrchestrationService, service)


ServiceDep = Annotated[OrchestrationService, Depends(get_service)]
router = APIRouter(
    prefix=PREFIX, include_in_schema=False, dependencies=[Depends(require_signature)], tags=["internal"]
)


def _raise(exc: StageError) -> AppError:
    if exc.code == "run_not_found":
        return AppError(ErrorCode.NOT_FOUND, exc.code, status_code=404)
    if exc.code.endswith("_missing"):
        return AppError(ErrorCode.CONFLICT, exc.code, status_code=409)
    return AppError(ErrorCode.VALIDATION_ERROR, exc.code, status_code=400)


@router.post("/runs/{run_id}/begin")
async def begin(run_id: uuid.UUID, body: BeginRequest, service: ServiceDep) -> BeginResult:
    try:
        return await service.begin(run_id, body.execution_id)
    except StageError as exc:
        raise _raise(exc) from None


@router.post("/runs/{run_id}/stages/{stage_id}")
async def run_stage(run_id: uuid.UUID, stage_id: str, service: ServiceDep) -> StageResult:
    try:
        return await service.run_stage(run_id, stage_id)
    except StageError as exc:
        raise _raise(exc) from None


@router.post("/runs/{run_id}/plan")
async def plan(run_id: uuid.UUID, service: ServiceDep) -> RunPlan:
    try:
        return await service.run_plan(run_id)
    except StageError as exc:
        raise _raise(exc) from None


@router.post("/runs/{run_id}/agents/{agent_id}")
async def run_agent(run_id: uuid.UUID, agent_id: str, service: ServiceDep) -> AgentResult:
    try:
        return await service.run_agent(run_id, agent_id)
    except StageError as exc:
        raise _raise(exc) from None


@router.post("/runs/{run_id}/finish")
async def finish(run_id: uuid.UUID, service: ServiceDep) -> FinishResult:
    try:
        return await service.finish(run_id)
    except StageError as exc:
        raise _raise(exc) from None


@router.post("/executions/{execution_id}/fail")
async def fail_execution(execution_id: str, service: ServiceDep) -> FinishResult:
    """Called by the n8n error-recovery workflow. Unknown or already-finished executions are a 404 no-op."""
    result = await service.fail_execution(execution_id)
    if result is None:
        raise AppError(ErrorCode.NOT_FOUND, "No active run for this execution.", status_code=404)
    return result
