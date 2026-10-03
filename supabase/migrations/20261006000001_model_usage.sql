-- AI gateway usage ledger (ADR 0011): one row per gateway call, written on the SYSTEM path.
--
-- Records WHAT a call cost and how it went, never what it said: no prompt, no response, no document text, no
-- names. Every value is a counter, a short code or an id. Same ownership model as the rest of the schema:
-- composite foreign keys force (case, owner) and (run, case, owner) to be one real set of the same owner.
--
--   app_system     INSERT only (the gateway). It cannot read, update or delete usage.
--   authenticated  SELECT own rows only (so a person can later see what their case used).
--   everyone else  nothing.
--
-- cost_micro_usd is NULL while a model's price has not been entered in registry/models.yaml: unknown, never invented.
create table public.model_usage (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null,
  case_id        uuid not null,
  run_id         uuid,
  node           text check (node is null or node ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  purpose        text not null check (purpose ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  provider       text not null check (provider ~ '^[a-z][a-z0-9_-]{0,31}$'),
  model          text not null check (char_length(model) between 1 and 80),
  tier           smallint not null check (tier between 1 and 3),
  input_tokens   integer not null check (input_tokens >= 0),
  output_tokens  integer not null check (output_tokens >= 0),
  cost_micro_usd bigint check (cost_micro_usd is null or cost_micro_usd >= 0),
  latency_ms     integer not null check (latency_ms >= 0),
  attempts       smallint not null check (attempts between 1 and 20),
  outcome        text not null check (outcome ~ '^[a-z][a-z0-9_]{0,63}$'),
  request_id     text check (request_id is null or request_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  created_at     timestamptz not null default now(),
  constraint model_usage_case_same_owner foreign key (case_id, owner_user_id)
    references public.cases (id, owner_user_id) on delete cascade,
  -- run_id may be null (a call outside a run); with a run, it must belong to the same case and owner.
  constraint model_usage_run_same_case_owner foreign key (run_id, case_id, owner_user_id)
    references public.workflow_runs (id, case_id, owner_user_id) on delete cascade
);
create index model_usage_owner_idx on public.model_usage (owner_user_id);
create index model_usage_case_idx on public.model_usage (case_id, created_at);
create index model_usage_run_idx on public.model_usage (run_id) where run_id is not null;

alter table public.model_usage enable row level security;
alter table public.model_usage force row level security;
revoke all on public.model_usage from public, anon, authenticated, service_role;

grant select on public.model_usage to authenticated;
create policy model_usage_select_own on public.model_usage for select to authenticated
  using (owner_user_id = (select auth.uid()));

grant insert on public.model_usage to app_system;
create policy model_usage_system_insert on public.model_usage for insert to app_system with check (true);

-- Re-assert the invariants this migration must not break.
do $$
declare
  bad text;
begin
  select string_agg(distinct table_name || ':' || privilege_type, ', ') into bad
  from information_schema.role_table_grants
  where table_schema = 'public' and grantee = 'app_system'
    and not (table_name = 'audit_logs' and privilege_type = 'INSERT')
    and not (table_name = 'model_usage' and privilege_type = 'INSERT')
    and not (table_name in ('workflow_runs', 'workflow_steps') and privilege_type in ('SELECT', 'INSERT', 'UPDATE'));
  if bad is not null then
    raise exception 'app_system has unexpected table privileges: %', bad;
  end if;
  if exists (select from information_schema.role_table_grants
              where table_schema = 'public' and table_name = 'model_usage'
                and grantee in ('anon', 'service_role', 'authenticated') and privilege_type <> 'SELECT') then
    raise exception 'clients may only SELECT model_usage';
  end if;
  if not (select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.model_usage'::regclass) then
    raise exception 'model_usage must have RLS enabled and forced';
  end if;
end $$;
