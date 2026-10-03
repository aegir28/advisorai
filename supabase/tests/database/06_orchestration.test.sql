-- n8n orchestration foundation (ADR 0012): what app_system may read and write for a run, and what it may not.
begin;
create extension if not exists pgtap with schema extensions;
select * from no_plan();

create schema tests;
create function tests.try_as(uid uuid, stmt text, as_role text default 'authenticated') returns text
language plpgsql as $$
declare n bigint;
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
do $$ begin execute format('grant app_system, app_backend to %I', current_user); end $$;

insert into auth.users (id, aud, role, email) values
  ('dddddddd-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'd1@advisorai.test'),
  ('dddddddd-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'd2@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('dddddddd-1000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001', 52, 'M'),
  ('dddddddd-1000-4000-8000-000000000002', 'dddddddd-0000-4000-8000-000000000002', 41, 'F');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('dddddddd-2000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001', 'dddddddd-1000-4000-8000-000000000001', 'AC-D1', 'synthetic concern one'),
  ('dddddddd-2000-4000-8000-000000000002', 'dddddddd-0000-4000-8000-000000000002', 'dddddddd-1000-4000-8000-000000000002', 'AC-D2', 'synthetic concern two');
insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path, mime_type, size_bytes, pages) values
  ('dddddddd-4000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'lab', 'a file name', 'ready',
   'dddddddd-0000-4000-8000-000000000001/dddddddd-2000-4000-8000-000000000001/dddddddd-4000-4000-8000-000000000001', 'application/pdf', 1000, 2);

-- ── Nothing is readable until a run for the case is active ──────────────────────────────────────
select is(tests.try_as(null, $$select id, concern from public.cases$$, 'app_system'), 'ok:0', 'app_system reads no case when no run is active');
select is(tests.try_as(null, $$select id from public.documents$$, 'app_system'), 'ok:0', 'nor any document');

insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version, orchestrator, idempotency_key) values
  ('dddddddd-3000-4000-8000-000000000001', 'dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'case_analysis', '1', 'n8n', 'key-0001-abcdef'),
  ('dddddddd-3000-4000-8000-000000000009', 'dddddddd-0000-4000-8000-000000000002', 'dddddddd-2000-4000-8000-000000000002', 'case_analysis', '1', 'native', null);

select is(tests.try_as(null, $$select id, concern, proposed_treatment from public.cases$$, 'app_system'), 'ok:1',
  'with an active n8n run, app_system reads exactly that case (not the other case, whose run is native)');
select is(tests.try_as(null, $$select age_years, sex from public.patients$$, 'app_system'), 'ok:1', 'and only that case''s patient (age and sex)');
select is(tests.try_as(null, $$select id, type, storage_path, pages from public.documents$$, 'app_system'), 'ok:1', 'and its documents');

-- ── ...and only the allowed columns ─────────────────────────────────────────────────────────────
select is(tests.try_as(null, $$select title from public.documents$$, 'app_system'), 'err:42501', 'the document title (a file name) is not readable');
select is(tests.try_as(null, $$select * from public.documents$$, 'app_system'), 'err:42501', 'select * on documents is refused');
select is(tests.try_as(null, $$select * from public.cases$$, 'app_system'), 'err:42501', 'select * on cases is refused');
select is(tests.try_as(null, $$select is_synthetic from public.cases$$, 'app_system'), 'err:42501', 'columns outside the grant are refused');
select is(tests.try_as(null, $$select * from public.facts$$, 'app_system'), 'err:42501', 'clinical record tables are not readable at all');
select is(tests.try_as(null, $$select * from public.profiles$$, 'app_system'), 'err:42501', 'profiles (the only table with a name) are not readable');
select is(tests.try_as(null, $$update public.cases set concern = 'x'$$, 'app_system'), 'err:42501', 'app_system cannot change a case');
select is(tests.try_as(null, $$delete from public.documents$$, 'app_system'), 'err:42501', 'nor delete a document');

-- ── a finished run closes the door again ────────────────────────────────────────────────────────
update public.workflow_runs set status = 'complete', finished_at = now() where id = 'dddddddd-3000-4000-8000-000000000001';
select is(tests.try_as(null, $$select id from public.cases$$, 'app_system'), 'ok:0', 'once the run has finished app_system reads nothing');
update public.workflow_runs set status = 'running' where id = 'dddddddd-3000-4000-8000-000000000001';

-- ── artifacts: append-only, idempotent, owner-readable ──────────────────────────────────────────
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001',
          'specialist_report', 'cardiology', 'specialist_report.v1', 'ok', '{"a": 1}')$$, 'app_system'),
  'ok:1', 'app_system can append an artifact for an active run');
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001',
          'specialist_report', 'cardiology', 'specialist_report.v1', 'ok', '{"a": 2}')$$, 'app_system'),
  'err:23505', 'the same (run, kind, key) cannot be written twice (idempotent, never rewritten)');
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000002', 'dddddddd-2000-4000-8000-000000000002', 'dddddddd-3000-4000-8000-000000000009',
          'specialist_report', 'x', 'specialist_report.v1', 'ok', '{}')$$, 'app_system'),
  'err:42501', 'no artifact for a run that is not an active n8n run');
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000002', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001',
          'specialist_report', 'y', 'specialist_report.v1', 'ok', '{}')$$, 'app_system'),
  'err:23503', 'an artifact cannot pair one owner with another owner''s run (composite foreign key)');
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, key, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001',
          'Not A Kind', '-', 'case_context.v1', 'ok', '{}')$$, 'app_system'),
  'err:23514', 'kind must be a short code');
select is(tests.try_as(null, $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001',
          'case_context', 'case_context.v1', 'ok', '[1,2]')$$, 'app_system'),
  'err:23514', 'a payload is a JSON object');
select is(tests.try_as(null, $$update public.analysis_artifacts set status = 'failed'$$, 'app_system'), 'err:42501', 'artifacts cannot be updated');
select is(tests.try_as(null, $$delete from public.analysis_artifacts$$, 'app_system'), 'err:42501', 'nor deleted');
select is(tests.try_as(null, $$select kind, key from public.analysis_artifacts$$, 'app_system'), 'ok:1', 'later stages can read earlier artifacts of an active run');

select is(tests.try_as('dddddddd-0000-4000-8000-000000000001', $$select * from public.analysis_artifacts$$), 'ok:1', 'the owner reads their artifacts');
select is(tests.try_as('dddddddd-0000-4000-8000-000000000002', $$select * from public.analysis_artifacts$$), 'ok:0', 'another user reads none');
select is(tests.try_as('dddddddd-0000-4000-8000-000000000001', $$insert into public.analysis_artifacts (owner_user_id, case_id, run_id, kind, schema_version, status, payload)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001', 'a', 'a.v1', 'ok', '{}')$$),
  'err:42501', 'a user cannot write artifacts');
select is(tests.try_as(null, $$select * from public.analysis_artifacts$$, 'anon'), 'err:42501', 'anon cannot read artifacts');

-- ── run extras: execution id and cancel are system-writable; identity and orchestrator are not ──
select is(tests.try_as(null, $$update public.workflow_runs set external_execution_id = 'n8n-123', cancel_requested_at = now() where id = 'dddddddd-3000-4000-8000-000000000001'$$, 'app_system'),
  'ok:1', 'app_system can record the n8n execution id and a cancel request');
select is(tests.try_as(null, $$update public.workflow_runs set orchestrator = 'native' where id = 'dddddddd-3000-4000-8000-000000000001'$$, 'app_system'),
  'err:42501', 'the orchestrator cannot be changed after the run exists');
select is(tests.try_as(null, $$update public.workflow_runs set idempotency_key = 'other-key-123456' where id = 'dddddddd-3000-4000-8000-000000000001'$$, 'app_system'),
  'err:42501', 'nor the idempotency key');
select is(tests.try_as(null, $$insert into public.workflow_runs (owner_user_id, case_id, definition, definition_version, orchestrator, idempotency_key)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'case_analysis', '1', 'n8n', 'key-0001-abcdef')$$, 'app_system'),
  'err:23505', 'a second run with the same idempotency key for a case is refused');

-- ── the usage ledger: one column readable on the system path ────────────────────────────────────
insert into public.model_usage (owner_user_id, case_id, run_id, purpose, provider, model, tier, input_tokens, output_tokens, cost_micro_usd, latency_ms, attempts, outcome)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001', 'test.step', 'fake', 'fake-small', 1, 1, 1, 123, 1, 1, 'success');
select is(tests.try_as(null, $$select coalesce(sum(cost_micro_usd), 0) from public.model_usage$$, 'app_system'), 'ok:1', 'app_system can total the cost column');
select is(tests.try_as(null, $$select model from public.model_usage$$, 'app_system'), 'err:42501', 'but not read any other column of usage');
select is(tests.try_as(null, $$select * from public.model_usage$$, 'app_system'), 'err:42501', 'nor select *');

-- ── steps come from the workflow definition: the number of steps is no longer fixed at 14 ───────
select lives_ok($$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001', 15, 'a_fifteenth_stage')$$,
  'a run may have more than 14 steps');
select throws_ok($$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001', 65, 'too_many')$$,
  '23514', null, 'but not more than the loader maximum (64)');
select throws_ok($$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)
  values ('dddddddd-0000-4000-8000-000000000001', 'dddddddd-2000-4000-8000-000000000001', 'dddddddd-3000-4000-8000-000000000001', 0, 'zero')$$,
  '23514', null, 'and step numbers start at 1');

select * from finish();
rollback;
