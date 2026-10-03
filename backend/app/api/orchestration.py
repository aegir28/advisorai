"""User-facing endpoints for the n8n-orchestrated analysis: start, cancel, read the finished report."""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Header, Request, status

from app.auth.dependencies import CurrentUserDep
from app.core.errors import AppError
from app.orchestration.starter import AnalysisStarter
from app.schemas.common import WireModel
from app.schemas.errors import ErrorCode
from app.schemas.report import PatientReport

router = APIRouter(tags=["analysis"])


class StartedRun(WireModel):
    run_id: str
    created: bool


def _starter(request: Request) -> AnalysisStarter:
    starter = request.app.state.analysis_starter
    if starter is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "Analysis is not available right now.", status_code=503)
    return cast(AnalysisStarter, starter)


@router.post(
    "/cases/{case_id}/analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StartedRun,
    operation_id="startAnalysis",
    summary="Start an analysis (idempotent per Idempotency-Key)",
)
async def start_analysis(
    case_id: uuid.UUID,
    user: CurrentUserDep,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_.:-]{8,128}$")],
) -> StartedRun:
    run_id, created = await _starter(request).start(user, case_id, idempotency_key)
    return StartedRun(run_id=str(run_id), created=created)


@router.post(
    "/analysis/{run_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="cancelAnalysis",
    summary="Ask a running analysis to stop",
)
async def cancel_analysis(run_id: uuid.UUID, user: CurrentUserDep, request: Request) -> None:
    await _starter(request).cancel(user, run_id)


@router.post(
    "/analysis/{run_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="resumeAnalysis",
    summary="Resume an analysis whose orchestrator stopped (completed steps are not redone)",
)
async def resume_analysis(run_id: uuid.UUID, user: CurrentUserDep, request: Request) -> None:
    await _starter(request).resume(user, run_id)


@router.get(
    "/analysis/{run_id}/report",
    response_model=PatientReport,
    operation_id="getRunReport",
    summary="The finished patient report of a run",
    responses={404: {"description": "No report for this run (yet)."}},
)
async def get_report(run_id: uuid.UUID, user: CurrentUserDep, request: Request) -> PatientReport:
    payload = await _starter(request).report(user, run_id, "report")
    if payload is None:
        raise AppError(ErrorCode.RUN_NOT_FOUND, "No report for this run yet.", status_code=404)
    return PatientReport.model_validate(payload)
