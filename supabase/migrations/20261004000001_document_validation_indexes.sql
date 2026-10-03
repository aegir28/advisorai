-- Phase 2C / 1: support for upload validation (no AI, no OCR).
--
-- * Duplicate detection looks up a document by (case, content hash). One READY document per content
--   hash per case is also a database guarantee, so two uploads finishing at the same moment cannot both
--   become 'ready' (the backend marks the loser 'duplicate').
-- * Uploads that never completed ('pending_upload') are found by age so they can be cleaned up.
--
-- No grants or policies change: RLS on documents already scopes everything to the owner.

create unique index documents_one_ready_per_hash
  on public.documents (case_id, sha256)
  where status = 'ready' and sha256 is not null;

create index documents_pending_upload_idx
  on public.documents (created_at)
  where status = 'pending_upload';
