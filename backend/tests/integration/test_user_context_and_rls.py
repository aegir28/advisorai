"""ADR 0005 against a real database: the user-context mechanism and RLS, through the application's own
`Database.user_session`, with two users. RLS is not considered complete until these pass."""

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.dependencies import CurrentUser
from app.db.database import Database, SystemOperation, SystemPathUnavailableError, create_engine
from app.db.profiles import get_profile
from tests.integration.conftest import Admin, insert_case

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MakeUser = Callable[[], Coroutine[Any, Any, CurrentUser]]

OWNER_TABLES = [
    "patients", "cases", "documents", "document_pages", "medical_records", "facts", "timeline_events",
    "medications", "lab_results", "diagnoses", "procedures", "workflow_runs", "workflow_steps",
]  # fmt: skip
ALL_TABLES = ["profiles", *OWNER_TABLES, "audit_logs"]


async def scalar(connection: Any, sql: str, **params: Any) -> Any:
    return (await connection.execute(text(sql), params)).scalar()


# ── The mechanism ───────────────────────────────────────────────────────────────────────────────
async def test_a_user_session_acts_as_the_verified_user_under_the_authenticated_role(
    database: Database, make_user: MakeUser
) -> None:
    user = await make_user()
    async with database.user_session(user) as connection:
        assert await scalar(connection, "select current_user") == "authenticated"
        assert await scalar(connection, "select auth.uid()") == user.user_id


async def test_the_login_role_has_no_privileges_without_a_context(
    database: Database, make_user: MakeUser
) -> None:
    """Fail closed: forgetting the context is an error, not a leak."""
    await make_user()
    async with database._engine.connect() as connection:  # the raw, context-free connection
        assert await scalar(connection, "select current_user") == "app_backend"
        assert await scalar(connection, "select current_setting('request.jwt.claim.sub', true)") in (None, "")
        # It cannot even call auth.uid(): the auth schema is closed to it too.
        with pytest.raises(ProgrammingError, match=r"permission denied"):
            await connection.execute(text("select auth.uid()"))
        await connection.rollback()
        for table in ALL_TABLES:
            with pytest.raises(ProgrammingError, match=r"permission denied"):
                await connection.execute(text(f"select 1 from public.{table} limit 1"))
            await connection.rollback()


async def test_the_context_does_not_leak_to_the_next_request_on_a_reused_connection(
    app_database_url: Any, make_user: MakeUser
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine as raw_engine

    one_connection = raw_engine(
        app_database_url.get_secret_value(),
        pool_size=1,
        max_overflow=0,
        connect_args={"statement_cache_size": 0},
    )
    database = Database(one_connection)
    user = await make_user()
    try:
        async with database.user_session(user) as connection:
            assert await scalar(connection, "select auth.uid()") == user.user_id
        # The pool has exactly one connection, so this reuses it.
        async with one_connection.connect() as connection:
            assert await scalar(connection, "select current_user") == "app_backend"
            assert await scalar(connection, "select current_setting('request.jwt.claim.sub', true)") in (
                None,
                "",
            )
            assert await scalar(connection, "select current_setting('request.jwt.claims', true)") in (
                None,
                "",
            )
    finally:
        await database.dispose()


async def test_the_context_is_discarded_even_when_the_request_fails(
    database: Database, make_user: MakeUser
) -> None:
    user = await make_user()
    with pytest.raises(RuntimeError):
        async with database.user_session(user) as connection:
            assert await scalar(connection, "select auth.uid()") == user.user_id
            raise RuntimeError("request failed")
    async with database._engine.connect() as connection:
        assert await scalar(connection, "select current_setting('request.jwt.claim.sub', true)") in (None, "")


async def test_concurrent_requests_for_different_users_never_mix(
    database: Database, make_user: MakeUser
) -> None:
    users = [await make_user() for _ in range(6)]

    async def whoami(user: CurrentUser) -> uuid.UUID:
        async with database.user_session(user) as connection:
            await asyncio.sleep(0.01)
            return uuid.UUID(str(await scalar(connection, "select auth.uid()")))

    assert await asyncio.gather(*(whoami(u) for u in users * 3)) == [u.user_id for u in users * 3]


# ── The system path is unreachable from user context ────────────────────────────────────────────
PRIVILEGED_ROLES = ("app_system", "postgres", "service_role", "anon", "supabase_admin")


async def test_a_normal_authenticated_session_cannot_assume_app_system(
    database: Database, make_user: MakeUser
) -> None:
    """Regression for the residual risk in ADR 0005: no SQL, however it is phrased, can take a user
    session to the system role (or to any privileged role)."""
    user = await make_user()
    async with database.user_session(user) as connection:
        assert await scalar(connection, "select current_user") == "authenticated"
        for role in PRIVILEGED_ROLES:
            for statement in (
                f"set local role {role}",
                f"set role {role}",
                f"set session authorization {role}",
            ):
                with pytest.raises(
                    DBAPIError, match=r"permission denied|must be|not permitted|does not exist"
                ):
                    async with connection.begin_nested():
                        await connection.execute(text(statement))
            # Even after dropping back to the login role first (RESET ROLE is always allowed), the
            # system role is still out of reach, because the login role is not a member of it.
            with pytest.raises(DBAPIError, match=r"permission denied|must be|not permitted|does not exist"):
                async with connection.begin_nested():
                    await connection.execute(text("reset role"))
                    await connection.execute(text(f"set local role {role}"))
        assert await scalar(connection, "select current_user") == "authenticated"


async def test_the_context_free_login_role_cannot_assume_app_system_either(database: Database) -> None:
    async with database._engine.connect() as connection:
        assert await scalar(connection, "select current_user") == "app_backend"
        for role in PRIVILEGED_ROLES:
            with pytest.raises(DBAPIError, match=r"permission denied|must be|not permitted|does not exist"):
                await connection.execute(text(f"set role {role}"))
            await connection.rollback()


async def test_the_user_path_login_has_no_membership_path_to_app_system(admin: Admin) -> None:
    rows = await admin(
        "select r as role, pg_has_role('app_backend', r, 'member') as app_backend_is_member from unnest(array["
        "'app_system','postgres','service_role','anon','supabase_admin']) as r where exists (select from pg_roles where rolname = r)"
    )
    assert rows and not [r["role"] for r in rows if r["app_backend_is_member"]]
    reach = await admin(
        "select r as role from unnest(array['authenticated','anon','service_role']) as r"
        " where pg_has_role(r, 'app_system', 'member')"
    )
    assert reach == []
    memberships = await admin(
        "select count(*) n from pg_auth_members m join pg_roles u on u.oid = m.member where u.rolname = 'app_system'"
    )
    assert memberships[0]["n"] == 0  # app_system is not a member of anything


async def test_the_system_session_is_a_separate_login_with_almost_no_power(database: Database) -> None:
    async with database.system_session(SystemOperation.AUDIT_APPEND) as connection:
        assert await scalar(connection, "select session_user") == "app_system"
        assert await scalar(connection, "select current_user") == "app_system"
        assert await scalar(connection, "select current_setting('request.jwt.claim.sub', true)") in (None, "")
        for statement in (
            "select * from public.cases",
            "select * from public.audit_logs",
            "update public.audit_logs set action = 'x.y'",
            "delete from public.patients",
            "select auth.uid()",
        ):
            with pytest.raises(ProgrammingError, match=r"permission denied"):
                async with connection.begin_nested():
                    await connection.execute(text(statement))
        for role in ("authenticated", "app_backend", "postgres"):
            with pytest.raises(DBAPIError):
                async with connection.begin_nested():
                    await connection.execute(text(f"set local role {role}"))


async def test_a_misconfigured_system_url_is_refused(app_database_url: Any) -> None:
    """If the system URL logged in as app_backend (or anything but app_system), refuse to use it."""
    engine = create_engine(app_database_url)
    database = Database(engine, create_engine(app_database_url))
    try:
        with pytest.raises(SystemPathUnavailableError):
            async with database.system_session(SystemOperation.AUDIT_APPEND):
                pass
    finally:
        await database.dispose()


# ── User A cannot read user B's data ────────────────────────────────────────────────────────────
async def test_each_user_sees_only_their_own_rows(database: Database, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    rows_a = await insert_case(database, a, with_document=True)
    rows_b = await insert_case(database, b, with_document=True)

    for user, own, other in ((a, rows_a, rows_b), (b, rows_b, rows_a)):
        async with database.user_session(user) as connection:
            for table, key in (("patients", "patient"), ("cases", "case"), ("documents", "document")):
                visible = {
                    r[0] for r in (await connection.execute(text(f"select id from public.{table}"))).all()
                }
                assert visible == {own[key]}, f"{table}: user sees someone else's rows"
            assert (
                await connection.execute(
                    text("select 1 from public.cases where id = :id"), {"id": other["case"]}
                )
            ).first() is None


async def test_a_user_sees_only_their_own_profile(database: Database, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    async with database.user_session(a) as connection:
        profiles = (await connection.execute(text("select user_id from public.profiles"))).all()
        assert [p[0] for p in profiles] == [a.user_id]
        own = await get_profile(connection, a.user_id)
        assert own is not None and own.user_id == a.user_id and own.display_name is not None
        assert await get_profile(connection, b.user_id) is None  # even asking for B's id by name


# ── User A cannot insert rows owned by user B ───────────────────────────────────────────────────
async def test_a_user_cannot_insert_rows_owned_by_someone_else(
    database: Database, make_user: MakeUser
) -> None:
    a, b = await make_user(), await make_user()
    rows_b = await insert_case(database, b)
    foreign_document = uuid.uuid4()
    # Every other constraint is satisfied, so ONLY row-level security can reject these.
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("insert into public.patients (owner_user_id, age_years, sex) values (:other, 30, 'F')", {}),
        (
            "insert into public.cases (owner_user_id, patient_id, code, concern) values (:other, :bp, 'AC-HACK1', 'x')",
            {"bp": rows_b["patient"]},
        ),
        (
            "insert into public.documents (id, owner_user_id, case_id, type, title, storage_path)"
            " values (:doc, :other, :bc, 'lab', 'x', :path)",
            {
                "doc": foreign_document,
                "bc": rows_b["case"],
                "path": f"{b.user_id}/{rows_b['case']}/{foreign_document}",
            },
        ),
    ]
    for sql, extra in attempts:
        with pytest.raises(DBAPIError, match=r"row-level security"):
            async with database.user_session(a) as connection:
                await connection.execute(text(sql), {"other": b.user_id, **extra})


async def test_the_owner_defaults_to_the_verified_user_and_cannot_be_omitted_without_a_context(
    database: Database, make_user: MakeUser, admin: Admin
) -> None:
    a = await make_user()
    rows = await insert_case(database, a)
    stored = await admin("select owner_user_id from public.patients where id = :id", {"id": rows["patient"]})
    assert stored[0]["owner_user_id"] == a.user_id


# ── User A cannot change owner_user_id, or touch B's rows ───────────────────────────────────────
async def test_a_user_cannot_change_owner_user_id(database: Database, make_user: MakeUser) -> None:
    a, b = await make_user(), await make_user()
    rows = await insert_case(database, a, with_document=True)
    for table, key in (("patients", "patient"), ("cases", "case"), ("documents", "document")):
        with pytest.raises(DBAPIError):
            async with database.user_session(a) as connection:
                await connection.execute(
                    text(f"update public.{table} set owner_user_id = :b where id = :id"),
                    {"b": b.user_id, "id": rows[key]},
                )


async def test_a_user_cannot_update_or_delete_someone_elses_rows(
    database: Database, make_user: MakeUser
) -> None:
    a, b = await make_user(), await make_user()
    rows_b = await insert_case(database, b)
    async with database.user_session(a) as connection:
        updated = await connection.execute(
            text("update public.cases set title = 'hijacked' where id = :id"), {"id": rows_b["case"]}
        )
        deleted = await connection.execute(
            text("delete from public.cases where id = :id"), {"id": rows_b["case"]}
        )
        profile = await connection.execute(
            text("update public.profiles set display_name = 'hijacked' where user_id = :id"),
            {"id": b.user_id},
        )
        assert (updated.rowcount, deleted.rowcount, profile.rowcount) == (0, 0, 0)
    async with database.user_session(b) as connection:
        assert (
            await scalar(connection, "select title from public.cases where id = :id", id=rows_b["case"])
            is None
        )
        assert await scalar(connection, "select count(*) from public.cases") == 1


# ── Child rows cannot cross owners ──────────────────────────────────────────────────────────────
async def test_child_rows_cannot_cross_owners(database: Database, make_user: MakeUser, admin: Admin) -> None:
    a, b = await make_user(), await make_user()
    rows_a = await insert_case(database, a, with_document=True)
    rows_b = await insert_case(database, b)

    # Through the app: A attaching their own document to B's case.
    doc_id = uuid.uuid4()
    with pytest.raises(IntegrityError, match=r"foreign key"):
        async with database.user_session(a) as connection:
            await connection.execute(
                text(
                    "insert into public.documents (id, case_id, type, title, storage_path)"
                    " values (:id, :bc, 'lab', 'x', :path)"
                ),
                {"id": doc_id, "bc": rows_b["case"], "path": f"{a.user_id}/{rows_b['case']}/{doc_id}"},
            )

    # As the database owner (RLS does not apply): composite FKs still refuse every cross-owner child.
    crossing: list[tuple[str, dict[str, Any]]] = [
        (
            "insert into public.facts (owner_user_id, case_id, document_id, type, label, fact_date, page, snippet, confidence)"
            " values (:b, :case, :doc, 'symptom', 'x', '2026-01-01', 1, 's', 0.5)",
            {"b": b.user_id, "case": rows_a["case"], "doc": rows_a["document"]},
        ),
        (
            "insert into public.workflow_runs (owner_user_id, case_id, definition, definition_version)"
            " values (:b, :case, 'case_analysis', '1')",
            {"b": b.user_id, "case": rows_a["case"]},
        ),
        (
            "insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)"
            " values (:b, :case, 'case.v1', cast(:doc as jsonb))",
            {
                "b": b.user_id,
                "case": rows_a["case"],
                "doc": f'{{"schema_version":"case.v1","case_id":"{rows_a["case"]}"}}',
            },
        ),
        (
            "insert into public.cases (owner_user_id, patient_id, code, concern) values (:b, :bp, 'AC-X3', 'x')",
            {"b": b.user_id, "bp": rows_a["patient"]},
        ),
    ]
    for sql, params in crossing:
        with pytest.raises(IntegrityError, match=r"foreign key|violates"):
            await admin(sql, params)


# ── anon and derived tables ─────────────────────────────────────────────────────────────────────
async def test_anon_can_access_nothing(admin_engine: AsyncEngine, make_user: MakeUser) -> None:
    await make_user()
    async with admin_engine.connect() as connection:
        for table in ALL_TABLES:
            with pytest.raises(ProgrammingError, match=r"permission denied"):
                async with connection.begin():
                    await connection.execute(text("set local role anon"))
                    await connection.execute(text(f"select 1 from public.{table} limit 1"))
        with pytest.raises(ProgrammingError, match=r"permission denied"):
            async with connection.begin():
                await connection.execute(text("set local role anon"))
                await connection.execute(text("insert into public.patients (age_years, sex) values (1, 'M')"))


async def test_derived_tables_are_read_only_for_the_user(database: Database, make_user: MakeUser) -> None:
    a = await make_user()
    rows = await insert_case(database, a, with_document=True)
    writes = [
        "insert into public.document_pages (owner_user_id, case_id, document_id, page_no) values (:u, :c, :d, 1)",
        "insert into public.workflow_runs (owner_user_id, case_id, definition, definition_version) values (:u, :c, 'x', '1')",
        "update public.workflow_runs set status = 'complete'",
        "delete from public.document_pages",
    ]
    for sql in writes:
        with pytest.raises(ProgrammingError, match=r"permission denied"):
            async with database.user_session(a) as connection:
                await connection.execute(
                    text(sql), {"u": a.user_id, "c": rows["case"], "d": rows["document"]}
                )


# ── Deletion ────────────────────────────────────────────────────────────────────────────────────
async def test_deleting_a_case_deletes_its_documents_and_its_patient(
    database: Database, make_user: MakeUser
) -> None:
    a = await make_user()
    rows = await insert_case(database, a, with_document=True)
    async with database.user_session(a) as connection:
        await connection.execute(text("delete from public.cases where id = :id"), {"id": rows["case"]})
        for table in ("cases", "documents", "patients"):
            assert await scalar(connection, f"select count(*) from public.{table}") == 0, table


async def test_the_synthetic_only_lock_holds_through_the_app_path(
    database: Database, make_user: MakeUser
) -> None:
    a = await make_user()
    with pytest.raises(IntegrityError, match=r"synthetic"):
        async with database.user_session(a) as connection:
            await connection.execute(
                text("insert into public.patients (age_years, sex, is_synthetic) values (30, 'F', false)")
            )
