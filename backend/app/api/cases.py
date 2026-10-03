"""/cases: the case lifecycle. The owner is always the verified caller (no owner or user ID is accepted)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import CaseServiceDep, client_ip
from app.auth.dependencies import CurrentUserDep
from app.safety.red_flags import check
from app.schemas.case_api import CaseSummary, NewCaseInput, SafetyCheckRequest, SafetyCheckResult

router = APIRouter(prefix="/cases", tags=["cases"])

_AUTH: dict[int | str, dict[str, Any]] = {401: {"description": "Missing, invalid or expired token."}}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "No such case for this account."}}

CaseId = Annotated[uuid.UUID, "case id"]


@router.post(
    "/safety-check",
    response_model=SafetyCheckResult,
    response_model_exclude_none=True,
    summary="Red-flag screen (rules only: no AI, nothing stored or logged)",
    operation_id="safetyCheck",
    responses=_AUTH,
)
async def safety_check(body: SafetyCheckRequest, user: CurrentUserDep) -> SafetyCheckResult:
    del user  # authenticated callers only; the screen itself is stateless
    result = check(body.text, body.current_symptoms)
    return SafetyCheckResult.model_validate(
        {"red_flag": result.red_flag, "matched": result.matched}
        | ({"category": result.category} if result.category else {})
    )


@router.get(
    "",
    response_model=list[CaseSummary],
    response_model_exclude_none=True,
    summary="The caller's cases",
    operation_id="listCases",
    responses=_AUTH,
)
async def list_cases(user: CurrentUserDep, cases: CaseServiceDep) -> list[CaseSummary]:
    return await cases.list(user)


@router.post(
    "",
    response_model=CaseSummary,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create a case",
    operation_id="createCase",
    responses=_AUTH,
)
async def create_case(
    body: NewCaseInput, request: Request, user: CurrentUserDep, cases: CaseServiceDep
) -> CaseSummary:
    return await cases.create(user, body, client_ip=client_ip(request))


@router.get(
    "/{case_id}",
    response_model=CaseSummary,
    response_model_exclude_none=True,
    summary="One of the caller's cases",
    operation_id="getCase",
    responses=_AUTH | _NOT_FOUND,
)
async def get_case(case_id: uuid.UUID, user: CurrentUserDep, cases: CaseServiceDep) -> CaseSummary:
    return await cases.get(user, case_id)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a case, its documents and its files",
    operation_id="deleteCase",
    responses=_AUTH | _NOT_FOUND | {503: {"description": "Files could not be removed; retry."}},
)
async def delete_case(
    case_id: uuid.UUID, request: Request, user: CurrentUserDep, cases: CaseServiceDep
) -> Response:
    await cases.delete(user, case_id, client_ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
