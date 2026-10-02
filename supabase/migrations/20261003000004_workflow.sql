-- Phase 2B / 4 of 8: workflow job persistence for the later processing pipeline.
-- Tables only: there is no engine, no worker and no API in this phase. workflow_runs doubles as the
-- job queue (status 'queued' + locking columns).

create table public.workflow_runs (
  id                  uuid primary key default gen_random_uuid(),
  owner_user_id       uuid not null default auth.uid(),
  case_id             uuid not null,
  definition          text not null,
  definition_version  text not null,
  -- 'queued' is an INTERNAL state. It is deliberately not mapped onto run.v1's 'running'; the
  -- workflow API contract is defined later (ADR 0004).
  status              text not null default 'queued' check (status in ('queued', 'running', 'complete', 'partial', 'failed')),
  progress            numeric(4, 3) not null default 0 check (progress between 0 and 1),
  failure             jsonb,
  warnings            text[] not null default '{}',
  attempts            integer not null default 0 check (attempts >= 0),
  locked_by           text,
  locked_until        timestamptz,
  started_at          timestamptz,
  finished_at         timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint workflow_runs_failed_explains_itself check (status <> 'failed' or failure is not null),
  constraint workflow_runs_id_case_owner_key unique (id, case_id, owner_user_id),
  constraint workflow_runs_case_same_owner foreign key (case_id, owner_user_id)
    references public.cases (id, owner_user_id) on delete cascade
);
create index workflow_runs_owner_idx on public.workflow_runs (owner_user_id);
create index workflow_runs_case_idx on public.workflow_runs (case_id);
create index workflow_runs_queue_idx on public.workflow_runs (created_at) where status = 'queued';

create table public.workflow_steps (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null,
  case_id        uuid not null,
  run_id         uuid not null,
  -- run.v1 has exactly 14 ordered steps; the engine creates all 14 together.
  n              smallint not null check (n between 1 and 14),
  node           text not null,
  status         text not null default 'pending' check (status in ('pending', 'running', 'done', 'warning', 'failed', 'skipped')),
  attempts       integer not null default 0 check (attempts >= 0),
  note           text,
  started_at     timestamptz,
  finished_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint workflow_steps_run_n_key unique (run_id, n),
  constraint workflow_steps_run_same_case_owner foreign key (run_id, case_id, owner_user_id)
    references public.workflow_runs (id, case_id, owner_user_id) on delete cascade
);
create index workflow_steps_owner_idx on public.workflow_steps (owner_user_id);
create index workflow_steps_case_idx on public.workflow_steps (case_id);

create trigger workflow_runs_set_updated_at before update on public.workflow_runs
  for each row execute function app_private.set_updated_at();
create trigger workflow_steps_set_updated_at before update on public.workflow_steps
  for each row execute function app_private.set_updated_at();
create trigger workflow_runs_owner_immutable before update on public.workflow_runs
  for each row execute function app_private.enforce_immutable_column('owner_user_id');
create trigger workflow_steps_owner_immutable before update on public.workflow_steps
  for each row execute function app_private.enforce_immutable_column('owner_user_id');

alter table public.workflow_runs enable row level security;
alter table public.workflow_runs force row level security;
alter table public.workflow_steps enable row level security;
alter table public.workflow_steps force row level security;

revoke all on public.workflow_runs, public.workflow_steps from public, anon, authenticated, service_role;

-- Read-only for the user. The pipeline writes through a system role added in a later phase.
grant select on public.workflow_runs, public.workflow_steps to authenticated;
create policy workflow_runs_select_own on public.workflow_runs for select to authenticated
  using (owner_user_id = (select auth.uid()));
create policy workflow_steps_select_own on public.workflow_steps for select to authenticated
  using (owner_user_id = (select auth.uid()));
