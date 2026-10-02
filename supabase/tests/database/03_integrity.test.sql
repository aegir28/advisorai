-- Integrity rules that hold for EVERY role, including the database owner: append-only audit log,
-- synthetic-only lock, storage path convention, one patient per case, cascades, check constraints.
begin;
create extension if not exists pgtap with schema extensions;
select * from no_plan();

insert into auth.users (id, aud, role, email) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'a@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('a1000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 50, 'M');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('a2000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a1000000-0000-4000-8000-000000000001', 'AC-AAA', 'c');
insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path) values
  ('a3000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'lab', 'd', 'ready',
   'aaaaaaaa-0000-4000-8000-000000000001/a2000000-0000-4000-8000-000000000001/a3000000-0000-4000-8000-000000000001');

-- ── Synthetic data only, until a deliberate migration says otherwise ────────────────────────────
select throws_ok(
  $$insert into public.patients (owner_user_id, age_years, sex, is_synthetic) values ('aaaaaaaa-0000-4000-8000-000000000001', 30, 'F', false)$$,
  '23514', null, 'a real (non-synthetic) patient is refused by the database');
select throws_ok(
  $$insert into public.cases (owner_user_id, patient_id, code, concern, is_synthetic)
    select owner_user_id, id, 'AC-REAL', 'x', false from public.patients limit 1$$,
  '23514', null, 'a real (non-synthetic) case is refused by the database');

-- ── Constraints ─────────────────────────────────────────────────────────────────────────────────
select throws_ok($$insert into public.patients (owner_user_id, age_years, sex) values ('aaaaaaaa-0000-4000-8000-000000000001', 121, 'M')$$, '23514', null, 'age above 120 is refused');
select throws_ok($$insert into public.patients (owner_user_id, age_years, sex) values ('aaaaaaaa-0000-4000-8000-000000000001', 30, 'Z')$$, '23514', null, 'unknown sex is refused');
select throws_ok($$update public.cases set status = 'queued' where id = 'a2000000-0000-4000-8000-000000000001'$$, '23514', null, 'a case status outside the contract is refused');
select lives_ok($$update public.documents set status = 'pending_upload' where id = 'a3000000-0000-4000-8000-000000000001'$$, 'pending_upload is a valid internal document state');
select throws_ok($$update public.documents set status = 'uploading' where id = 'a3000000-0000-4000-8000-000000000001'$$, '23514', null, 'an unknown document status is refused');
select throws_ok(
  $$insert into public.documents (owner_user_id, case_id, type, title, storage_path)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'lab', 'x', 'somewhere/else/entirely')$$,
  '23514', null, 'a storage path that is not owner/case/document is refused');
select throws_ok(
  $$insert into public.cases (owner_user_id, patient_id, code, concern)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a1000000-0000-4000-8000-000000000001', 'AC-DUP', 'x')$$,
  '23505', null, 'one patient row per case: a second case for the same patient is refused');
select throws_ok(
  $$insert into public.documents (owner_user_id, case_id, type, title, mime_type, storage_path)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'lab', 'x', 'application/zip',
            'aaaaaaaa-0000-4000-8000-000000000001/a2000000-0000-4000-8000-000000000001/a3000000-0000-4000-8000-0000000000f1')$$,
  '23514', null, 'a document MIME type outside PDF/JPEG/PNG is refused');

-- ── Workflow persistence ────────────────────────────────────────────────────────────────────────
insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version) values
  ('a5000000-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case_analysis', '1');
select is((select status from public.workflow_runs where id = 'a5000000-0000-4000-8000-000000000001'), 'queued',
          'a new workflow run starts in the internal queued state (not mapped to running)');
select lives_ok($$update public.workflow_runs set status = 'running' where id = 'a5000000-0000-4000-8000-000000000001'$$, 'queued -> running is allowed');
select throws_ok($$update public.workflow_runs set status = 'failed' where id = 'a5000000-0000-4000-8000-000000000001'$$, '23514', null, 'a failed run must carry a failure (as in run.v1)');
select lives_ok($$update public.workflow_runs set status = 'failed', failure = '{"title":"Stopped","body":"Why"}' where id = 'a5000000-0000-4000-8000-000000000001'$$, 'a failed run with a failure is allowed');
select throws_ok($$update public.workflow_runs set status = 'exploded' where id = 'a5000000-0000-4000-8000-000000000001'$$, '23514', null, 'an unknown run status is refused');
select throws_ok($$update public.workflow_runs set progress = 1.5 where id = 'a5000000-0000-4000-8000-000000000001'$$, '23514', null, 'progress above 1 is refused');
select throws_ok($$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node) values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 15, 'x')$$, '23514', null, 'step 15 does not exist (run.v1 has 14)');
insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node) values
  ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 1, 'x');
select throws_ok($$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node) values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'a5000000-0000-4000-8000-000000000001', 1, 'y')$$, '23505', null, 'a run cannot have two step 1s');

-- ── Medical records: the snapshot must be a case.v1 object with no identity ─────────────────────
select throws_ok(
  $$insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case.v1',
            '{"schema_version":"case.v1","case_id":"a2000000-0000-4000-8000-000000000001","name":"Someone"}')$$,
  '23514', null, 'a snapshot with a "name" key is refused');
select throws_ok(
  $$insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case.v1',
            '{"schema_version":"case.v1","case_id":"a2000000-0000-4000-8000-000000000001","email":"x@y.z"}')$$,
  '23514', null, 'a snapshot with an "email" key is refused');
select throws_ok(
  $$insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case.v2',
            '{"schema_version":"case.v2","case_id":"a2000000-0000-4000-8000-000000000001"}')$$,
  '23514', null, 'only case.v1 snapshots are accepted');
select throws_ok(
  $$insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case.v1',
            '{"schema_version":"case.v1","case_id":"some-other-case"}')$$,
  '23514', null, 'a snapshot must be about its own case');
select lives_ok(
  $$insert into public.medical_records (owner_user_id, case_id, schema_version, case_json)
    values ('aaaaaaaa-0000-4000-8000-000000000001', 'a2000000-0000-4000-8000-000000000001', 'case.v1',
            '{"schema_version":"case.v1","case_id":"a2000000-0000-4000-8000-000000000001","chief_concern":"c"}')$$,
  'a clean case.v1 snapshot is accepted');

-- ── audit_logs: append-only for EVERY role, even the database owner ─────────────────────────────
insert into public.audit_logs (action, actor_user_id, target_type, target_id, request_id, ip_hash, metadata)
values ('case.create', 'aaaaaaaa-0000-4000-8000-000000000001', 'case', 'a2000000-0000-4000-8000-000000000001', 'req_audit1',
        repeat('a', 64), '{"result":"success"}');
select throws_ok($$update public.audit_logs set action = 'case.delete'$$, '42501', 'audit_logs is append-only', 'the owner cannot UPDATE audit rows');
select throws_ok($$delete from public.audit_logs$$, '42501', 'audit_logs is append-only', 'the owner cannot DELETE audit rows');
select throws_ok($$truncate public.audit_logs$$, '42501', 'audit_logs is append-only', 'the owner cannot TRUNCATE audit rows');
select throws_ok($$insert into public.audit_logs (action) values ('NOT AN ACTION')$$, '23514', null, 'an audit action must look like domain.event');
select throws_ok($$insert into public.audit_logs (action, ip_hash) values ('case.create', '203.0.113.9')$$, '23514', null, 'a raw IP address cannot be stored: only a 64-hex HMAC');
select throws_ok($$insert into public.audit_logs (action, metadata) values ('case.create', '{"snippet":"HbA1c 8.9"}')$$, '23514', null, 'medical content cannot be put in audit metadata');
select throws_ok($$insert into public.audit_logs (action, metadata) values ('case.create', '{"email":"a@b.c"}')$$, '23514', null, 'identity cannot be put in audit metadata');
select throws_ok($$insert into public.audit_logs (action, metadata) values ('document.signed_url_issued', '{"url":"https://x"}')$$, '23514', null, 'a signed URL cannot be put in audit metadata');

-- ── Audit rows survive deletion of the data they describe ───────────────────────────────────────
select is((select count(*)::int from public.audit_logs where request_id = 'req_audit1'), 1, 'the audit row exists before deletion');

-- ── Deletion: deleting the user removes everything, but not the audit trail ─────────────────────
select is((select count(*)::int from public.patients where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001'), 1, 'the patient exists');
select lives_ok($$delete from auth.users where id = 'aaaaaaaa-0000-4000-8000-000000000001'$$, 'a user can be deleted');
select is(
  (select (select count(*) from public.patients where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.cases where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.documents where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.medical_records where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.workflow_runs where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.workflow_steps where owner_user_id = 'aaaaaaaa-0000-4000-8000-000000000001')
        + (select count(*) from public.profiles where user_id = 'aaaaaaaa-0000-4000-8000-000000000001'))::int,
  0, 'deleting the user cascaded through patients, cases, documents, records, runs, steps and the profile');
select is((select count(*)::int from public.audit_logs where request_id = 'req_audit1'), 1, 'the audit row survives the deletion');

-- ── Deleting a case removes its patient (nothing is orphaned) ───────────────────────────────────
insert into auth.users (id, aud, role, email) values ('cccccccc-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'c@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex) values ('c1000000-0000-4000-8000-000000000001', 'cccccccc-0000-4000-8000-000000000001', 60, 'F');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('c2000000-0000-4000-8000-000000000001', 'cccccccc-0000-4000-8000-000000000001', 'c1000000-0000-4000-8000-000000000001', 'AC-CCC', 'c');
select lives_ok($$delete from public.cases where id = 'c2000000-0000-4000-8000-000000000001'$$, 'a case can be deleted');
select is((select count(*)::int from public.patients where id = 'c1000000-0000-4000-8000-000000000001'), 0, 'deleting the case also deleted its patient row');

-- ── Phase 2C: one READY document per content hash per case (upload validation) ──────────────────
insert into auth.users (id, aud, role, email) values
  ('dddddddd-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'd@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex)
  values ('dddddddd-1000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001', 40, 'F');
insert into public.cases (id, owner_user_id, patient_id, code, concern)
  values ('dddddddd-2000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001',
          'dddddddd-1000-4000-8000-000000000001', 'AC-DUP', 'synthetic');
insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path, sha256) values
  ('dddddddd-3000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001',
   'dddddddd-2000-4000-8000-000000000001', 'lab', 'a.pdf', 'ready',
   'dddddddd-0000-4000-8000-000000000001/dddddddd-2000-4000-8000-000000000001/dddddddd-3000-4000-8000-000000000001',
   repeat('a', 64));

select throws_ok(
  $$insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path, sha256) values
    ('dddddddd-3000-4000-8000-000000000002', 'dddddddd-0000-4000-8000-000000000001',
     'dddddddd-2000-4000-8000-000000000001', 'lab', 'b.pdf', 'ready',
     'dddddddd-0000-4000-8000-000000000001/dddddddd-2000-4000-8000-000000000001/dddddddd-3000-4000-8000-000000000002',
     repeat('a', 64))$$,
  '23505'::char(5), null::text, 'two READY documents with the same content hash cannot exist in one case');

select lives_ok(
  $$insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path, sha256) values
    ('dddddddd-3000-4000-8000-000000000003', 'dddddddd-0000-4000-8000-000000000001',
     'dddddddd-2000-4000-8000-000000000001', 'lab', 'c.pdf', 'duplicate',
     'dddddddd-0000-4000-8000-000000000001/dddddddd-2000-4000-8000-000000000001/dddddddd-3000-4000-8000-000000000003',
     repeat('a', 64))$$,
  'the same hash is allowed once the document is marked duplicate');


select * from finish();
rollback;
