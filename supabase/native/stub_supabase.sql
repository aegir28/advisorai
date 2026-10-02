-- SUBSTITUTE for the parts of a Supabase stack the migrations touch (auth, storage, extensions, roles).
-- Used ONLY by supabase/native/run.sh when Docker or the Supabase CLI cannot run. It is NOT a
-- replacement for `supabase start` + `supabase db reset` + `supabase test db` (the `supabase` CI workflow),
-- and a green native run must never be reported as one.
--
-- Shapes mirror Supabase's own definitions for the columns the project uses.

do $$
begin
  if not exists (select from pg_roles where rolname = 'anon') then create role anon nologin noinherit; end if;
  if not exists (select from pg_roles where rolname = 'authenticated') then create role authenticated nologin noinherit; end if;
  if not exists (select from pg_roles where rolname = 'service_role') then create role service_role nologin noinherit bypassrls; end if;
end $$;

create schema if not exists extensions;
create schema if not exists auth;
create schema if not exists storage;
grant usage on schema extensions, auth, storage to anon, authenticated, service_role;

create table if not exists auth.users (
  id uuid primary key,
  aud text,
  role text,
  email text,
  raw_user_meta_data jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Same logic as Supabase's auth.uid().
create or replace function auth.uid() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;
grant execute on function auth.uid() to anon, authenticated, service_role;

create table if not exists storage.buckets (
  id text primary key,
  name text not null,
  public boolean default false,
  file_size_limit bigint,
  allowed_mime_types text[]
);
create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets (id),
  name text
);
alter table storage.objects enable row level security;
grant select, insert, update, delete on storage.objects to anon, authenticated;
