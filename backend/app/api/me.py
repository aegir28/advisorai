"""GET /api/v1/me: who the verified token belongs to.

The proof that the whole chain works end to end: JWT -> `CurrentUser` -> user-scoped transaction ->
RLS -> the caller's own profile. The route takes no user ID from the client.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import CurrentUserDep
from app.core.errors import AppError
from app.db.database import Database
from app.db.profiles import get_profile
from app.schemas.common import WireModel
from app.schemas.errors import ErrorCode

router = APIRouter(tags=["account"])


class MeResponse(WireModel):
    user_id: str
    display_name: str | None = None
    locale: str
    consented_at: datetime | None = None
    consent_version: str | None = None
    data_mode: str


def get_database(request: Request) -> Database:
    database: Database | None = request.app.state.database
    if database is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "The service is not ready.", status_code=503)
    return database


DatabaseDep = Annotated[Database, Depends(get_database)]


@router.get(
    "/me",
    response_model=MeResponse,
    # Optional means ABSENT on the wire, never null (ADR 0001).
    response_model_exclude_none=True,
    summary="The signed-in user's own profile",
    operation_id="getMe",
    responses={
        401: {"description": "Missing, invalid or expired token."},
        503: {"description": "Sign-in or the database is not available."},
    },
)
async def get_me(request: Request, user: CurrentUserDep, database: DatabaseDep) -> MeResponse:
    async with database.user_session(user) as connection:
        profile = await get_profile(connection, user.user_id)
    if profile is None:
        raise AppError(ErrorCode.PROFILE_NOT_FOUND, "Your profile could not be found.", status_code=404)
    # Optional means ABSENT on the wire (ADR 0001): leave out the fields that are not set instead of
    # passing None, which the contract model (correctly) refuses.
    body: dict[str, object] = {
        "user_id": str(profile.user_id),
        "locale": profile.locale,
        "data_mode": request.app.state.settings.data_mode,
    }
    for key, value in (
        ("display_name", profile.display_name),
        ("consented_at", profile.consented_at),
        ("consent_version", profile.consent_version),
    ):
        if value is not None:
            body[key] = value
    return MeResponse.model_validate(body)
