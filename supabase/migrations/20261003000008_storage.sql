-- Phase 2B / 8 of 8: the private case-documents bucket.
--
-- The bucket is private, limited to 20 MB and to PDF / JPEG / PNG. Clients get NO direct access to
-- it: not through the anon key, not through a user JWT. The backend alone issues short-lived signed
-- URLs (5 minutes for downloads) after it has checked ownership under RLS, and it audits every URL it
-- issues. Object path convention (also enforced on documents.storage_path):
--   {owner_user_id}/{case_id}/{document_id}

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('case-documents', 'case-documents', false, 20971520,
        array['application/pdf', 'image/jpeg', 'image/png'])
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- No permissive policy grants anon/authenticated access to storage.objects for this bucket, so the
-- default is deny. This RESTRICTIVE policy makes the intent explicit and keeps a future, careless
-- permissive policy from opening the bucket: a restrictive policy must pass in addition to any
-- permissive one.
drop policy if exists case_documents_backend_only on storage.objects;
create policy case_documents_backend_only on storage.objects
  as restrictive for all to anon, authenticated
  using (bucket_id <> 'case-documents')
  with check (bucket_id <> 'case-documents');
