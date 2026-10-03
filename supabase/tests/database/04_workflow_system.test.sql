-- Phase 2D: the system path for workflow runs and steps. What app_system may and may not do, and that a user
-- session still cannot write either table.
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
  ('eeeeeeee-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'e1@advisorai.test'),
  ('eeeeeeee-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'e2@advisorai.test');
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('eeeeeeee-1000-4000-8000-000000000001', 'eeeeeeee-0000-4000-8000-000000000001', 40, 'F'),
  ('eeeeeeee-1000-4000-8000-000000000002', 'eeeeeeee-0000-4000-8000-000000000002', 41, 'M');
insert into public.cases (id, owner_user_id, patient_id, code, concern) values
  ('eeeeeeee-2000-4000-8000-000000000001', 'eeeeeeee-0000-4000-8000-000000000001', 'eeeeeeee-1000-4000-8000-000000000001', 'AC-E1', 'synthetic'),
  ('eeeeeeee-2000-4000-8000-000000000002', 'eeeeeeee-0000-4000-8000-000000000002', 'eeeeeeee-1000-4000-8000-000000000002', 'AC-E2', 'synthetic');

-- ── The system role can enqueue and drive a run ─────────────────────────────────────────────────
select is(tests.try_as(null, $$insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version)
  values ('eeeeeeee-3000-4000-8000-000000000001', 'eeeeeeee-0000-4000-8000-000000000001',
          'eeeeeeee-2000-4000-8000-000000000001', 'case_analysis', '1')$$, 'app_system'),
  'ok:1', 'app_system can enqueue a run');
select is(tests.try_as(null, $$insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node)
  values ('eeeeeeee-0000-4000-8000-000000000001', 'eeeeeeee-2000-4000-8000-000000000001',
          'eeeeeeee-3000-4000-8000-000000000001', 1, 'classify')$$, 'app_system'),
  'ok:1', 'app_system can create a step');
select is(tests.try_as(null, $$update public.workflow_runs set status = 'running', locked_by = 'w1',
  locked_until = now() + interval '60 seconds', attempts = attempts + 1
  where id = 'eeeeeeee-3000-4000-8000-000000000001'$$, 'app_system'),
  'ok:1', 'app_system can claim (lease) a run');
select is(tests.try_as(null, $$update public.workflow_steps set status = 'done', input_hash = repeat('b', 64)
  where run_id = 'eeeeeeee-3000-4000-8000-000000000001'$$, 'app_system'),
  'ok:1', 'app_system can record a step result and its input hash');

-- ── ...but not rewrite what a run is, or reach case data ────────────────────────────────────────
select is(tests.try_as(null, $$update public.workflow_runs set owner_user_id = 'eeeeeeee-0000-4000-8000-000000000002'
  where id = 'eeeeeeee-3000-4000-8000-000000000001'$$, 'app_system'),
  'err:42501', 'app_system cannot change a run''s owner (no column grant)');
select is(tests.try_as(null, $$update public.workflow_runs set case_id = 'eeeeeeee-2000-4000-8000-000000000002'
  where id = 'eeeeeeee-3000-4000-8000-000000000001'$$, 'app_system'),
  'err:42501', 'app_system cannot move a run to another case');
select is(tests.try_as(null, $$update public.workflow_runs set definition = 'other' where true$$, 'app_system'),
  'err:42501', 'app_system cannot change a run''s definition');
select is(tests.try_as(null, $$select * from public.cases$$, 'app_system'),
  'err:42501', 'app_system cannot read cases');
select is(tests.try_as(null, $$select * from public.documents$$, 'app_system'),
  'err:42501', 'app_system cannot read documents');
select is(tests.try_as(null, $$delete from public.workflow_runs$$, 'app_system'),
  'err:42501', 'app_system cannot delete runs');
select is(tests.try_as(null, $$insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version)
  values (gen_random_uuid(), 'eeeeeeee-0000-4000-8000-000000000001', 'eeeeeeee-2000-4000-8000-000000000002', 'x', '1')$$,
  'app_system'),
  'err:23503', 'a run cannot pair one owner with another owner''s case (composite foreign key)');

-- ── Users still cannot write either table, and see only their own rows ──────────────────────────
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000001', $$insert into public.workflow_runs
  (owner_user_id, case_id, definition, definition_version)
  values ('eeeeeeee-0000-4000-8000-000000000001', 'eeeeeeee-2000-4000-8000-000000000001', 'x', '1')$$),
  'err:42501', 'a user cannot insert a run');
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000001', $$update public.workflow_runs set status = 'complete'$$),
  'err:42501', 'a user cannot update a run');
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000001', $$update public.workflow_steps set status = 'done'$$),
  'err:42501', 'a user cannot update a step');
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000001', $$select * from public.workflow_runs$$),
  'ok:1', 'a user sees their own run');
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000002', $$select * from public.workflow_runs$$),
  'ok:0', 'another user sees none of it');
select is(tests.try_as('eeeeeeee-0000-4000-8000-000000000002', $$select * from public.workflow_steps$$),
  'ok:0', 'nor its steps');
select is(tests.try_as(null, $$select * from public.workflow_runs$$, 'anon'),
  'err:42501', 'anon cannot read runs');

-- (That app_system cannot SET ROLE to anything is asserted by role membership in 01 and by migration 7;
-- this session is a superuser, for which SET ROLE always succeeds, so it cannot test that here.)
select is(tests.try_as(null, $$select count(*) from public.audit_logs$$, 'app_system'), 'err:42501',
  'app_system still cannot read the audit log');

select * from finish();
rollback;
