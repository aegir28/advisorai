# ADR 0007: Case and document lifecycle (Phase 2C)

- Status: accepted
- Date: 2026-10-04
- Scope: `backend/app/{api,services,db,docintel,safety}`, `supabase/migrations/20261004000001_*`

Blueprint references: API structure (p. 52), phase 4 (case creation, safety gate) and phase 5 (private
bucket, signed URLs, validation), failure handling (p. 38: "duplicate / unsupported file: skip with message /
reject upload"), audit logging (p. 37).

## Endpoints (all under `/api/v1`, all require a verified Bearer token)

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/cases/safety-check` | Rule-based red-flag screen. Stateless; nothing stored or logged. |
| `POST` | `/cases` | Creates a pseudonymous patient + case. Status starts as `awaiting_upload`. |
| `GET` | `/cases`, `/cases/{id}` | The caller's cases only. |
| `DELETE` | `/cases/{id}` | Purge order below. `204`. |
| `GET` | `/cases/{id}/documents` | Never returns `pending_upload` rows. |
| `POST` | `/cases/{id}/documents/upload-url` | Declared name/type/mime/size validated; row `pending_upload`; signed upload URL. |
| `POST` | `/cases/{id}/documents/{doc}/complete` | Server-side validation (below). Idempotent. |
| `DELETE` | `/cases/{id}/documents/{doc}` | Removes the file, then the row. |

**Deviation from the blueprint table:** the blueprint lists `POST /cases/{id}/safety-check`. The existing
frontend contract (`AdvisorApi.safetyCheck`) takes only the typed text and ticked symptoms, and the screen runs
**before a case exists**, so the endpoint is `POST /cases/safety-check` (no id). The rules and the response
shape are unchanged.

`POST /cases/{id}/analysis` and everything under `/runs/*` are **not** built: they need the AI pipeline.

## Decisions

1. **The owner is never input.** No route or body accepts a user or owner ID (`extra="forbid"` on every
   request model; a test posts an `owner_user_id` and expects `422`). Every repository query also filters by
   the verified caller, in addition to RLS.
2. **Not yours = not found.** Another person's case or document answers `404`, identical to a missing one.
3. **The storage path is derived, never supplied.** `StoragePath(owner, case, document)` is the only way to
   build one, and `documents.storage_path` is checked by the database to equal that layout.
4. **Two-step upload; the file never passes through the API on the way in.** The browser PUTs to the signed
   URL. `complete` then reads the object back with the service key (capped at 20 MB) and validates it.
5. **Validation is technical only (`docintel/validate.py`):** size (≤ 20 MB, non-empty), the **real type from
   the magic bytes** (the declared type and the file name are untrusted), SHA-256, and page count (PDF via
   `pypdf`; images are one page). Encrypted, damaged or > 300-page PDFs are refused. **No OCR, no text
   extraction, no AI.** Notes shown to the person are fixed strings, never derived from file content.
6. **Document status.** `ready` = passed validation and is available to the later pipeline (it does *not*
   mean it has been read). `duplicate` = same hash already `ready` in the same case (a partial unique index
   makes this a database guarantee under concurrency). `needs_attention` = rejected, with a note.
   `processing` is reserved for the extraction phase. `pending_upload` stays internal.
7. **Rejected and duplicate files are deleted from storage**; the row stays so the person sees why.
8. **Case status.** Create → `awaiting_upload`. Documents do not change it. `processing`, `complete`,
   `partial`, `failed` are set by the workflow (next phase).
9. **Delete = purge order (blueprint WF05).** (a) mark `deletion_requested_at` (the case disappears from reads
   and takes no new uploads), (b) delete every file, (c) delete the rows (cascade; the patient goes with the
   case), (d) audit. If (b) fails the response is `503 STORAGE_UNAVAILABLE`, the rows are kept (still hidden)
   and **the same `DELETE` can be retried**. A case with no documents needs no storage at all.
10. **Audit of completed operations is best-effort** (`AuditWriter.record_completed`): once a create/delete/
    upload has committed it cannot be undone and a `500` would misreport it, so a failed audit write is logged
    at `ERROR` (action + request ID, no content) and does not fail the request. Where the audit row must exist
    *before* something is released (a signed URL), `record` still fails the request. Audit rows hold ids,
    action and time only; free text (`concern`, document names) is never audited or logged.
11. **Contract.** `CaseSummary` and `DocumentItem` are request/response models, not versioned agent contracts.
    `owner_label` and `specialty_label` (prototype display strings) are not sent by the backend; `pages` is
    optional (unknown for a rejected file). The frontend schema makes the same fields optional.

## Not done here, and why

- Stale `pending_upload` rows (an upload URL that was never used) are indexed for a sweep
  (`documents_pending_upload_idx`) but no sweeper runs yet; it belongs with the background worker.
- Per-user rate limiting is not implemented; the document-per-case cap (`ADVISORAI_MAX_DOCUMENTS_PER_CASE`)
  bounds storage use. Add a limiter before any public exposure.
- Supabase signed upload URLs have a fixed lifetime set by the Storage service; it cannot be shortened from
  the backend. The URL is a bearer capability for exactly one object path and is never logged or audited.
