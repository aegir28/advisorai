-- Phase 2D: the system path for workflow runs and steps (job queue + step persistence). No AI.
--
-- Until now workflow_runs / workflow_steps were read-only for everyone (ADR 0004). The worker is a system
-- actor, so it gets exactly what it needs, on its OWN login role (app_system, ADR 0005), and nothing a
-- user session can reach:
--
--   workflow_runs   SELECT, INSERT (enqueue), UPDATE of status/progress/failure/warnings/attempts/lock
--                   columns/timestamps. Not owner_user_id, case_id, definition (set once at INSERT).
--   workflow_steps  SELECT, INSERT, UPDATE of status/attempts/note/timestamps/input_hash/error_code.
--
-- app_system has no BYPASSRLS, so each table gets an explicit policy for it. The composite foreign keys still
-- force a run's (case, owner) pair to be one real case of that owner, whoever inserts it.
--
-- Block the user path from this: `authenticated` keeps SELECT only (migration 4); the pgTAP tests assert it.

-- Step idempotency (blueprint p. 46): the hash of a node's inputs; a step that already succeeded with the
-- same hash for the same case is reused instead of re-run. error_code is a short machine code, never text
-- from a document, a prompt or a model.
alter table public.workflow_steps
  add column input_hash text check (input_hash is null or input_hash ~ '^[0-9a-f]{64}$'),
  add column error_code text check (error_code is null or error_code ~ '^[a-z][a-z0-9_]{0,63}$');

create index workflow_steps_reuse_idx on public.workflow_steps (case_id, node, input_hash)
  where status in ('done', 'warning') and input_hash is not null;
-- The worker finds expired leases (a crashed worker) by lock time.
create index workflow_runs_lease_idx on public.workflow_runs (locked_until) where status = 'running';

grant select, insert on public.workflow_runs to app_system;
grant update (status, progress, failure, warnings, attempts, locked_by, locked_until, started_at, finished_at)
  on public.workflow_runs to app_system;
grant select, insert on public.workflow_steps to app_system;
grant update (status, attempts, note, started_at, finished_at, input_hash, error_code)
  on public.workflow_steps to app_system;

create policy workflow_runs_system_select on public.workflow_runs for select to app_system using (true);
create policy workflow_runs_system_insert on public.workflow_runs for insert to app_system with check (true);
create policy workflow_runs_system_update on public.workflow_runs for update to app_system
  using (true) with check (true);
create policy workflow_steps_system_select on public.workflow_steps for select to app_system using (true);
create policy workflow_steps_system_insert on public.workflow_steps for insert to app_system with check (true);
create policy workflow_steps_system_update on public.workflow_steps for update to app_system
  using (true) with check (true);

-- Re-assert the invariants this migration must not break.
do $$
declare
  bad text;
begin
  select string_agg(distinct table_name || ':' || privilege_type, ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and grantee = 'app_system'
    and not (table_name = 'audit_logs' and privilege_type = 'INSERT')
    and not (table_name in ('workflow_runs', 'workflow_steps') and privilege_type in ('SELECT', 'INSERT', 'UPDATE'));
  if bad is not null then
    raise exception 'app_system has unexpected table privileges: %', bad;
  end if;
  if exists (select from information_schema.role_table_grants
              where table_schema = 'public' and table_name in ('workflow_runs', 'workflow_steps')
                and grantee in ('authenticated', 'anon', 'service_role')
                and privilege_type <> 'SELECT') then
    raise exception 'clients may only SELECT workflow_runs / workflow_steps';
  end if;
end $$;
