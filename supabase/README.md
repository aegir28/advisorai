# supabase

Local Supabase project, versioned SQL and the database tests. **Phase 2B.** Everything here is
synthetic: no real patient data (ADR 0004).

```
config.toml                  local stack (Data API, realtime, analytics, ... are OFF; Google OAuth is Phase 2C)
migrations/*.sql             the single source of truth for the schema, RLS and storage policies (no Alembic)
seed.sql                     fictional demo user, 3 cases, documents, facts, one workflow run (no credentials)
tests/database/*.test.sql    pgTAP: schema/privacy, RLS isolation (two users, anon, system), integrity
```

## Migrations (forward-only, applied in order)

| # | File | What |
| --- | --- | --- |
| 1 | `helpers_and_roles` | `app_private` helpers, two unrelated login roles `app_backend` (user path) / `app_system` (system path), default-deny privileges |
| 2 | `identity` | `profiles` (the only name), `patients` (age and sex only), new-user trigger |
| 3 | `cases_documents` | `cases`, `documents`, `document_pages`, composite owner FKs, RLS |
| 4 | `workflow` | `workflow_runs` (also the job queue), `workflow_steps` |
| 5 | `clinical_records` | `medical_records` (`case.v1` snapshot), `facts`, timeline, medications, labs, diagnoses, procedures |
| 6 | `audit` | append-only `audit_logs`, no foreign keys |
| 7 | `security_assertions` | changes nothing; **fails the migration** if any RLS/grant/role invariant is false |
| 8 | `storage` | private `case-documents` bucket + restrictive policy (no direct client access) |

Rules every migration follows: a table never exists without RLS (enabled **and** forced) and its policies in
the same file; every patient-owned table has `owner_user_id` and references its parent with a composite
`(parent_id, case_id, owner_user_id)` foreign key; clients get only the grants they need.

## Run it locally

Needs Docker and the Supabase CLI.

```bash
supabase start -x studio,imgproxy      # from the repository root
supabase db reset                      # clean database: migrations, then seed.sql
supabase test db                       # pgTAP / RLS tests
supabase db lint --level error
```

Then the backend integration tests (from `backend/`):

```bash
eval "$(supabase status -o env)"
export ADVISORAI_TEST_ADMIN_DATABASE_URL="${DB_URL/postgresql:\/\//postgresql+asyncpg://}"
export ADVISORAI_TEST_SUPABASE_URL="$API_URL" ADVISORAI_TEST_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
uv run --no-sync pytest tests/integration -q
```

The integration tests set random throw-away passwords on the `app_backend` and `app_system` roles
themselves. To run the backend app against this database, set them yourself (no password is stored in the
repository). They are two separate logins on purpose: the user path (`app_backend`) can never switch to the
system path (`app_system`).

```sql
alter role app_backend with password '<choose one>';
alter role app_system  with password '<choose a different one>';
```

## Without Docker: the native substitute

If Docker or the Supabase images are unavailable, `supabase/native/run.sh up|pgtap|reset|down` builds a
throw-away PostgreSQL 16 cluster with a **stub** of the Supabase `auth`/`storage` schemas and roles, applies the
real migrations and seed, and runs the real pgTAP files. It prints the `ADVISORAI_TEST_ADMIN_DATABASE_URL` for the
backend integration tests (the two Storage API tests still skip). It is **not** a replacement for the stack above
and a green native run is never reported as one. It needs `postgresql-16` and `postgresql-16-pgtap`.

## Google sign-in (Supabase Auth)

`config.toml` has an `[auth.external.google]` block, **disabled** so `supabase start` works without credentials.
To use real Google sign-in locally: create a Google OAuth client (authorised redirect URI
`<API_EXTERNAL_URL>/auth/v1/callback`), export `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID` and
`SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET` in the shell that runs `supabase start`, and set `enabled = true`. These
credentials belong to Supabase Auth only: never the frontend, the backend or the repository
([ADR 0009](../docs/adr/0009-google-auth-and-frontend-http-integration.md)).

## Adding a migration

`supabase migration new <name>`, write forward-only SQL, include RLS and policies for any new table, add
pgTAP assertions, and run the three commands above. Never edit an applied migration.
