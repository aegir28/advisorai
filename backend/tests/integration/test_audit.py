"""The audit log against a real database: append-only for every role, content-free, HMAC'd IPs."""

import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.audit.writer import AuditAction, AuditWriter
from app.auth.dependencies import CurrentUser
from app.db.database import Database, SystemOperation
from tests.integration.conftest import Admin, insert_case

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]
SECRET = SecretStr("0123456789abcdef0123456789abcdef-integration")


async def rows_for(admin: Admin, target_id: str) -> list[dict[str, Any]]:
    return await admin("select * from public.audit_logs where target_id = :t order by at", {"t": target_id})


async def test_an_audit_row_is_written_with_a_hashed_ip_and_no_content(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    target = str(uuid.uuid4())
    writer = AuditWriter(database, SECRET)
    await writer.record(
        AuditAction.DOCUMENT_VIEW, actor=user.user_id, target_type="document", target_id=target,
        client_ip="203.0.113.9", metadata={"result": "success"},
    )  # fmt: skip
    [row] = await rows_for(admin, target)
    assert row["actor_user_id"] == user.user_id and row["action"] == "document.view"
    assert row["request_id"].startswith("req_")
    assert row["ip_hash"] == writer.hash_ip("203.0.113.9") and "203" not in row["ip_hash"]
    assert row["metadata"] == {"result": "success"}


async def test_audit_rows_survive_the_deletion_of_the_user_they_describe(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    target = str(uuid.uuid4())
    await AuditWriter(database, SECRET).record(
        AuditAction.DATA_DELETION, actor=user.user_id, target_id=target
    )
    await admin("delete from auth.users where id = :id", {"id": user.user_id})
    assert len(await rows_for(admin, target)) == 1


async def test_audit_logs_cannot_be_updated_deleted_or_truncated_even_by_the_database_owner(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    target = str(uuid.uuid4())
    await AuditWriter(database, SECRET).record(AuditAction.CASE_CREATE, actor=user.user_id, target_id=target)
    for sql in (
        "update public.audit_logs set action = 'case.delete' where target_id = :t",
        "delete from public.audit_logs where target_id = :t",
        "truncate public.audit_logs",
    ):
        with pytest.raises(DBAPIError, match=r"append-only"):
            await admin(sql, {"t": target})
    assert len(await rows_for(admin, target)) == 1


async def test_clients_cannot_read_or_write_the_audit_log(database: Database, make_user: MakeUser) -> None:
    user = await make_user()
    for sql in (
        "select * from public.audit_logs",
        "insert into public.audit_logs (action) values ('case.create')",
    ):
        with pytest.raises(ProgrammingError, match=r"permission denied"):
            async with database.user_session(user) as connection:
                await connection.execute(text(sql))


async def test_the_system_login_can_only_append(database: Database) -> None:
    for sql in (
        "select * from public.audit_logs",
        "update public.audit_logs set action = 'x.y'",
        "delete from public.audit_logs",
        "select * from public.cases",
    ):
        with pytest.raises(ProgrammingError, match=r"permission denied"):
            async with database.system_session(SystemOperation.AUDIT_APPEND) as connection:
                await connection.execute(text(sql))


async def test_the_database_itself_refuses_content_even_if_the_writer_were_bypassed(
    database: Database,
) -> None:
    for bad_metadata in ({"snippet": "HbA1c 8.9"}, {"email": "a@b.c"}, {"url": "https://signed"}):
        with pytest.raises(IntegrityError, match=r"content_free|check"):
            async with database.system_session(SystemOperation.AUDIT_APPEND) as connection:
                await connection.execute(
                    text(
                        "insert into public.audit_logs (action, metadata) values ('case.update', cast(:m as jsonb))"
                    ),
                    {"m": json.dumps(bad_metadata)},
                )
    with pytest.raises(IntegrityError):
        async with database.system_session(SystemOperation.AUDIT_APPEND) as connection:
            await connection.execute(
                text("insert into public.audit_logs (action, ip_hash) values ('case.update', '203.0.113.9')")
            )


async def test_an_audit_row_outlives_a_rolled_back_business_transaction(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    user = await make_user()
    target = str(uuid.uuid4())
    writer = AuditWriter(database, SECRET)
    with pytest.raises(RuntimeError):
        async with database.user_session(user) as connection:
            await connection.execute(text("insert into public.patients (age_years, sex) values (20, 'M')"))
            await writer.record(
                AuditAction.CASE_CREATE, actor=user.user_id, target_id=target
            )  # own transaction
            raise RuntimeError("business logic failed")
    assert len(await rows_for(admin, target)) == 1
    assert (
        await admin("select count(*) n from public.patients where owner_user_id = :u", {"u": user.user_id})
    )[0]["n"] == 0


async def test_helper_inserted_rows_stay_private(database: Database, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    await insert_case(database, a)
    async with database.user_session(b) as connection:
        assert (await connection.execute(text("select count(*) from public.cases"))).scalar() == 0
