-- Phase 2B / 5 of 8: structured medical records.
-- medical_records keeps the case.v1 JSON snapshot (all the sections that are not normalised yet).
-- facts is the provenance root: every normalised clinical row points at a fact, and every fact
-- points at a document page and snippet. All tables are pseudonymous: no name, email or phone.

-- Keys that must never appear at the top level of a stored case snapshot.
create or replace function app_private.case_json_has_identity(doc jsonb) returns boolean
language sql immutable as $$
  select doc ?| array['name', 'display_name', 'full_name', 'patient_name', 'owner_label',
                      'email', 'phone', 'mobile', 'address', 'dob', 'date_of_birth']
$$;

create table public.medical_records (
  id              uuid primary key default gen_random_uuid(),
  owner_user_id   uuid not null default auth.uid(),
  case_id         uuid not null,
  run_id          uuid,
  schema_version  text not null check (schema_version = 'case.v1'),
  case_json       jsonb not null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint medical_records_is_a_case_object check (
    jsonb_typeof(case_json) = 'object'
    and case_json ->> 'schema_version' = schema_version
    and case_json ->> 'case_id' = case_id::text
  ),
  constraint medical_records_no_identity check (not app_private.case_json_has_identity(case_json)),
  constraint medical_records_case_same_owner foreign key (case_id, owner_user_id)
    references public.cases (id, owner_user_id) on delete cascade,
  -- run_id is nullable; with MATCH SIMPLE the run link is enforced whenever it is set.
  constraint medical_records_run_same_case_owner foreign key (run_id, case_id, owner_user_id)
    references public.workflow_runs (id, case_id, owner_user_id) on delete cascade
);
create unique index medical_records_one_per_run on public.medical_records (run_id) where run_id is not null;

create table public.facts (
  id               uuid primary key default gen_random_uuid(),
  owner_user_id    uuid not null default auth.uid(),
  case_id          uuid not null,
  document_id      uuid not null,
  type             text not null check (type in (
                     'symptom', 'lab_result', 'ecg', 'procedure_finding', 'medication',
                     'diagnosis', 'recommendation', 'treatment_history', 'imaging')),
  label            text not null,
  value            text,
  flag             text check (flag in ('high', 'low', 'abnormal')),
  fact_date        date not null,
  page             integer not null check (page >= 1),
  section          text,
  snippet          text not null check (char_length(snippet) >= 1),
  confidence       numeric(4, 3) not null check (confidence between 0 and 1),
  uncertain_value  boolean not null default false,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint facts_id_case_owner_key unique (id, case_id, owner_user_id),
  constraint facts_document_same_case_owner foreign key (document_id, case_id, owner_user_id)
    references public.documents (id, case_id, owner_user_id) on delete cascade
);

create table public.timeline_events (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null default auth.uid(),
  case_id        uuid not null,
  fact_id        uuid not null,
  event_date     date not null,
  precision      text not null check (precision in ('day', 'month', 'approx')),
  title          text not null,
  detail         text not null,
  conflict       text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint timeline_events_fact_same_case_owner foreign key (fact_id, case_id, owner_user_id)
    references public.facts (id, case_id, owner_user_id) on delete cascade
);

create table public.medications (
  id               uuid primary key default gen_random_uuid(),
  owner_user_id    uuid not null default auth.uid(),
  case_id          uuid not null,
  fact_id          uuid not null,
  medication_name  text not null,
  dose             text,
  freq             text,
  start_text       text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint medications_fact_same_case_owner foreign key (fact_id, case_id, owner_user_id)
    references public.facts (id, case_id, owner_user_id) on delete cascade
);

create table public.lab_results (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null default auth.uid(),
  case_id        uuid not null,
  fact_id        uuid not null,
  test_name      text not null,
  value          text,
  unit           text,
  flag           text check (flag in ('high', 'low', 'abnormal')),
  result_date    date,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint lab_results_fact_same_case_owner foreign key (fact_id, case_id, owner_user_id)
    references public.facts (id, case_id, owner_user_id) on delete cascade
);

create table public.diagnoses (
  id              uuid primary key default gen_random_uuid(),
  owner_user_id   uuid not null default auth.uid(),
  case_id         uuid not null,
  fact_id         uuid not null,
  diagnosis_name  text not null,
  status          text not null check (status in ('documented', 'suspected')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint diagnoses_fact_same_case_owner foreign key (fact_id, case_id, owner_user_id)
    references public.facts (id, case_id, owner_user_id) on delete cascade
);

create table public.procedures (
  id              uuid primary key default gen_random_uuid(),
  owner_user_id   uuid not null default auth.uid(),
  case_id         uuid not null,
  fact_id         uuid not null,
  procedure_name  text not null,
  procedure_date  date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint procedures_fact_same_case_owner foreign key (fact_id, case_id, owner_user_id)
    references public.facts (id, case_id, owner_user_id) on delete cascade
);

-- Indexes for the owner/case lookups RLS and the app perform.
create index medical_records_owner_idx on public.medical_records (owner_user_id);
create index medical_records_case_idx on public.medical_records (case_id);
create index facts_owner_idx on public.facts (owner_user_id);
create index facts_case_idx on public.facts (case_id);
create index facts_document_idx on public.facts (document_id);
create index timeline_events_owner_idx on public.timeline_events (owner_user_id);
create index timeline_events_case_idx on public.timeline_events (case_id);
create index timeline_events_fact_idx on public.timeline_events (fact_id);
create index medications_owner_idx on public.medications (owner_user_id);
create index medications_case_idx on public.medications (case_id);
create index medications_fact_idx on public.medications (fact_id);
create index lab_results_owner_idx on public.lab_results (owner_user_id);
create index lab_results_case_idx on public.lab_results (case_id);
create index lab_results_fact_idx on public.lab_results (fact_id);
create index diagnoses_owner_idx on public.diagnoses (owner_user_id);
create index diagnoses_case_idx on public.diagnoses (case_id);
create index diagnoses_fact_idx on public.diagnoses (fact_id);
create index procedures_owner_idx on public.procedures (owner_user_id);
create index procedures_case_idx on public.procedures (case_id);
create index procedures_fact_idx on public.procedures (fact_id);

-- updated_at and owner immutability on every table, RLS on every table, read-only for the user.
do $$
declare
  t text;
begin
  foreach t in array array['medical_records', 'facts', 'timeline_events', 'medications',
                           'lab_results', 'diagnoses', 'procedures']
  loop
    execute format('create trigger %I before update on public.%I for each row execute function app_private.set_updated_at()',
                   t || '_set_updated_at', t);
    execute format('create trigger %I before update on public.%I for each row execute function app_private.enforce_immutable_column(%L)',
                   t || '_owner_immutable', t, 'owner_user_id');
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
    -- Derived data: the user may read their own rows; only the (later) pipeline writes them.
    execute format('grant select on public.%I to authenticated', t);
    execute format('create policy %I on public.%I for select to authenticated using (owner_user_id = (select auth.uid()))',
                   t || '_select_own', t);
  end loop;
end $$;
