-- Phase 2B / 1 of 8: helper functions, database roles, default-deny privileges.
-- See docs/adr/0004 and docs/adr/0005.

-- Helper functions live in a schema that is never exposed to clients.
create schema if not exists app_private;
revoke all on schema app_private from public;

-- ── Roles ────────────────────────────────────────────────────────────────────────────────────────
-- The backend uses TWO unrelated login roles, so user-scoped code can never reach the system path:
--
--   app_backend  user path. LOGIN, NOINHERIT, no privileges of its own. A query only gets privileges
--                inside a user session (SET LOCAL ROLE authenticated + the verified claims). A query run
--                without a context fails with "permission denied" (fail closed).
--   app_system   system path (this phase: INSERT on audit_logs only). Its OWN login role and its own
--                connection pool. It is NOT a member of anything and NOTHING is a member of it, so a
--                session running as app_backend cannot SET ROLE to it. It is not service_role and has
--                no BYPASSRLS.
--
-- No passwords are stored in the repository: set them out of band (see backend/README.md).
do $$
begin
  if not exists (select from pg_roles where rolname = 'app_backend') then
    create role app_backend login noinherit nosuperuser nobypassrls nocreatedb nocreaterole;
  end if;
  if not exists (select from pg_roles where rolname = 'app_system') then
    create role app_system login noinherit nosuperuser nobypassrls nocreatedb nocreaterole;
  end if;
end $$;

-- app_backend may SET ROLE authenticated (the user context). Deliberately NO grant of app_system.
grant authenticated to app_backend;

-- ── Default-deny privileges ─────────────────────────────────────────────────────────────────────
-- New tables, sequences and functions start with NO grants for client roles; each migration grants
-- exactly what it needs.
alter default privileges in schema public revoke all on tables from anon, authenticated, service_role;
alter default privileges in schema public revoke all on sequences from anon, authenticated, service_role;
alter default privileges in schema public revoke all on functions from anon, authenticated, service_role;
revoke create on schema public from public, anon, authenticated;
grant usage on schema public to authenticated, app_system;

-- ── Trigger helpers ─────────────────────────────────────────────────────────────────────────────
create or replace function app_private.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- The column named in the trigger argument (the owner column) can never change.
create or replace function app_private.enforce_immutable_column() returns trigger
language plpgsql as $$
begin
  if (to_jsonb(new) ->> tg_argv[0]) is distinct from (to_jsonb(old) ->> tg_argv[0]) then
    raise exception '% is immutable', tg_argv[0] using errcode = '42501';
  end if;
  return new;
end $$;
