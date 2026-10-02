-- Phase 2B / 6 of 8: append-only audit log.
-- "Audit what happened, never what the patient's records say" (blueprint, security part).
--
-- Deliberately NOT like the other tables: no owner column, no foreign keys. Audit rows must survive
-- the deletion of the user, case or document they describe, and must not be touched by FK actions.
-- No medical content, names, emails, phone numbers, signed URLs or tokens: only ids, action, time,
-- request id and an HMAC of the client IP (the secret lives in the backend, never in the database).

create table public.audit_logs (
  id             uuid primary key default gen_random_uuid(),
  at             timestamptz not null default now(),
  actor_user_id  uuid,
  action         text not null check (action ~ '^[a-z]+(\.[a-z_]+)+$'),
  target_type    text check (target_type is null or target_type ~ '^[a-z_]{1,40}$'),
  target_id      text check (target_id is null or char_length(target_id) <= 80),
  request_id     text check (request_id is null or request_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  ip_hash        text check (ip_hash is null or ip_hash ~ '^[0-9a-f]{64}$'),
  metadata       jsonb not null default '{}'::jsonb,
  constraint audit_metadata_is_small_and_content_free check (
    jsonb_typeof(metadata) = 'object'
    and pg_column_size(metadata) <= 2048
    and not (metadata ?| array[
      'text', 'content', 'snippet', 'value', 'concern', 'title', 'note', 'prompt', 'response',
      'name', 'display_name', 'email', 'phone', 'address', 'ip', 'token', 'jwt', 'url', 'signed_url'])
  )
);
create index audit_logs_at_idx on public.audit_logs (at);
create index audit_logs_actor_idx on public.audit_logs (actor_user_id, at);
create index audit_logs_target_idx on public.audit_logs (target_type, target_id);

-- Append-only, enforced twice: no UPDATE/DELETE/TRUNCATE grants for anyone, and a trigger that
-- refuses them for every role, including a superuser.
create or replace function app_private.audit_logs_are_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'audit_logs is append-only' using errcode = '42501';
end $$;

create trigger audit_logs_no_update_delete before update or delete on public.audit_logs
  for each row execute function app_private.audit_logs_are_append_only();
create trigger audit_logs_no_truncate before truncate on public.audit_logs
  for each statement execute function app_private.audit_logs_are_append_only();

alter table public.audit_logs enable row level security;
alter table public.audit_logs force row level security;

revoke all on public.audit_logs from public, anon, authenticated, service_role;

-- The only writer is the narrow system role, and it can only INSERT. There is deliberately no
-- policy and no grant for authenticated/anon: clients can neither read nor write audit rows.
grant insert on public.audit_logs to app_system;
create policy audit_logs_system_insert on public.audit_logs for insert to app_system with check (true);
