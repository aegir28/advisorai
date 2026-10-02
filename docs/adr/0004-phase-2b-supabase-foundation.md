# ADR 0004: Phase 2B, the Supabase foundation (scope and decisions)

- Status: accepted
- Date: 2026-10-02
- Scope: `supabase/`, `backend/app/{db,auth,storage,audit}`, CI

## Approved decisions

1. **Authentication.** Google only for real product authentication (Phase 2C builds it). Local test
   users may use email/password or locally minted test tokens in development and tests only.
2. **Database access.** FastAPI connects directly to Postgres. RLS stays enforced for user-scoped
   operations ([ADR 0005](0005-database-user-context.md)). PostgREST is not the backend data layer, and
   the Data API is switched off for this project (`[api] enabled = false`), so the only door to the data
   is FastAPI.
3. **Migrations.** `supabase/migrations/*.sql` is the single source of truth. No Alembic.
4. **JWT.** Supabase JWTs are verified with the project's JWKS asymmetric keys: signature, expiry,
   issuer, `aud = authenticated` and `sub`. Symmetric (HS*) tokens are rejected.
5. **Facts.** A normalised `facts` table is added. The other `case.v1` sections stay in the JSON
   `medical_records` snapshot until a later phase needs them normalised.
6. **Synthetic data.** `ADVISORAI_DATA_MODE=synthetic_only` is the only accepted value. The database
   enforces it too: `is_synthetic` columns carry `CHECK (is_synthetic)`, so unlocking real data needs a
   deliberate migration and an ADR, not a flag.
7. **Storage.** Private `case-documents` bucket. Backend-issued signed URLs only; download URLs last at
   most 5 minutes. Signed URLs and JWTs are never logged.
8. **Audit.** Append-only `audit_logs`; no medical content; the client IP is stored only as an HMAC
   with a server-side secret.
9. **CI.** The local Supabase stack runs in CI, with pgTAP/RLS tests and the backend integration tests.
10. **Patient model.** One `patients` row per case for the MVP (enforced by `UNIQUE (patient_id)` on
    `cases`; the schema stays 1:N-capable).

## Corrections applied

- **Owner column on every patient-owned table.** `owner_user_id uuid NOT NULL` is explicit on
  `patients, cases, documents, document_pages, medical_records, facts, timeline_events, medications,
  lab_results, diagnoses, procedures, workflow_runs, workflow_steps`. `audit_logs` is the deliberate
  exception (it must survive deletion and has no ownership FK). Child rows use **composite foreign
  keys** `(parent_id, case_id, owner_user_id)`, so a child row cannot belong to a different owner than
  its parent, whatever RLS says. Tests prove it.
- **`queued` stays internal.** `workflow_runs.status` is `queued | running | complete | partial |
  failed`. It is **not** mapped to `running`, and `run.v1` is not versioned. No API exposes
  `workflow_runs` in this phase, so the contract question is deferred until the workflow API is defined.
- **`pending_upload` stays internal.** `documents.status` includes it. No API in this phase returns
  documents, so an incomplete upload is never exposed.
- **Explicit database user context** for direct Postgres access: see ADR 0005.

## Scope

**In:** local Supabase project, 8 forward-only migrations, 15 tables, RLS, private bucket policies,
backend DB integration, JWKS JWT verification, `CurrentUser`, `GET /api/v1/me`,
`GET /api/v1/health/ready`, audit writer, signed-URL gateway, pgTAP and integration tests, a Supabase
CI workflow, synthetic seed data.

**Out:** Google OAuth, frontend authentication, the document upload API, OCR, MIME sniffing, SHA dedupe,
extraction, workflow engine, AI gateway, OpenAI, specialist agents, `pgvector`, evidence retrieval,
persistence of reports, questions or second opinions.

## Tables

| Table | Owner column | Notes |
| --- | --- | --- |
| `profiles` | `user_id` (= the owner) | The only place a name lives. |
| `patients` | `owner_user_id` | Pseudonymous: `age_years`, `sex`. No name. |
| `cases` | `owner_user_id` | Pseudonymous `code`. |
| `documents` | `owner_user_id` | `storage_path` is checked to equal `owner/case/document`. |
| `document_pages` | `owner_user_id` | Schema only; nothing writes it yet. |
| `medical_records` | `owner_user_id` | `case.v1` JSON snapshot; identity keys are rejected by a `CHECK`. |
| `facts` | `owner_user_id` | Provenance root: document, page, snippet. |
| `timeline_events`, `medications`, `lab_results`, `diagnoses`, `procedures` | `owner_user_id` | Each links to a `facts` row. |
| `workflow_runs`, `workflow_steps` | `owner_user_id` | Job persistence for the later pipeline. No engine. |
| `audit_logs` | none | Append-only; no foreign keys. |

## Choices made while implementing (flagged for review)

- **No `latest_run_id` on `cases`.** It would make `cases` and `workflow_runs` reference each other. The
  latest run is the newest `workflow_runs` row for the case.
- **No `*.name` columns.** `documents.title` (a user-visible label that can carry personal details) and
  clinical `medication_name` / `test_name` / `diagnosis_name` / `procedure_name` are the only name-like
  columns; a pgTAP test pins that list, so a new identity column cannot slip in.
- **Deleting a case deletes its patient** (a trigger), so nothing is orphaned under the 1:1 model.
- **The Data API is disabled** in `config.toml` (`[api] enabled = false`), not just left unused.
- **`service_role` has no grants on public tables**; the backend never uses it for data. It is used only for
  Storage API calls.
- **Storage has no client policy at all** and one RESTRICTIVE policy that keeps `anon`/`authenticated` out
  of the bucket even if a permissive policy is added later.
- **`app_system` holds one grant** (`INSERT` on `audit_logs`) and is a separate login: a user session
  cannot reach it (a residual risk found in testing was fixed; see ADR 0005).
- **Free text is sensitive.** `cases.concern`, `cases.proposed_treatment` and `documents.title` are typed by
  people and can contain identifying details. They are never AI context and must be de-identified before any
  AI step exists.

## Consequences

- The backend role (`app_backend`) has **no privileges of its own**. Forgetting to set a context fails
  closed.
- Two writers are possible: the signed-in user (RLS applies, login `app_backend`) and a narrow `app_system`
  **login on its own connection pool** whose only grant in this phase is `INSERT` on `audit_logs`. The user
  path cannot become the system role (ADR 0005).
- Adding real patient data later is a conscious, reviewable change, not a configuration toggle.
