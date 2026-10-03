-- n8n orchestration foundation (ADR 0012).
--
-- n8n sequences the clinical pipeline but holds NO database login. Everything it needs goes through the backend,
-- which acts on the SYSTEM path (app_system). Until now that role could only drive workflow_runs / steps. This
-- migration gives it exactly what a run needs and nothing a user session can reach:
--
--   * READ the case being analysed, ONLY while a run for that case is active (queued/running, orchestrator 'n8n'),
--     and only the columns a model call may be built from. documents.title (a file name: personal) and storage
--     internals other than the path are not readable; there is no read of any other case.
--   * APPEND results to analysis_artifacts (insert-only, one row per run/kind/key: idempotent, never rewritten).
--   * record the n8n execution id and a cancel request on the run.
--
-- A user can read their own artifacts (RLS) and nothing more. Artifacts hold document text and model output for
-- the owner's own case; they are removed with the case (ON DELETE CASCADE) like everything else.

-- ── runs: who orchestrates, correlation, idempotency, cancel ─────────────────────────────────────
alter table public.workflow_runs
  add column orchestrator text not null default 'native' check (orchestrator in ('native', 'n8n')),
  add column external_execution_id text check (external_execution_id is null or external_execution_id ~ '^[A-Za-z0-9_.:-]{1,128}$'),
  -- One analysis per (case, idempotency key): a retried POST /analysis returns the same run instead of a second one.
  add column idempotency_key text check (idempotency_key is null or idempotency_key ~ '^[A-Za-z0-9_.:-]{8,128}$'),
  add column cancel_requested_at timestamptz;
create unique index workflow_runs_idempotency_key on public.workflow_runs (case_id, idempotency_key)
  where idempotency_key is not null;
create index workflow_runs_active_n8n_idx on public.workflow_runs (case_id) where orchestrator = 'n8n' and status in ('queued', 'running');

grant update (external_execution_id, cancel_requested_at) on public.workflow_runs to app_system;

-- ── artifacts: what each stage produced ──────────────────────────────────────────────────────────
create table public.analysis_artifacts (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null,
  case_id        uuid not null,
  run_id         uuid not null,
  -- e.g. document_text, extracted_facts, case_context, routing_plan, specialist_report, verification, ...
  -- A pattern, not a list: a new stage or specialist needs no migration.
  kind           text not null check (kind ~ '^[a-z][a-z0-9_]{0,47}$'),
  -- A per-kind key: a specialist id, a document id, or '-' for one-per-run kinds.
  key            text not null default '-' check (key ~ '^[a-z0-9_.-]{1,64}$'),
  schema_version text not null check (schema_version ~ '^[a-z][a-z0-9_]*\.v[0-9]+$'),
  -- `unavailable`: the stage could not produce a result (specialist timed out, provider down). It is recorded, never invented.
  status         text not null check (status in ('ok', 'unavailable', 'failed')),
  reason_code    text check (reason_code is null or reason_code ~ '^[a-z][a-z0-9_]{0,63}$'),
  payload        jsonb not null check (jsonb_typeof(payload) = 'object' and pg_column_size(payload) < 4000000),
  created_at     timestamptz not null default now(),
  constraint analysis_artifacts_run_kind_key unique (run_id, kind, key),
  constraint analysis_artifacts_run_same_case_owner foreign key (run_id, case_id, owner_user_id)
    references public.workflow_runs (id, case_id, owner_user_id) on delete cascade
);
create index analysis_artifacts_owner_idx on public.analysis_artifacts (owner_user_id);
create index analysis_artifacts_case_idx on public.analysis_artifacts (case_id, created_at);

alter table public.analysis_artifacts enable row level security;
alter table public.analysis_artifacts force row level security;
revoke all on public.analysis_artifacts from public, anon, authenticated, service_role;

grant select on public.analysis_artifacts to authenticated;
create policy analysis_artifacts_select_own on public.analysis_artifacts for select to authenticated
  using (owner_user_id = (select auth.uid()));

-- ── the system path: active-run reads, append-only writes ────────────────────────────────────────
grant select, insert on public.analysis_artifacts to app_system;
create policy analysis_artifacts_system_select on public.analysis_artifacts for select to app_system
  using (exists (select 1 from public.workflow_runs r where r.id = analysis_artifacts.run_id and r.orchestrator = 'n8n' and r.status in ('queued', 'running')));
create policy analysis_artifacts_system_insert on public.analysis_artifacts for insert to app_system
  with check (exists (select 1 from public.workflow_runs r where r.id = analysis_artifacts.run_id and r.orchestrator = 'n8n' and r.status in ('queued', 'running')));

grant select (id, owner_user_id, patient_id, code, intent, concern, proposed_treatment, status) on public.cases to app_system;
create policy cases_system_active_run_select on public.cases for select to app_system
  using (exists (select 1 from public.workflow_runs r where r.case_id = cases.id and r.owner_user_id = cases.owner_user_id and r.orchestrator = 'n8n' and r.status in ('queued', 'running')));

grant select (id, owner_user_id, age_years, sex) on public.patients to app_system;
create policy patients_system_active_run_select on public.patients for select to app_system
  using (exists (select 1 from public.cases c join public.workflow_runs r on r.case_id = c.id and r.owner_user_id = c.owner_user_id
                  where c.patient_id = patients.id and c.owner_user_id = patients.owner_user_id and r.orchestrator = 'n8n' and r.status in ('queued', 'running')));

grant select (id, owner_user_id, case_id, type, status, storage_path, mime_type, size_bytes, sha256, pages, ocr_confidence) on public.documents to app_system;
create policy documents_system_active_run_select on public.documents for select to app_system
  using (exists (select 1 from public.workflow_runs r where r.case_id = documents.case_id and r.owner_user_id = documents.owner_user_id and r.orchestrator = 'n8n' and r.status in ('queued', 'running')));

-- ── re-assert what must stay true ────────────────────────────────────────────────────────────────
do $$
declare
  bad text;
begin
  -- Column-level reads of app_system, exhaustively: anything else is refused.
  select string_agg(distinct table_name || '.' || column_name, ', ') into bad
  from information_schema.role_column_grants
  where table_schema = 'public' and grantee = 'app_system' and privilege_type = 'SELECT'
    and not (
      (table_name = 'cases' and column_name in ('id', 'owner_user_id', 'patient_id', 'code', 'intent', 'concern', 'proposed_treatment', 'status'))
      or (table_name = 'patients' and column_name in ('id', 'owner_user_id', 'age_years', 'sex'))
      or (table_name = 'documents' and column_name in ('id', 'owner_user_id', 'case_id', 'type', 'status', 'storage_path', 'mime_type', 'size_bytes', 'sha256', 'pages', 'ocr_confidence'))
      or (table_name = 'model_usage' and column_name = 'cost_micro_usd')
      or table_name in ('workflow_runs', 'workflow_steps', 'analysis_artifacts', 'audit_logs')
    );
  if bad is not null then
    raise exception 'app_system can read unexpected columns: %', bad;
  end if;
  -- Writes: never to case data, never UPDATE/DELETE on artifacts or usage.
  if exists (select from information_schema.role_table_grants
              where table_schema = 'public' and grantee = 'app_system' and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE')
                and table_name not in ('workflow_runs', 'workflow_steps')) then
    raise exception 'app_system may not UPDATE/DELETE outside the workflow tables';
  end if;
  if exists (select from information_schema.role_table_grants
              where table_schema = 'public' and grantee = 'app_system' and privilege_type = 'INSERT'
                and table_name not in ('audit_logs', 'model_usage', 'workflow_runs', 'workflow_steps', 'analysis_artifacts')) then
    raise exception 'app_system may not INSERT outside its own tables';
  end if;
  if exists (select from information_schema.role_table_grants
              where table_schema = 'public' and table_name = 'analysis_artifacts'
                and grantee in ('anon', 'service_role', 'authenticated') and privilege_type <> 'SELECT') then
    raise exception 'clients may only SELECT analysis_artifacts';
  end if;
  if not (select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.analysis_artifacts'::regclass) then
    raise exception 'analysis_artifacts must have RLS enabled and forced';
  end if;
end $$;
