-- Schema shape, owner columns, composite foreign keys, grants, identity separation, storage setup.
begin;
create extension if not exists pgtap with schema extensions;
select * from no_plan();

-- ── The 16 tables (15 from Phase 2B + model_usage, the AI usage ledger) ───────────────────────────────────────────────────────────────────────────────
select tables_are(
  'public',
  array['profiles', 'patients', 'cases', 'documents', 'document_pages', 'medical_records', 'facts',
        'timeline_events', 'medications', 'lab_results', 'diagnoses', 'procedures',
        'workflow_runs', 'workflow_steps', 'model_usage', 'audit_logs'],
  'public schema has exactly the expected tables'
);

-- ── RLS enabled AND forced on every table ───────────────────────────────────────────────────────
select is(
  (select count(*)::int from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p') and not (c.relrowsecurity and c.relforcerowsecurity)),
  0, 'every public table has RLS enabled and forced'
);

-- ── Owner column on every patient-owned table; audit_logs is the deliberate exception ───────────
select col_not_null('public', t, 'owner_user_id', t || '.owner_user_id is NOT NULL')
from unnest(array['patients', 'cases', 'documents', 'document_pages', 'medical_records', 'facts',
                  'timeline_events', 'medications', 'lab_results', 'diagnoses', 'procedures',
                  'workflow_runs', 'workflow_steps']) as t;
select col_type_is('public', t, 'owner_user_id', 'uuid', t || '.owner_user_id is uuid')
from unnest(array['patients', 'cases', 'documents', 'document_pages', 'medical_records', 'facts',
                  'timeline_events', 'medications', 'lab_results', 'diagnoses', 'procedures',
                  'workflow_runs', 'workflow_steps']) as t;
select col_is_pk('public', 'profiles', 'user_id', 'profiles is keyed by the owning user');

select hasnt_column('public', 'audit_logs', 'owner_user_id', 'audit_logs has no owner column');
select is(
  (select count(*)::int from pg_constraint where conrelid = 'public.audit_logs'::regclass and contype = 'f'),
  0, 'audit_logs has no foreign keys (rows survive deletion of what they describe)'
);

-- ── Composite foreign keys: every child's FK to its parent includes the owner column ────────────
select ok(
  exists (
    select 1 from pg_constraint k
    join pg_attribute a on a.attrelid = k.conrelid and a.attnum = any (k.conkey) and a.attname = 'owner_user_id'
    where k.conrelid = ('public.' || t)::regclass and k.contype = 'f' and cardinality(k.conkey) > 1
  ),
  t || ' references its parent with a composite (..., owner_user_id) foreign key'
)
from unnest(array['cases', 'documents', 'document_pages', 'medical_records', 'facts', 'timeline_events',
                  'medications', 'lab_results', 'diagnoses', 'procedures', 'workflow_runs',
                  'workflow_steps']) as t;

-- ── Identity separation: names, emails and phone numbers exist only in profiles / auth ──────────
select is(
  (select coalesce(string_agg(table_name || '.' || column_name, ', '), '')
     from information_schema.columns
    where table_schema = 'public'
      and not (table_name = 'profiles' and column_name = 'display_name')
      and (column_name ~* '(email|phone|mobile|address|birth|dob|owner_label|first_name|last_name|full_name|patient_name)'
           or column_name = 'name' or column_name = 'display_name')),
  '', 'no identity column exists outside profiles.display_name'
);
select is(
  (select coalesce(string_agg(table_name || '.' || column_name, ', ' order by table_name), '')
     from information_schema.columns
    where table_schema = 'public' and column_name ~ '_name$'
      and (table_name || '.' || column_name) not in
          ('profiles.display_name', 'medications.medication_name', 'lab_results.test_name',
           'diagnoses.diagnosis_name', 'procedures.procedure_name')),
  '', '*_name columns are only profiles.display_name and clinical item names'
);
select has_column('public', 'profiles', 'display_name', 'profiles.display_name exists');
select hasnt_column('public', 'patients', 'display_name', 'patients carry no name');

-- ── Grants ──────────────────────────────────────────────────────────────────────────────────────
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and grantee in ('anon', 'service_role', 'PUBLIC')),
  0, 'anon, service_role and PUBLIC hold no privileges on any public table'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and grantee = 'app_backend'),
  0, 'the backend login role holds no privileges of its own (fail closed)'
);
select is(
  (select coalesce(string_agg(table_name::text || ':' || privilege_type::text, ',' order by table_name::text, privilege_type::text), '')
     from information_schema.role_table_grants
    where table_schema = 'public' and grantee = 'app_system'),
  'audit_logs:INSERT,model_usage:INSERT,workflow_runs:INSERT,workflow_runs:SELECT,workflow_steps:INSERT,workflow_steps:SELECT',
  'app_system holds only the audit INSERT, the model_usage INSERT and the workflow run/step table privileges'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'audit_logs'
      and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE')
      and grantee not in ('postgres', 'supabase_admin')),
  0, 'nobody but the owner holds UPDATE/DELETE/TRUNCATE on audit_logs'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and grantee = 'authenticated'
      and table_name in ('document_pages', 'medical_records', 'facts', 'timeline_events', 'medications',
                         'lab_results', 'diagnoses', 'procedures', 'workflow_runs', 'workflow_steps')
      and privilege_type <> 'SELECT'),
  0, 'derived tables are read-only for authenticated'
);
select is(
  (select count(*)::int from pg_roles
    where rolname in ('app_backend', 'app_system') and (rolsuper or rolbypassrls)),
  0, 'app_backend and app_system are neither superuser nor BYPASSRLS'
);
select is((select rolinherit from pg_roles where rolname = 'app_backend'), false, 'app_backend is NOINHERIT');
select is((select rolcanlogin from pg_roles where rolname = 'app_system'), true, 'app_system is its own login role (a separate connection from app_backend)');

-- The system path is unreachable from user context: no SET ROLE route from app_backend / authenticated.
select is(pg_has_role('app_backend', 'app_system', 'member'), false, 'app_backend is NOT a member of app_system (no SET ROLE to it)');
select is(pg_has_role('authenticated', 'app_system', 'member'), false, 'authenticated cannot reach app_system');
select is(pg_has_role('anon', 'app_system', 'member'), false, 'anon cannot reach app_system');
select is(pg_has_role('service_role', 'app_system', 'member'), false, 'service_role is not a member of app_system');
select is(
  (select count(*)::int from pg_auth_members m join pg_roles u on u.oid = m.member where u.rolname = 'app_system'),
  0, 'app_system is not a member of any role');
select is(
  (select coalesce(string_agg(r, ', '), '') from unnest(array['postgres', 'service_role', 'anon', 'supabase_admin', 'app_system']) r
    where case when exists (select from pg_roles where rolname = r)
                then pg_has_role('app_backend', r, 'member') else false end),
  '', 'app_backend can become none of the privileged roles');
select is(
  (select coalesce(string_agg(r, ', '), '') from unnest(array['authenticated']) r where pg_has_role('app_backend', r, 'member')),
  'authenticated', 'app_backend can become exactly one role: authenticated (the user context)');

-- ── Every non-audit table has at least one policy; audit_logs has no client policy ──────────────
select is(
  (select count(*)::int from pg_tables t
    where t.schemaname = 'public' and t.tablename <> 'audit_logs'
      and not exists (select 1 from pg_policies p where p.schemaname = 'public' and p.tablename = t.tablename)),
  0, 'every table except audit_logs has an RLS policy'
);
select is(
  (select count(*)::int from pg_policies
    where schemaname = 'public' and tablename = 'audit_logs'
      and not ('app_system' = any (roles) and cmd = 'INSERT')),
  0, 'audit_logs has no policy except INSERT for app_system'
);

-- ── Storage: private bucket, limits, no client access ───────────────────────────────────────────
select is((select public from storage.buckets where id = 'case-documents'), false, 'case-documents is private');
select is((select file_size_limit from storage.buckets where id = 'case-documents'), 20971520::bigint, 'case-documents is limited to 20 MB');
select is(
  (select allowed_mime_types from storage.buckets where id = 'case-documents'),
  array['application/pdf', 'image/jpeg', 'image/png'], 'case-documents allows only PDF, JPEG and PNG'
);
select is(
  (select count(*)::int from pg_policies
    where schemaname = 'storage' and tablename = 'objects' and policyname = 'case_documents_backend_only'
      and permissive = 'RESTRICTIVE'),
  1, 'a RESTRICTIVE policy keeps anon/authenticated out of the case-documents bucket'
);

select * from finish();
rollback;
