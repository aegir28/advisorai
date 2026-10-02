-- Phase 2B / 2 of 8: identity (profiles) and pseudonymous patients.
-- profiles is the ONLY public table that may hold a person's name. Email lives in auth.users.
-- Patient medical data is pseudonymous: patients carry age and sex, never a name.

create table public.profiles (
  user_id        uuid primary key references auth.users (id) on delete cascade,
  display_name   text check (display_name is null or char_length(display_name) between 1 and 120),
  locale         text not null default 'en' check (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  consented_at   timestamptz,
  consent_version text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint profiles_consent_pair check ((consented_at is null) = (consent_version is null))
);

create table public.patients (
  id             uuid primary key default gen_random_uuid(),
  owner_user_id  uuid not null default auth.uid() references auth.users (id) on delete cascade,
  age_years      smallint not null check (age_years between 0 and 120),
  sex            text not null check (sex in ('F', 'M', 'X')),
  -- Synthetic data only until a deliberate migration and ADR say otherwise (ADR 0004, decision 6).
  is_synthetic   boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint patients_synthetic_only_until_unlocked check (is_synthetic),
  -- Target of composite foreign keys, so child rows cannot belong to a different owner.
  constraint patients_id_owner_key unique (id, owner_user_id)
);
create index patients_owner_idx on public.patients (owner_user_id);

create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function app_private.set_updated_at();
create trigger profiles_user_immutable before update on public.profiles
  for each row execute function app_private.enforce_immutable_column('user_id');
create trigger patients_set_updated_at before update on public.patients
  for each row execute function app_private.set_updated_at();
create trigger patients_owner_immutable before update on public.patients
  for each row execute function app_private.enforce_immutable_column('owner_user_id');

-- A profile row is created for every new auth user (Google sign-in in Phase 2C; test users now).
-- The display name comes from provider metadata and is stored only here.
create or replace function app_private.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (user_id, display_name)
  values (
    new.id,
    nullif(left(coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', ''), 120), '')
  )
  on conflict (user_id) do nothing;
  return new;
end $$;
revoke all on function app_private.handle_new_user() from public;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function app_private.handle_new_user();

-- ── RLS and grants ──────────────────────────────────────────────────────────────────────────────
alter table public.profiles enable row level security;
alter table public.profiles force row level security;
alter table public.patients enable row level security;
alter table public.patients force row level security;

revoke all on public.profiles, public.patients from public, anon, authenticated, service_role;

-- Profiles are created by the trigger, never by clients; the owner may read and update their own.
grant select on public.profiles to authenticated;
grant update (display_name, locale, consented_at, consent_version) on public.profiles to authenticated;
create policy profiles_select_own on public.profiles for select to authenticated
  using (user_id = (select auth.uid()));
create policy profiles_update_own on public.profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on public.patients to authenticated;
create policy patients_select_own on public.patients for select to authenticated
  using (owner_user_id = (select auth.uid()));
create policy patients_insert_own on public.patients for insert to authenticated
  with check (owner_user_id = (select auth.uid()));
create policy patients_update_own on public.patients for update to authenticated
  using (owner_user_id = (select auth.uid())) with check (owner_user_id = (select auth.uid()));
create policy patients_delete_own on public.patients for delete to authenticated
  using (owner_user_id = (select auth.uid()));
