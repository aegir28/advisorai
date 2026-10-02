-- Phase 2B / 3 of 8: cases, documents, document pages.
-- Every row carries owner_user_id. Child rows reference their parent with a COMPOSITE foreign key
-- that includes the owner, so a child can never belong to a different owner than its parent,
-- independently of RLS.

create table public.cases (
  id                    uuid primary key default gen_random_uuid(),
  owner_user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
  patient_id            uuid not null,
  -- Pseudonymous display code ("AC-9F2"). Cases are shown by code and title, never by identity.
  code                  text not null check (code ~ '^[A-Z0-9][A-Z0-9-]{2,23}$'),
  title                 text check (title is null or char_length(title) between 1 and 120),
  intent                text,
  -- Free text typed by the patient. It can contain identifying details, so it is treated as sensitive
  -- and must be de-identified before it can ever reach an AI provider (blueprint, security part).
  concern               text not null check (char_length(concern) between 1 and 4000),
  proposed_treatment    text check (proposed_treatment is null or char_length(proposed_treatment) <= 2000),
  status                text not null default 'draft'
                          check (status in ('draft', 'awaiting_upload', 'processing', 'complete', 'partial', 'failed')),
  is_synthetic          boolean not null default true,
  -- Set by the delete flow before storage objects are removed, so a half-finished delete is visible.
  deletion_requested_at timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint cases_synthetic_only_until_unlocked check (is_synthetic),
  constraint cases_id_owner_key unique (id, owner_user_id),
  constraint cases_owner_code_key unique (owner_user_id, code),
  -- MVP: exactly one patient row per case. Drop this constraint (and nothing else) to allow 1:N.
  constraint cases_one_patient_per_case unique (patient_id),
  constraint cases_patient_same_owner foreign key (patient_id, owner_user_id)
    references public.patients (id, owner_user_id) on delete cascade
);
create index cases_owner_idx on public.cases (owner_user_id);

create table public.documents (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null default auth.uid(),
  case_id        uuid not null,
  type           text not null check (type in ('lab', 'ecg', 'prescription', 'discharge', 'imaging', 'consult', 'other')),
  -- User-visible label (usually the file name). It can carry personal details, so it is sensitive
  -- free text and never part of AI context.
  title          text not null check (char_length(title) between 1 and 255),
  -- pending_upload is an INTERNAL state: no API exposes it yet (ADR 0004).
  status         text not null default 'pending_upload'
                   check (status in ('pending_upload', 'processing', 'ready', 'needs_attention', 'duplicate')),
  storage_path   text not null,
  mime_type      text check (mime_type in ('application/pdf', 'image/jpeg', 'image/png')),
  size_bytes     bigint check (size_bytes between 1 and 20971520),
  sha256         text check (sha256 ~ '^[0-9a-f]{64}$'),
  pages          integer check (pages >= 1),
  ocr_confidence numeric(4, 3) check (ocr_confidence between 0 and 1),
  note           text,
  uploaded_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint documents_id_case_owner_key unique (id, case_id, owner_user_id),
  constraint documents_storage_path_key unique (storage_path),
  -- Blueprint: storage path = user_id/case_id/doc_id.
  constraint documents_storage_path_convention
    check (storage_path = owner_user_id::text || '/' || case_id::text || '/' || id::text),
  constraint documents_case_same_owner foreign key (case_id, owner_user_id)
    references public.cases (id, owner_user_id) on delete cascade
);
create index documents_owner_idx on public.documents (owner_user_id);
create index documents_case_idx on public.documents (case_id);

create table public.document_pages (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null,
  case_id        uuid not null,
  document_id    uuid not null,
  page_no        integer not null check (page_no >= 1),
  -- Filled by document processing in a later phase; nothing writes it yet.
  text           text,
  ocr_confidence numeric(4, 3) check (ocr_confidence between 0 and 1),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint document_pages_document_page_key unique (document_id, page_no),
  constraint document_pages_document_same_case_owner foreign key (document_id, case_id, owner_user_id)
    references public.documents (id, case_id, owner_user_id) on delete cascade
);
create index document_pages_owner_idx on public.document_pages (owner_user_id);
create index document_pages_case_idx on public.document_pages (case_id);

create trigger cases_set_updated_at before update on public.cases
  for each row execute function app_private.set_updated_at();
create trigger documents_set_updated_at before update on public.documents
  for each row execute function app_private.set_updated_at();
create trigger document_pages_set_updated_at before update on public.document_pages
  for each row execute function app_private.set_updated_at();
create trigger cases_owner_immutable before update on public.cases
  for each row execute function app_private.enforce_immutable_column('owner_user_id');
create trigger documents_owner_immutable before update on public.documents
  for each row execute function app_private.enforce_immutable_column('owner_user_id');
create trigger document_pages_owner_immutable before update on public.document_pages
  for each row execute function app_private.enforce_immutable_column('owner_user_id');

-- One patient row per case: deleting the case removes its patient too (privacy: nothing is orphaned).
create or replace function app_private.delete_orphan_patient() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  delete from public.patients p
  where p.id = old.patient_id
    and not exists (select 1 from public.cases c where c.patient_id = p.id);
  return null;
end $$;
revoke all on function app_private.delete_orphan_patient() from public;
create trigger cases_delete_orphan_patient after delete on public.cases
  for each row execute function app_private.delete_orphan_patient();

-- ── RLS and grants ──────────────────────────────────────────────────────────────────────────────
alter table public.cases enable row level security;
alter table public.cases force row level security;
alter table public.documents enable row level security;
alter table public.documents force row level security;
alter table public.document_pages enable row level security;
alter table public.document_pages force row level security;

revoke all on public.cases, public.documents, public.document_pages from public, anon, authenticated, service_role;

-- The signed-in user (through the backend, under RLS) manages their own cases and documents.
grant select, insert, update, delete on public.cases to authenticated;
create policy cases_select_own on public.cases for select to authenticated
  using (owner_user_id = (select auth.uid()));
create policy cases_insert_own on public.cases for insert to authenticated
  with check (owner_user_id = (select auth.uid()));
create policy cases_update_own on public.cases for update to authenticated
  using (owner_user_id = (select auth.uid())) with check (owner_user_id = (select auth.uid()));
create policy cases_delete_own on public.cases for delete to authenticated
  using (owner_user_id = (select auth.uid()));

grant select, insert, update, delete on public.documents to authenticated;
create policy documents_select_own on public.documents for select to authenticated
  using (owner_user_id = (select auth.uid()));
create policy documents_insert_own on public.documents for insert to authenticated
  with check (owner_user_id = (select auth.uid()));
create policy documents_update_own on public.documents for update to authenticated
  using (owner_user_id = (select auth.uid())) with check (owner_user_id = (select auth.uid()));
create policy documents_delete_own on public.documents for delete to authenticated
  using (owner_user_id = (select auth.uid()));

-- Pages are derived data: read-only for the user, written only by the (later) pipeline.
grant select on public.document_pages to authenticated;
create policy document_pages_select_own on public.document_pages for select to authenticated
  using (owner_user_id = (select auth.uid()));
