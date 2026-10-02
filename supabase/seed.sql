-- Synthetic seed data for LOCAL development and CI only. Entirely fictional: no real person, no real
-- record. It mirrors the three prototype scenarios in frontend/src/mocks/scenarios/.
--
-- This file contains no credentials. The app_backend login password is NOT set here: set it out of
-- band for local use (see backend/README.md); the integration tests set a random one themselves.
--
-- It runs as the database owner (which bypasses RLS) on `supabase start` / `supabase db reset`.

-- One fictional user, matching the prototype's demo account. The profile row is created by the
-- on_auth_user_created trigger.
insert into auth.users (id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values (
  '00000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'demo@advisorai.test',
  '{"full_name": "Demo User"}'::jsonb, now(), now()
)
on conflict (id) do nothing;

-- Three pseudonymous patients (age and sex only) and their cases.
insert into public.patients (id, owner_user_id, age_years, sex) values
  ('10000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001', 52, 'M'),
  ('10000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', 47, 'F'),
  ('10000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000001', 38, 'M')
on conflict (id) do nothing;

insert into public.cases (id, owner_user_id, patient_id, code, title, concern, proposed_treatment, status) values
  ('20000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001',
   '10000000-0000-4000-8000-000000000001', 'AC-9F2', 'Heart stent decision',
   'Is angioplasty necessary now?', 'Angioplasty (PCI) to the LAD artery', 'complete'),
  ('20000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001',
   '10000000-0000-4000-8000-000000000002', 'AC-K21', 'Knee surgery',
   'Do I really need knee surgery, or is there something missing from my records?',
   'Arthroscopic partial meniscectomy (right knee)', 'partial'),
  ('20000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000001',
   '10000000-0000-4000-8000-000000000003', 'AC-M77', 'Two reports disagree',
   'My MRI report and my discharge summary seem to say different things. What is actually being said?',
   'Follow-up MRI in 3 months and a neurology review', 'complete')
on conflict (id) do nothing;

-- Documents for the cardiology case. storage_path follows owner/case/document. No storage objects
-- exist for these rows: they are metadata only.
insert into public.documents (id, owner_user_id, case_id, type, title, status, storage_path, mime_type, pages)
select d.id, '00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
       d.type, d.title, 'ready',
       '00000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000001/' || d.id,
       d.mime, d.pages
from (values
  ('30000000-0000-4000-8000-000000000001'::uuid, 'consult',  'GP consultation note.pdf',        'application/pdf', 2),
  ('30000000-0000-4000-8000-000000000002'::uuid, 'ecg',      'ECG report, Feb 2026.pdf',        'application/pdf', 1),
  ('30000000-0000-4000-8000-000000000003'::uuid, 'lab',      'HbA1c and lipid panel.pdf',       'application/pdf', 2),
  ('30000000-0000-4000-8000-000000000004'::uuid, 'imaging',  'Coronary angiography report.pdf', 'application/pdf', 3)
) as d (id, type, title, mime, pages)
on conflict (id) do nothing;

-- A few facts, each pointing at a document page and snippet, with the normalised rows that use them.
insert into public.facts (id, owner_user_id, case_id, document_id, type, label, value, flag, fact_date, page, section, snippet, confidence) values
  ('40000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '30000000-0000-4000-8000-000000000001', 'symptom', 'Chest tightness on exertion', 'Climbing stairs, since January', null,
   '2026-01-15', 1, 'History', 'Chest tightness on climbing two flights of stairs for the past few weeks.', 0.900),
  ('40000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '30000000-0000-4000-8000-000000000003', 'lab_result', 'HbA1c', '8.9 %', 'high',
   '2026-03-05', 1, 'Diabetes panel', 'HbA1c 8.9 % (target < 7.0 %) H', 0.970),
  ('40000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '30000000-0000-4000-8000-000000000004', 'diagnosis', 'Coronary artery disease', 'LAD stenosis', null,
   '2026-04-14', 2, 'Conclusion', 'Significant stenosis of the proximal LAD.', 0.930)
on conflict (id) do nothing;

insert into public.timeline_events (owner_user_id, case_id, fact_id, event_date, precision, title, detail) values
  ('00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '40000000-0000-4000-8000-000000000001', '2026-01-15', 'month', 'Chest tightness begins',
   'Tightness on climbing stairs, as described in the GP note.');
insert into public.lab_results (owner_user_id, case_id, fact_id, test_name, value, unit, flag, result_date) values
  ('00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '40000000-0000-4000-8000-000000000002', 'HbA1c', '8.9', '%', 'high', '2026-03-05');
insert into public.diagnoses (owner_user_id, case_id, fact_id, diagnosis_name, status) values
  ('00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
   '40000000-0000-4000-8000-000000000003', 'Coronary artery disease', 'documented');

-- One finished workflow run with its 14 steps (job persistence only: no engine exists yet).
insert into public.workflow_runs (id, owner_user_id, case_id, definition, definition_version, status, progress, started_at, finished_at)
values ('50000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001',
        '20000000-0000-4000-8000-000000000001', 'case_analysis', '1', 'complete', 1,
        '2026-10-02T09:08:00Z', '2026-10-02T09:12:00Z')
on conflict (id) do nothing;

insert into public.workflow_steps (owner_user_id, case_id, run_id, n, node, status)
select '00000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001',
       '50000000-0000-4000-8000-000000000001', n, 'step_' || n, 'done'
from generate_series(1, 14) as n
on conflict (run_id, n) do nothing;
