"""Integration tests need the local Supabase stack (`supabase start`) and are skipped without it.

    ADVISORAI_TEST_ADMIN_DATABASE_URL   postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
    ADVISORAI_TEST_SUPABASE_URL         http://127.0.0.1:54321            (storage tests only)
    ADVISORAI_TEST_SERVICE_ROLE_KEY     from `supabase status -o env`      (storage tests only)

The admin URL is used ONLY to create fixtures and to set a random, throw-away password on the
`app_backend` and `app_system` roles. Everything the application does goes through those two logins, exactly as in
production, so these tests exercise the real fail-closed role and the real user-context mechanism.
"""

import os
import secrets
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, Protocol

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.auth.dependencies import CurrentUser
from app.db.database import Database, create_engine

ENV_ADMIN = "ADVISORAI_TEST_ADMIN_DATABASE_URL"
ENV_SUPABASE_URL = "ADVISORAI_TEST_SUPABASE_URL"
ENV_SERVICE_KEY = "ADVISORAI_TEST_SERVICE_ROLE_KEY"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(ENV_ADMIN):
        return
    skip = pytest.mark.skip(
        reason=f"needs the local Supabase stack: set {ENV_ADMIN} (see tests/integration/conftest.py)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ[ENV_ADMIN])
    yield engine
    await engine.dispose()


async def login_url(admin_engine: AsyncEngine, role: str) -> SecretStr:
    """A login URL for `role` with a random password that exists only for this test."""
    password = secrets.token_hex(16)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f"alter role {role} with password '{password}'"))
    url = make_url(os.environ[ENV_ADMIN]).set(username=role, password=password)
    return SecretStr(url.render_as_string(hide_password=False))


@pytest.fixture
async def app_database_url(admin_engine: AsyncEngine) -> SecretStr:
    """Login URL for the USER path role, `app_backend`."""
    return await login_url(admin_engine, "app_backend")


@pytest.fixture
async def system_database_url(admin_engine: AsyncEngine) -> SecretStr:
    """Login URL for the SYSTEM path role, `app_system` (a separate login, a separate pool)."""
    return await login_url(admin_engine, "app_system")


@pytest.fixture
async def database(app_database_url: SecretStr, system_database_url: SecretStr) -> AsyncIterator[Database]:
    db = Database(create_engine(app_database_url), create_engine(system_database_url))
    yield db
    await db.dispose()


class Admin(Protocol):
    """Run SQL as the database owner; `params` is optional. Returns rows as dicts."""

    async def __call__(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


@pytest.fixture
async def admin(admin_engine: AsyncEngine) -> Admin:
    """Run SQL as the database owner (fixtures and inspection only). Returns rows as dicts."""

    async def run(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with admin_engine.begin() as connection:
            result = await connection.execute(text(sql), params or {})
            return [dict(row) for row in result.mappings()] if result.returns_rows else []

    return run


@pytest.fixture
async def make_user(admin: Admin) -> AsyncIterator[Callable[[], Coroutine[Any, Any, CurrentUser]]]:
    """Creates auth users (the new-user trigger creates their profiles) and deletes them afterwards."""
    created: list[uuid.UUID] = []

    async def create() -> CurrentUser:
        user_id = uuid.uuid4()
        await admin(
            "insert into auth.users (id, aud, role, email, raw_user_meta_data)"
            " values (:id, 'authenticated', 'authenticated', :email, cast(:meta as jsonb))",
            {
                "id": user_id,
                "email": f"{user_id.hex[:12]}@advisorai.test",
                "meta": f'{{"full_name": "Test {user_id.hex[:6]}"}}',
            },
        )
        created.append(user_id)
        return CurrentUser(user_id)

    yield create
    for user_id in created:
        await admin("delete from auth.users where id = :id", {"id": user_id})


async def insert_case(
    database: Database, user: CurrentUser, *, with_document: bool = False
) -> dict[str, uuid.UUID]:
    """Create a patient, a case and optionally a ready document AS the user, through the app path."""
    patient_id, case_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with database.user_session(user) as connection:
        await connection.execute(
            text("insert into public.patients (id, age_years, sex) values (:id, 40, 'F')"), {"id": patient_id}
        )
        await connection.execute(
            text(
                "insert into public.cases (id, patient_id, code, concern)"
                " values (:id, :patient, :code, 'synthetic concern')"
            ),
            {"id": case_id, "patient": patient_id, "code": f"AC-{case_id.hex[:6].upper()}"},
        )
        if with_document:
            await connection.execute(
                text(
                    "insert into public.documents (id, case_id, type, title, status, storage_path)"
                    " values (:id, :case, 'lab', 'synthetic.pdf', 'ready', :path)"
                ),
                {"id": document_id, "case": case_id, "path": f"{user.user_id}/{case_id}/{document_id}"},
            )
    return {"patient": patient_id, "case": case_id, "document": document_id}
