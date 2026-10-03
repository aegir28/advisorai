"""Profile reads. The only module that touches `public.profiles` in this phase."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class Profile:
    user_id: uuid.UUID
    display_name: str | None
    locale: str
    consented_at: datetime | None
    consent_version: str | None


async def get_profile(connection: AsyncConnection, user_id: uuid.UUID) -> Profile | None:
    """The caller's own profile. RLS already limits the table to the caller; the explicit filter is
    defence in depth, so the query is correct even if it were ever run without RLS."""
    result = await connection.execute(
        text(
            "select user_id, display_name, locale, consented_at, consent_version"
            " from public.profiles where user_id = :user_id"
        ),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return Profile(
        user_id=row["user_id"],
        display_name=row["display_name"],
        locale=row["locale"],
        consented_at=row["consented_at"],
        consent_version=row["consent_version"],
    )


async def record_consent(connection: AsyncConnection, user_id: uuid.UUID, version: str) -> Profile | None:
    """The caller accepts the prototype / consent notice. The first acceptance of a version keeps its time;
    accepting a newer version replaces both. RLS and the column grant limit this to the caller's own row."""
    await connection.execute(
        text(
            "update public.profiles set consented_at = now(), consent_version = :version"
            " where user_id = :user_id and (consent_version is distinct from :version)"
        ),
        {"user_id": user_id, "version": version},
    )
    return await get_profile(connection, user_id)
