"""Direct Postgres access with an explicit, request-scoped user context (ADR 0005).

Two completely separate paths, each with its OWN login role and connection pool:

* USER path, login `app_backend` (no privileges of its own, fail closed). `user_session(user)` opens one
  transaction, becomes `authenticated` and sets the claims that make `auth.uid()` return the VERIFIED
  user. RLS applies to everything run inside it. Every setting is `SET LOCAL`, so commit or rollback
  restores the unprivileged login role and nothing leaks to the next request on a pooled connection.
* SYSTEM path, login `app_system` (a narrow role: INSERT into `audit_logs`, and the workflow run/step tables).
  `system_session(operation)` connects as that role directly. There is NO `SET ROLE` between the two
  paths: `app_backend` is not a member of `app_system`, so nothing running on the user path can become
  it, whatever SQL it runs.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.auth.dependencies import CurrentUser

# Constants only: role names are never taken from input. User-derived values are bind parameters.
_SET_USER_CONTEXT = text(
    "select set_config('role', 'authenticated', true),"
    " set_config('request.jwt.claims', :claims, true),"
    " set_config('request.jwt.claim.sub', :sub, true),"
    " set_config('request.jwt.claim.role', 'authenticated', true)"
)

SYSTEM_ROLE = "app_system"


class SystemPathUnavailableError(Exception):
    """No system connection is configured, or it is not logged in as `app_system`."""


class SystemOperation(StrEnum):
    """The only system operations. A new one needs a grant on `app_system` and an update to ADR 0005."""

    AUDIT_APPEND = "audit.append"
    # Phase 2D: the job queue. `app_system` holds SELECT/INSERT/UPDATE(some columns) on workflow_runs and
    # workflow_steps (migration 20261005000001) and nothing else beyond the audit INSERT.
    WORKFLOW_ENQUEUE = "workflow.enqueue"
    WORKFLOW_RUN = "workflow.run"
    # AI usage ledger (migration 20261006000001): `app_system` gets INSERT on model_usage, nothing else new.
    AI_USAGE_RECORD = "ai.usage_record"


def create_engine(database_url: SecretStr) -> AsyncEngine:
    return create_async_engine(
        database_url.get_secret_value(),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        # Transaction-mode poolers (Supavisor) cannot keep prepared statements across transactions.
        connect_args={
            "statement_cache_size": 0,
            "server_settings": {"application_name": "advisorai-backend"},
        },
    )


class Database:
    def __init__(self, engine: AsyncEngine, system_engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._system_engine = system_engine

    @asynccontextmanager
    async def user_session(self, user: CurrentUser) -> AsyncIterator[AsyncConnection]:
        """One transaction acting as `user`. Anything run on the yielded connection is under RLS."""
        subject = str(user.user_id)
        claims = json.dumps({"sub": subject, "role": "authenticated"}, separators=(",", ":"))
        async with self._engine.connect() as connection, connection.begin():
            await connection.execute(_SET_USER_CONTEXT, {"claims": claims, "sub": subject})
            yield connection

    @asynccontextmanager
    async def system_session(self, operation: SystemOperation) -> AsyncIterator[AsyncConnection]:
        """One transaction on the SYSTEM connection (login `app_system`), for an approved operation."""
        if not isinstance(operation, SystemOperation):
            raise TypeError("system_session requires a SystemOperation")
        if self._system_engine is None:
            raise SystemPathUnavailableError("the system database connection is not configured")
        async with self._system_engine.connect() as connection, connection.begin():
            # Misconfiguration guard: the system URL must really log in as app_system, never as the
            # user-path role or a more powerful one.
            current = (await connection.execute(text("select current_user"))).scalar()
            if current != SYSTEM_ROLE:
                raise SystemPathUnavailableError("the system connection is not logged in as app_system")
            yield connection

    async def ping(self) -> None:
        """Reachability only. Runs as the unprivileged login role: `select 1` needs no privileges."""
        async with self._engine.connect() as connection:
            await connection.execute(text("select 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()
        if self._system_engine is not None:
            await self._system_engine.dispose()
