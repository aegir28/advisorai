# ADR 0005: Request-scoped database user context (direct Postgres + RLS)

- Status: accepted
- Date: 2026-10-02
- Scope: `backend/app/db/`, `backend/app/auth/`, `supabase/migrations/`

## Problem

FastAPI connects straight to Postgres. A Supabase JWT only becomes `auth.uid()` inside Postgres when
PostgREST (or another Supabase service) sets the request context for it. A direct connection gets no
such context: `auth.uid()` is `NULL`, so RLS policies written as `owner_user_id = auth.uid()` would
silently match nothing, or, worse, the backend would be tempted to connect as a role that bypasses RLS.

## Decision

The backend builds the context itself, explicitly, per request, and only from a **verified** token.

1. **Verify first.** `get_current_user` verifies the Bearer JWT (JWKS, signature, expiry, issuer,
   `aud = authenticated`, `sub` is a UUID, `role = authenticated`, not an anonymous session). Failure is a
   `401 UNAUTHENTICATED` envelope. Only the verifier creates a `CurrentUser`.
2. **Fail-closed connection role.** The user path logs in as `app_backend`: `LOGIN NOINHERIT NOSUPERUSER
   NOBYPASSRLS`, no table privileges, `SET`-only membership in `authenticated` and **nothing else**. A query
   run without a context has no privileges and fails with `permission denied`.
3. **User-scoped transaction.** `Database.user_session(user)` opens a transaction and runs, with
   `is_local = true` (that is, `SET LOCAL`):

   ```sql
   SELECT set_config('role', 'authenticated', true),
          set_config('request.jwt.claims', :claims_json, true),
          set_config('request.jwt.claim.sub', :sub, true),
          set_config('request.jwt.claim.role', 'authenticated', true);
   ```

   `claims_json` and `sub` are built server-side from the verified token and passed as bind parameters;
   the role names are constants. `auth.uid()` then returns the verified user and RLS applies.
4. **Reset by construction.** Every setting is transaction-local, so commit or rollback restores
   `app_backend` with no privileges and no `auth.uid()`. Nothing leaks to the next request on a pooled
   connection (tested with a pool of one connection).
5. **The client never picks the user.** No route accepts a user or owner ID, and no header is trusted.
   The only input to the context is the verified `sub`. A test inspects every route in OpenAPI to keep
   it that way; another sends spoofed identity headers.
6. **System path: a separate login, not a role switch.** `Database.system_session(operation)` connects with
   its **own login role, `app_system`, on its own connection pool** (`ADVISORAI_SYSTEM_DATABASE_URL`, which
   must differ from `ADVISORAI_DATABASE_URL`). There is **no `SET ROLE` between the two paths**:
   `app_backend` is not a member of `app_system`, `app_system` is not a member of anything, and `anon`,
   `authenticated` and `service_role` cannot reach it either. A session running as `app_backend` therefore
   cannot become `app_system`, whatever SQL it runs, including after `RESET ROLE`. The system session also
   checks that it really is logged in as `app_system` and refuses to run otherwise, and with no system
   connection configured it fails closed instead of borrowing the user connection. It accepts only an
   enumerated operation. In this phase the single operation is `audit.append`, and `app_system` holds
   `INSERT` on `audit_logs` and nothing else. It is not `service_role` and has no `BYPASSRLS`. Each new system
   operation must be added to the enum, to the role's grants and to this ADR.
7. **Defence in depth.** RLS policies use `(select auth.uid())`. `owner_user_id` defaults to
   `auth.uid()`, is checked by `WITH CHECK`, and is immutable by trigger.
8. **Pooler-safe.** `statement_cache_size = 0` for asyncpg, and everything is transaction-local, so
   transaction-mode poolers (Supavisor) work.

## What the tests prove

User A cannot read user B's rows; cannot insert a row owned by B; cannot change `owner_user_id`; child
rows cannot cross owners (including as a superuser, because composite FKs are not RLS); `anon` can read
nothing; a request with no context can read nothing; and the context does not survive the transaction.
The same assertions run at SQL level (pgTAP) and through the application's own `user_session`.

## Threats considered

| Threat | Mitigation |
| --- | --- |
| Forged or expired token | JWKS verification, algorithm allow-list, `alg: none` and HS* rejected |
| Client sends a user ID | No such input exists; tested |
| Code path forgets the context | `app_backend` has no privileges: fail-closed |
| Context leaks across pooled connections | `SET LOCAL` only; tested with pool size 1 |
| Over-privileged system access | Narrow `app_system` on its own login and pool, enumerated operations, no `BYPASSRLS` |
| User session reaching the system role | Impossible by role membership: no `SET ROLE` path; asserted in migration 7, pgTAP and integration tests |
| Superuser connection used by mistake | The backend never uses one; the role has no `SUPERUSER` |

## Residual risk found by the integration tests, and its fix

The first implementation made `app_system` a role that `app_backend` could `SET ROLE` to. Postgres checks
`SET ROLE` against the **login** role, and `app_backend` was a member of `app_system`, so SQL running inside a
user session could still `SET LOCAL ROLE app_system`. The damage was bounded (`app_system` could only append
audit rows) and no route runs client-supplied SQL, but the system path was guarded only by application code.

**Fixed:** `app_system` is now its own login role with its own pool (step 6). The membership grant is gone.
Three layers keep it that way:

1. **Migration 7 fails the migration run** if `app_backend`, `authenticated`, `anon` or `service_role` can
   reach `app_system`, if `app_system` is a member of any role, or if `app_backend` can become any privileged
   role.
2. **pgTAP** asserts the same, and that `SET ROLE app_system` fails from an authenticated session, from
   `app_backend` and from `anon`, and that `app_system` cannot become `authenticated` or `app_backend`.
3. **Integration tests** try `SET LOCAL ROLE`, `SET ROLE` and `SET SESSION AUTHORIZATION` to `app_system`,
   `postgres`, `service_role`, `anon` and `supabase_admin` from a real user session (and after `RESET ROLE`,
   and from the context-free login) and require every one to be refused.

What remains, and is true of every design that sets claims with `SET LOCAL`: SQL running in a user session can
still change its own claims, for example set `request.jwt.claim.sub` to another user's ID, because `set_config`
is allowed to any role. The mitigation is the same as PostgREST's: no statement is built from client input,
every user-derived value is a bind parameter, and routes may not run client-supplied SQL. Any future feature
that executes dynamic SQL needs its own review.

## Rejected alternatives

- **PostgREST as the data layer**: not approved; the Data API is disabled.
- **Connect as `postgres` or `service_role` and filter by user in SQL**: one forgotten `WHERE` leaks
  every patient's data.
- **Session-level `SET`**: persists on a pooled connection.
