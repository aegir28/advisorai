"""Case persistence. Every function runs on a USER-scoped connection (`Database.user_session`), so RLS
applies; the explicit `owner_user_id` filters are defence in depth, so each query is correct on its own.
Nothing here writes identity: a case is a pseudonymous code, an age, a sex and free text the person typed.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

# No 0/O/1/I: codes are read aloud and typed by people.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_ATTEMPTS = 8

_SELECT = """
select c.id, c.code, c.title, c.concern, c.proposed_treatment, c.status, c.updated_at,
       p.age_years, p.sex,
       (select count(*) from public.documents d
         where d.case_id = c.id and d.status <> 'pending_upload') as document_count,
       (select r.id from public.workflow_runs r where r.case_id = c.id
         order by r.created_at desc limit 1) as run_id
  from public.cases c join public.patients p on p.id = c.patient_id and p.owner_user_id = c.owner_user_id
 where c.owner_user_id = :owner and c.deletion_requested_at is null
"""


@dataclass(frozen=True, slots=True)
class CaseRow:
    id: uuid.UUID
    code: str
    title: str | None
    concern: str
    proposed_treatment: str | None
    status: str
    updated_at: datetime
    age_years: int
    sex: str
    document_count: int
    run_id: uuid.UUID | None


def _row(m: Any) -> CaseRow:
    return CaseRow(
        id=m["id"],
        code=m["code"],
        title=m["title"],
        concern=m["concern"],
        proposed_treatment=m["proposed_treatment"],
        status=m["status"],
        updated_at=m["updated_at"],
        age_years=m["age_years"],
        sex=m["sex"],
        document_count=int(m["document_count"]),
        run_id=m["run_id"],
    )


def new_case_code() -> str:
    return "AC-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))


async def list_cases(connection: AsyncConnection, owner: uuid.UUID) -> list[CaseRow]:
    result = await connection.execute(text(_SELECT + " order by c.updated_at desc"), {"owner": owner})
    return [_row(m) for m in result.mappings()]


async def get_case(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> CaseRow | None:
    result = await connection.execute(text(_SELECT + " and c.id = :id"), {"owner": owner, "id": case_id})
    m = result.mappings().first()
    return _row(m) if m else None


async def create_case(
    connection: AsyncConnection,
    owner: uuid.UUID,
    *,
    age_years: int,
    sex: str,
    concern: str,
    proposed_treatment: str | None,
    intent: str | None,
) -> uuid.UUID:
    """One pseudonymous patient row and one case row. The `awaiting_upload` status is the first state of
    a new case: the next step is adding documents."""
    patient_id, case_id = uuid.uuid4(), uuid.uuid4()
    await connection.execute(
        text(
            "insert into public.patients (id, owner_user_id, age_years, sex) values (:id, :owner, :age, :sex)"
        ),
        {"id": patient_id, "owner": owner, "age": age_years, "sex": sex},
    )
    for _ in range(_CODE_ATTEMPTS):
        # A savepoint, so a code collision (unique per owner) does not abort the whole transaction.
        try:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "insert into public.cases (id, owner_user_id, patient_id, code, title, intent,"
                        " concern, proposed_treatment, status)"
                        " values (:id, :owner, :patient, :code, :title, :intent, :concern, :treatment,"
                        " 'awaiting_upload')"
                    ),
                    {
                        "id": case_id,
                        "owner": owner,
                        "patient": patient_id,
                        "code": new_case_code(),
                        "title": intent,
                        "intent": intent,
                        "concern": concern,
                        "treatment": proposed_treatment or None,
                    },
                )
            return case_id
        except IntegrityError as exc:
            if "cases_owner_code_key" not in str(exc.orig):
                raise
    raise RuntimeError("could not allocate a unique case code")


async def mark_deletion_requested(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> bool:
    """Hide the case and refuse new uploads while its files are being removed. False if it is not the
    caller's case. Works on a case that is already marked, so a failed delete can simply be retried."""
    result = await connection.execute(
        text(
            "update public.cases set deletion_requested_at = coalesce(deletion_requested_at, now())"
            " where id = :id and owner_user_id = :owner returning id"
        ),
        {"id": case_id, "owner": owner},
    )
    return result.first() is not None


async def delete_case(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> None:
    """Cascades to documents, records and runs; the patient row goes with it (trigger)."""
    await connection.execute(
        text("delete from public.cases where id = :id and owner_user_id = :owner"),
        {"id": case_id, "owner": owner},
    )


async def touch_case(connection: AsyncConnection, owner: uuid.UUID, case_id: uuid.UUID) -> None:
    await connection.execute(
        text("update public.cases set updated_at = now() where id = :id and owner_user_id = :owner"),
        {"id": case_id, "owner": owner},
    )
