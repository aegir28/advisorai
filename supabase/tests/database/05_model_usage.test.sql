-- AI usage ledger: who can write it, who can read it, and that it cannot be pointed at someone else's case or run.
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
  ('ffffffff-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'u1@advisorai.test'),
  ('ffffffff-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'u2@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('ffffffff-1000-4000-8000-000000000001', 'ffffffff-0000-4000-8000-000000000001', 40, 'F'),
  ('ffffffff-1000-4000-8000-000000000002', 'ffffffff-0000-4000-8000-000000000002', 41, 'M');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('ffffffff-2000-4000-8000-000000000001', 'ffffffff-0000-4000-8000-000000000001', 'ffffffff-1000-4000-8000-000000000001', 'AC-U1', 'synthetic'),
  ('ffffffff-2000-4000-8000-000000000002', 'ffffffff-0000-4000-8000-000000000002', 'ffffffff-1000-4000-8000-000000000002', 'AC-U2', 'synthetic');
insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version) values
  ('ffffffff-3000-4000-8000-000000000001', 'ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001', 'case_analysis', '1');

-- ── the system role can append usage, for a real case/run of the right owner ─────────────────────
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, run_id, node, purpose, provider, model, tier, input_tokens, output_tokens, cost_micro_usd, latency_ms, attempts, outcome, request_id)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001', 'ffffffff-3000-4000-8000-000000000001',
          'step_a', 'test.step', 'fake', 'fake-small', 1, 100, 50, 30, 12, 1, 'success', 'req-1')$$, 'app_system'),
  'ok:1', 'app_system can record usage for a run');
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, cost_micro_usd, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'test.step', 'openai', 'some-model', 2, 1, 1, null, 5, 2, 'retries_exhausted')$$, 'app_system'),
  'ok:1', 'usage without a run is allowed, and an unknown cost is NULL, not an invented number');

-- ── ownership is enforced by composite foreign keys ─────────────────────────────────────────────
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000002',
          'test.step', 'fake', 'fake-small', 1, 1, 1, 1, 1, 'success')$$, 'app_system'),
  'err:23503', 'usage cannot name a case that belongs to a different owner');
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, run_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000002', 'ffffffff-2000-4000-8000-000000000002', 'ffffffff-3000-4000-8000-000000000001',
          'test.step', 'fake', 'fake-small', 1, 1, 1, 1, 1, 'success')$$, 'app_system'),
  'err:23503', 'usage cannot name a run of a different case/owner');

-- ── the ledger holds counters and codes only ────────────────────────────────────────────────────
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'a prompt with spaces and text', 'fake', 'fake-small', 1, 1, 1, 1, 1, 'success')$$, 'app_system'),
  'err:23514', 'purpose must be a short code, not text');
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'test.step', 'fake', 'fake-small', 1, 1, 1, 1, 1, 'it said: the patient has ...')$$, 'app_system'),
  'err:23514', 'outcome must be a short code, not model output');
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'test.step', 'fake', 'fake-small', 7, 1, 1, 1, 1, 'success')$$, 'app_system'),
  'err:23514', 'tier is 1..3');
select is(tests.try_as(null, $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, cost_micro_usd, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'test.step', 'fake', 'fake-small', 1, 1, 1, -5, 1, 1, 'success')$$, 'app_system'),
  'err:23514', 'cost cannot be negative');

-- ── the system role is write-only here ──────────────────────────────────────────────────────────
select is(tests.try_as(null, $$select * from public.model_usage$$, 'app_system'), 'err:42501', 'app_system cannot read usage back');
select is(tests.try_as(null, $$update public.model_usage set tier = 2$$, 'app_system'), 'err:42501', 'app_system cannot update usage');
select is(tests.try_as(null, $$delete from public.model_usage$$, 'app_system'), 'err:42501', 'app_system cannot delete usage');

-- ── users read only their own rows and never write ──────────────────────────────────────────────
select is(tests.try_as('ffffffff-0000-4000-8000-000000000001', $$select * from public.model_usage$$), 'ok:2', 'an owner sees their own usage rows');
select is(tests.try_as('ffffffff-0000-4000-8000-000000000002', $$select * from public.model_usage$$), 'ok:0', 'another user sees none of it');
select is(tests.try_as('ffffffff-0000-4000-8000-000000000001', $$insert into public.model_usage
  (owner_user_id, case_id, purpose, provider, model, tier, input_tokens, output_tokens, latency_ms, attempts, outcome)
  values ('ffffffff-0000-4000-8000-000000000001', 'ffffffff-2000-4000-8000-000000000001',
          'test.step', 'fake', 'fake-small', 1, 1, 1, 1, 1, 'success')$$), 'err:42501', 'a user cannot write usage');
select is(tests.try_as('ffffffff-0000-4000-8000-000000000001', $$update public.model_usage set tier = 3$$), 'err:42501', 'a user cannot update usage');
select is(tests.try_as(null, $$select * from public.model_usage$$, 'anon'), 'err:42501', 'anon cannot read usage');

-- ── RLS is on and forced; deleting the case removes its usage ───────────────────────────────────
select is((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.model_usage'::regclass), true, 'RLS is enabled and forced');
delete from public.cases where id = 'ffffffff-2000-4000-8000-000000000001';
select is((select count(*)::int from public.model_usage), 0, 'usage is deleted with its case');

select * from finish();
rollback;
