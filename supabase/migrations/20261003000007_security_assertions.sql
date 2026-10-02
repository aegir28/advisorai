-- Phase 2B / 7 of 8: security assertions.
-- This migration changes nothing. It FAILS the migration run if any invariant the design depends on
-- is not true, so a later migration that adds a table without RLS cannot be applied unnoticed.

do $$
declare
  bad text;
begin
  -- 1. Every table in public has RLS enabled and forced.
  select string_agg(c.relname, ', ') into bad
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind in ('r', 'p')
    and not (c.relrowsecurity and c.relforcerowsecurity);
  if bad is not null then
    raise exception 'RLS is not enabled and forced on: %', bad;
  end if;

  -- 2. Anonymous and service_role have no privileges on any public table.
  select string_agg(distinct table_name || ' (' || grantee || ')', ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and grantee in ('anon', 'service_role', 'PUBLIC');
  if bad is not null then
    raise exception 'unexpected grants on public tables: %', bad;
  end if;

  -- 3. Clients and the system role can never modify or truncate the audit log.
  select string_agg(distinct grantee || ':' || privilege_type, ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and table_name = 'audit_logs'
    and (privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE') or grantee in ('authenticated', 'anon'))
    and grantee not in ('postgres', 'supabase_admin');
  if bad is not null then
    raise exception 'audit_logs has forbidden grants: %', bad;
  end if;

  -- 4. The backend login roles have no privileges of their own and cannot bypass RLS.
  if exists (select from pg_roles where rolname = 'app_backend'
             and (rolsuper or rolbypassrls or rolinherit)) then
    raise exception 'app_backend must be NOSUPERUSER NOBYPASSRLS NOINHERIT';
  end if;
  if exists (select from pg_roles where rolname = 'app_system' and (rolsuper or rolbypassrls)) then
    raise exception 'app_system must be NOSUPERUSER NOBYPASSRLS';
  end if;

  -- 5. The system path is unreachable from user context: nothing running as the user-path login role
  --    (or as authenticated / anon / service_role) may SET ROLE to app_system, and app_system itself is
  --    not a member of anything.
  select string_agg(r, ', ') into bad
  from unnest(array['app_backend', 'authenticated', 'anon', 'service_role']) as r
  where pg_has_role(r, 'app_system', 'member');
  if bad is not null then
    raise exception 'these roles can reach app_system: %', bad;
  end if;
  if exists (select from pg_auth_members m join pg_roles u on u.oid = m.member
              where u.rolname = 'app_system') then
    raise exception 'app_system must not be a member of any role';
  end if;
  -- ... and the user-path login role can only become authenticated, nothing privileged.
  select string_agg(r, ', ') into bad
  from unnest(array['postgres', 'service_role', 'anon', 'supabase_admin', 'app_system']) as r
  where exists (select from pg_roles where rolname = r) and pg_has_role('app_backend', r, 'member');
  if bad is not null then
    raise exception 'app_backend can become: %', bad;
  end if;
end $$;
