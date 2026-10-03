-- RLS isolation between two users, anon, and the system role. Mirrors ADR 0005: the helper below
-- does exactly what the backend does (SET LOCAL role + claims), then reports what the statement did.
begin;
create extension if not exists pgtap with schema extensions;
select * from no_plan();

create schema tests;
-- Runs `stmt` as `as_role`, with `uid` as the verified user (NULL = no context at all), and returns
-- 'ok:<rows affected or returned>' or 'err:<sqlstate>'. Everything is transaction-local and undone.
create function tests.try_as(uid uuid, stmt text, as_role text default 'authenticated') returns text
language plpgsql as $$
declare
  n bigint;
begin
  perform set_config('role', as_role, true);
  perform set_config('request.jwt.claims',
                     case when uid is null then '' else json_build_object('sub', uid, 'role', as_role)::text end, true);
  perform set_config('request.jwt.claim.sub', coalesce(uid::text, ''), true);
  execute stmt;
  get diagnostics n = row_count;
  execute 'reset role';
  return 'ok:' || n;
exception when others then
  execute 'reset role';
  return 'err:' || sqlstate;
end $$;

-- The test session must be allowed to SET ROLE to the project roles (a no-op for a superuser).
-- The role is named explicitly: on the Supabase image `GRANT ... TO CURRENT_USER` crashed the server.
do $$ begin execute format('grant app_system, app_backend to %I', current_user); end $$;

-- ── Fixtures, written as the database owner (bypasses RLS) ──────────────────────────────────────
-- Users A and B. Profiles are created by the on_auth_user_created trigger.
insert into auth.users (id, aud, role, email, raw_user_meta_data) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'a@advisorai.test', '{"full_name":"User A"}'),
  ('bbbbbbbb-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'b@advisorai.test', '{"full_name":"User B"}');

insert into public.patients (id, owner_user_id, age_years, sex) values
  ('a1000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 50, 'M'),
  ('b1000000-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000001', 40, 'F');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('a2000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a1000000-0000-4000-8000-000000000001', 'AC-AAA', 'A concern'),
  ('b2000000-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000001', 'b1000000-0000-4000-8000-000000000001', 'AC-BBB', 'B concern');
insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path) values
  ('a3000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'lab', 'A doc', 'ready',
   'aaaaaaaa-0000-4000-8000-000000000001/a2000000-0000-4000-8000-000000000001/a3000000-0000-4000-8000-000000000001'),
  ('b3000000-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000001', 'b2000000-0000-4000-8000-000000000001', 'lab', 'B doc', 'ready',
   'bbbbbbbb-0000-4000-8000-000000000001/b2000000-0000-4000-8000-000000000001/b3000000-0000-4000-8000-000000000001');

-- Derived rows for A only (so "B sees 0" is meaningful for every table).
insert into public.document_pages (owner_user_id, case_id, document_id, page_no, text) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a3000000-0000-4000-8000-000000000001', 1, 'synthetic text');
insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version) values
  ('a5000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case_analysis', '1');
insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 1, 'step_1');
insert into public.medical_records (owner_user_id, case_id, run_id, schema_version, case_json) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 'case.v1',
   '{"schema_version":"case.v1","case_id":"a2000000-0000-4000-8000-000000000001"}');
insert into public.facts (id, owner_user_id, case_id, document_id, type, label, fact_date, page, snippet, confidence) values
  ('a4000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001',
   'a3000000-0000-4000-8000-000000000001', 'lab_result', 'HbA1c', '2026-03-05', 1, 'HbA1c 8.9 %', 0.9);
insert into public.timeline_events (owner_user_id, case_id, fact_id, event_date, precision, title, detail) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', '2026-03-05', 'day', 't', 'd');
insert into public.medications (owner_user_id, case_id, fact_id, medication_name) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', 'metformin');
insert into public.lab_results (owner_user_id, case_id, fact_id, test_name) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', 'HbA1c');
insert into public.diagnoses (owner_user_id, case_id, fact_id, diagnosis_name, status) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', 'diabetes', 'documented');
insert into public.procedures (owner_user_id, case_id, fact_id, procedure_name) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', 'angiography');

select is((select count(*)::int from public.profiles
            where user_id in ('aaaaaaaa-0000-4000-8000-000000000001', 'bbbbbbbb-0000-4000-8000-000000000001')), 2,
          'the new-user trigger created a profile for each user');

-- ═══ 1. User A cannot read user B's data (and vice versa), on every owner table ════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', 'select * from public.' || t),
          'ok:1', 'A sees exactly their own row in ' || t)
from unnest(array['patients', 'cases', 'documents', 'document_pages', 'medical_records', 'facts',
                  'timeline_events', 'medications', 'lab_results', 'diagnoses', 'procedures',
                  'workflow_runs', 'workflow_steps']) as t;
select is(tests.try_as('bbbbbbbb-0000-4000-8000-000000000001', 'select * from public.' || t),
          'ok:0', 'B sees none of A''s rows in ' || t)
from unnest(array['document_pages', 'medical_records', 'facts', 'timeline_events', 'medications',
                  'lab_results', 'diagnoses', 'procedures', 'workflow_runs', 'workflow_steps']) as t;
select is(tests.try_as('bbbbbbbb-0000-4000-8000-000000000001', 'select * from public.' || t),
          'ok:1', 'B sees exactly their own row in ' || t)
from unnest(array['patients', 'cases', 'documents']) as t;
select is(tests.try_as('bbbbbbbb-0000-4000-8000-000000000001',
                       $$select * from public.cases where id = 'a2000000-0000-4000-8000-000000000001'$$),
          'ok:0', 'B cannot read A''s case even by its exact id');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', 'select * from public.profiles'),
          'ok:1', 'A sees only their own profile');
select is(tests.try_as(null, 'select * from public.cases'), 'ok:0',
          'authenticated with no verified user (auth.uid() is NULL) sees nothing');
select is(tests.try_as(null, 'select * from public.cases', 'app_backend'), 'err:42501',
          'the backend login role with NO context (nothing set) is refused outright: fail closed');
select is(tests.try_as(null, 'select * from public.audit_logs', 'app_backend'), 'err:42501',
          'the backend login role has no access to the audit log either without a context');

-- ═══ 2. User A cannot insert rows owned by user B ═══════════════════════════════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.patients (owner_user_id, age_years, sex) values ('bbbbbbbb-0000-4000-8000-000000000001', 30, 'F')$$),
          'err:42501', 'A cannot insert a patient owned by B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.cases (owner_user_id, patient_id, code, concern) values ('bbbbbbbb-0000-4000-8000-000000000001', 'b1000000-0000-4000-8000-000000000001', 'AC-X1', 'x')$$),
          'err:42501', 'A cannot insert a case owned by B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.documents (owner_user_id, case_id, type, title, storage_path)
              values ('bbbbbbbb-0000-4000-8000-000000000001', 'b2000000-0000-4000-8000-000000000001', 'lab', 'x',
                      'bbbbbbbb-0000-4000-8000-000000000001/b2000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-0000000000aa')$$),
          'err:42501', 'A cannot insert a document owned by B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.patients (age_years, sex) values (30, 'F')$$),
          'ok:1', 'A CAN insert a patient, and owner_user_id defaults to the verified user');
select is((select owner_user_id from public.patients where age_years = 30 and sex = 'F' and id <> 'b1000000-0000-4000-8000-000000000001'),
          'aaaaaaaa-0000-4000-8000-000000000001'::uuid, 'the defaulted owner is exactly A');
select is(tests.try_as(null, $$insert into public.patients (age_years, sex) values (30, 'F')$$), 'err:42501',
          'without a user context nothing can be inserted');

-- ═══ 3. User A cannot change owner_user_id ══════════════════════════════════════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.cases set owner_user_id = 'bbbbbbbb-0000-4000-8000-000000000001' where id = 'a2000000-0000-4000-8000-000000000001'$$),
          'err:42501', 'A cannot hand their case to B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.patients set owner_user_id = 'bbbbbbbb-0000-4000-8000-000000000001' where id = 'a1000000-0000-4000-8000-000000000001'$$),
          'err:42501', 'A cannot hand their patient to B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.documents set owner_user_id = 'bbbbbbbb-0000-4000-8000-000000000001' where id = 'a3000000-0000-4000-8000-000000000001'$$),
          'err:42501', 'A cannot hand their document to B');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.profiles set user_id = 'bbbbbbbb-0000-4000-8000-000000000001' where user_id = 'aaaaaaaa-0000-4000-8000-000000000001'$$),
          'err:42501', 'A cannot re-point their profile');
select throws_ok(
  $$update public.cases set owner_user_id = 'bbbbbbbb-0000-4000-8000-000000000001' where id = 'a2000000-0000-4000-8000-000000000001'$$,
  '42501', 'owner_user_id is immutable', 'even the database owner cannot change owner_user_id (trigger)');

-- ═══ 4. User A cannot update or delete user B's rows ════════════════════════════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.cases set title = 'hijacked' where id = 'b2000000-0000-4000-8000-000000000001'$$),
          'ok:0', 'A updating B''s case changes nothing');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$delete from public.cases where id = 'b2000000-0000-4000-8000-000000000001'$$),
          'ok:0', 'A deleting B''s case deletes nothing');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.profiles set display_name = 'hijacked' where user_id = 'bbbbbbbb-0000-4000-8000-000000000001'$$),
          'ok:0', 'A cannot rename B''s profile');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$update public.profiles set display_name = 'Renamed A' where user_id = 'aaaaaaaa-0000-4000-8000-000000000001'$$),
          'ok:1', 'A can update their own profile');
select is((select title from public.cases where id = 'b2000000-0000-4000-8000-000000000001'), null,
          'B''s case is untouched');

-- ═══ 5. Derived tables are read-only for the user ═══════════════════════════════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.facts (owner_user_id, case_id, document_id, type, label, fact_date, page, snippet, confidence)
              values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a3000000-0000-4000-8000-000000000001', 'symptom', 'x', '2026-01-01', 1, 's', 0.5)$$),
          'err:42501', 'A cannot insert facts (only the pipeline can)');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', $$update public.workflow_runs set status = 'complete'$$),
          'err:42501', 'A cannot update workflow runs');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', $$delete from public.document_pages$$),
          'err:42501', 'A cannot delete document pages');

-- ═══ 6. Child rows cannot cross owners ══════════════════════════════════════════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
            $$insert into public.documents (id, owner_user_id, case_id, type, title, storage_path)
              values ('00000000-0000-4000-8000-0000000000bb', 'aaaaaaaa-0000-4000-8000-000000000001', 'b2000000-0000-4000-8000-000000000001', 'lab', 'x',
                      'aaaaaaaa-0000-4000-8000-000000000001/b2000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-0000000000bb')$$),
          'err:23503', 'A cannot attach their own document to B''s case (composite FK)');
select throws_ok(
  $$insert into public.facts (owner_user_id, case_id, document_id, type, label, fact_date, page, snippet, confidence)
    values ('bbbbbbbb-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a3000000-0000-4000-8000-000000000001', 'symptom', 'x', '2026-01-01', 1, 's', 0.5)$$,
  '23503', null, 'even as the database owner, a fact owned by B cannot hang off A''s case and document');
select throws_ok(
  $$insert into public.timeline_events (owner_user_id, case_id, fact_id, event_date, precision, title, detail)
    values ('bbbbbbbb-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a4000000-0000-4000-8000-000000000001', '2026-03-05', 'day', 't', 'd')$$,
  '23503', null, 'a timeline event cannot cross owners');
select throws_ok(
  $$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)
    values ('bbbbbbbb-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 2, 'x')$$,
  '23503', null, 'a workflow step cannot cross owners');
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('a1000000-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000001', 33, 'F');
select throws_ok(
  $$insert into public.cases (owner_user_id, patient_id, code, concern)
    values ('bbbbbbbb-0000-4000-8000-000000000001', 'a1000000-0000-4000-8000-000000000002', 'AC-X2', 'x')$$,
  '23503', null, 'a case cannot point at another owner''s (unused) patient');

-- ═══ 7. anon can access nothing ═════════════════════════════════════════════════════════════════
select is(tests.try_as(null, 'select 1 from public.' || t || ' limit 1', 'anon'), 'err:42501', 'anon cannot read ' || t)
from unnest(array['profiles', 'patients', 'cases', 'documents', 'document_pages', 'medical_records', 'facts',
                  'timeline_events', 'medications', 'lab_results', 'diagnoses', 'procedures',
                  'workflow_runs', 'workflow_steps', 'audit_logs']) as t;
select is(tests.try_as(null, $$insert into public.patients (owner_user_id, age_years, sex) values ('aaaaaaaa-0000-4000-8000-000000000001', 1, 'M')$$, 'anon'),
          'err:42501', 'anon cannot insert');
select is(tests.try_as(null, $$update public.cases set title = 'x'$$, 'anon'), 'err:42501', 'anon cannot update');
select is(tests.try_as(null, $$delete from public.cases$$, 'anon'), 'err:42501', 'anon cannot delete');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', 'select * from public.cases', 'anon'), 'err:42501',
          'anon cannot read even if a user claim is presented');

-- ═══ 8. audit_logs: clients cannot touch it; the system role can only append ════════════════════
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', 'select * from public.audit_logs'), 'err:42501', 'authenticated cannot read audit_logs');
select is(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001', $$insert into public.audit_logs (action) values ('case.create')$$), 'err:42501', 'authenticated cannot write audit_logs');
select is(tests.try_as(null, $$insert into public.audit_logs (action, actor_user_id, request_id) values ('case.create', 'aaaaaaaa-0000-4000-8000-000000000001', 'req_t1')$$, 'app_system'),
          'ok:1', 'app_system can append an audit row');
select is(tests.try_as(null, 'select * from public.audit_logs', 'app_system'), 'err:42501', 'app_system cannot read audit rows');
select is(tests.try_as(null, $$update public.audit_logs set action = 'case.delete'$$, 'app_system'), 'err:42501', 'app_system cannot update audit rows');
select is(tests.try_as(null, 'delete from public.audit_logs', 'app_system'), 'err:42501', 'app_system cannot delete audit rows');
select is(tests.try_as(null, 'select * from public.cases', 'app_system'), 'err:42501', 'app_system has no access to patient data');

-- ═══ 8b. A user session cannot escalate to the system role ═════════════════════════════════════
-- Proven at the ROLE-MEMBERSHIP level in 01_schema_and_privacy (pg_has_role: app_backend, authenticated,
-- anon and service_role are not members of app_system; app_system is a member of nothing) and enforced at
-- migration time by 20261003000007_security_assertions.sql.
-- It cannot be proven here by trying `SET ROLE`: Postgres checks SET ROLE against the SESSION user, and in
-- this test the session user is the test runner, which may become any role. The BEHAVIOURAL proof logs in as
-- app_backend and tries SET ROLE / SET SESSION AUTHORIZATION: backend/tests/integration/
-- test_user_context_and_rls.py::test_a_normal_authenticated_session_cannot_assume_app_system.

-- ═══ 9. storage: no direct client access to the private bucket ══════════════════════════════════
insert into storage.objects (bucket_id, name) values
  ('case-documents', 'aaaaaaaa-0000-4000-8000-000000000001/a2000000-0000-4000-8000-000000000001/a3000000-0000-4000-8000-000000000001');
select matches(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
                 $$select * from storage.objects where bucket_id = 'case-documents'$$),
               '^(ok:0|err:.*)$', 'the owner cannot list their own files directly: only signed URLs');
select matches(tests.try_as(null, $$select * from storage.objects where bucket_id = 'case-documents'$$, 'anon'),
               '^(ok:0|err:.*)$', 'anon cannot list the bucket');
select matches(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
                 $$insert into storage.objects (bucket_id, name) values ('case-documents', 'aaaaaaaa-0000-4000-8000-000000000001/x/y')$$),
               '^err:', 'the owner cannot write to the bucket directly');
select matches(tests.try_as('aaaaaaaa-0000-4000-8000-000000000001',
                 $$delete from storage.objects where bucket_id = 'case-documents'$$),
               '^(ok:0|err:.*)$', 'the owner cannot delete bucket objects directly');

select * from finish();
rollback;
