"""`CurrentUser`: the authenticated caller, produced only from a verified token.

There is deliberately no other way to obtain one: no route takes a user or owner ID from the client,
and no header is trusted for identity (ADR 0005, step 5).
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError
from app.schemas.errors import ErrorCode

from .verifier import AuthError, AuthUnavailableError, JwtVerifier

logger = logging.getLogger("advisorai.auth")

_bearer = HTTPBearer(auto_error=False, description="Supabase access token (Google sign-in, Phase 2C).")


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: uuid.UUID


def _unauthenticated() -> AppError:
    # One generic answer for every failure: the reason is logged, never returned.
    return AppError(
        ErrorCode.UNAUTHENTICATED,
        "You need to sign in to do this.",
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    verifier: JwtVerifier | None = request.app.state.jwt_verifier
    if verifier is None:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "Sign-in is not available right now.",
            status_code=503,
        )
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthenticated()
    try:
        claims = await verifier.verify(credentials.credentials)
    except AuthError as exc:
        logger.info("token rejected: %s", exc.reason)
        raise _unauthenticated() from exc
    except AuthUnavailableError as exc:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "Sign-in is not available right now.",
            status_code=503,
        ) from exc
    return CurrentUser(user_id=claims.sub)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
