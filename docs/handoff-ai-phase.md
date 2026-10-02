# Handoff: starting the AI / API-key phase

Read first: the architecture blueprint (Part 2 agentic AI, Part 3 reasoning & verification, Part 5 AI
infrastructure, Part 7 engineering), then ADRs 0004-0010. This document says what is ready, what is not, and the
order to start in.

## State at handoff

| Area | State |
| --- | --- |
| Database | 10 migrations, 15 tables, RLS enabled + forced everywhere, composite owner FKs, append-only audit, private bucket, synthetic-only `CHECK`s. Migrations assert their own invariants. |
| Auth | Google via Supabase Auth wired (frontend adapter, JWKS verification, consent on the profile). **Provider disabled in `config.toml`; a live Google round-trip was not exercised.** Mock auth stays the default. |
| API | `/me`, `/me/consent`, `/cases` (CRUD, safety check), `/cases/{id}/documents` (signed upload, validate, list, remove), `/analysis/{run_id}`. |
| Upload | Two-step signed-URL upload; server-side validation (real type from bytes, size, SHA-256, pages, duplicates). No OCR. |
| Workflow | Definitions, lease-based queue, engine (retry/timeout/idempotent), worker (off by default), run/step persistence. **Zero node types registered.** |
| Frontend | Switchable mock ↔ HTTP; AI-dependent calls answer "no results" / `ApiNotAvailableError`. |
| Security | RLS everywhere, request-scoped user context, separate `app_system` login with narrow grants, security headers, body limit, secrets hygiene tests, repo guards. |
| CI | `backend`, `frontend`, `supabase` (real stack), `guards`. |

## Recommended starting point (in this order)

1. **First PR: ADR + relax the `ai-scope` guard + the AI gateway skeleton, with a mocked provider.**
   - ADR 0011: provider choice (blueprint: OpenAI behind a provider-agnostic adapter), model map (`registry/models.yaml`,
     tier 1/2/3), budget (≈ ₹5,000), de-identification rules, `store=false`.
   - Remove/relax the `ai-scope` rule in `scripts/repo_guards.py` and its tests in the same PR.
   - `backend/app/ai/`: `gateway.py` (de-identify → meter → validate → call), `model_router.py`, `adapters/openai.py`
     behind a `Provider` protocol, and a **recorded-response fake provider** so tests stay free (blueprint p. 53).
   - Migration: `model_usage` (+ RLS; written on the system path, new `SystemOperation`), audit `ai.call`.
   - Provider key: `ADVISORAI_OPENAI_API_KEY` as `SecretStr` in `Settings`, backend environment only, added to
     `.env.example` empty and to production-required settings. Never in the frontend, never logged (extend the log
     redactor to its prefix).
   - **De-identification first.** `cases.concern`, `cases.proposed_treatment` and `documents.title` are free text a
     person typed and can contain identity. They must pass through `safety/deidentify.py` before reaching any prompt.
2. **Phase 7: extraction (Milestone A: upload → extracted case → timeline, no specialist AI).**
   - Local text/OCR first (PyMuPDF / pdfplumber / Tesseract; blueprint p. 41), vision fallback behind the gateway.
   - Node types `docintel.*` and `ai.classify_docs` / `ai.extract_facts`; write `document_pages`, `facts`,
     `timeline_events`, `medications`, `lab_results`, `diagnoses`, and the `case.v1` snapshot in `medical_records`.
     These tables exist with RLS; nothing writes them yet, so each write path needs a system operation + grants.
   - Author `workflows/case_analysis.v1.yaml` (14 nodes) and register the node types; add
     `POST /cases/{id}/analysis` (`202 + run_id`) calling `WorkflowService.enqueue_analysis`; flip
     `ADVISORAI_WORKER_ENABLED` on; replace `startAnalysis` / `getTimeline` in `createHttpApi`.
3. Then blueprint phases 8-11 in order (router + 5 specialists, evidence / `pgvector` / verifier / cross-review,
   questions, reviewer + patient report), 12 (PDF), 14 (benchmark scorer on `evals/`), each gated by its benchmark.

Do not skip 1: the gateway is the only door to a provider, and de-identification is a precondition, not a feature.

## Things the next phase inherits (known gaps, none hidden)

- **Not verified against the real stack in the build environment:** `supabase start` / `db reset` / `db lint` /
  `test db` and the two Storage API integration tests (images could not be pulled). Everything else was run on
  native PostgreSQL 16 with stubbed `auth`/`storage` (`supabase/tests/native/`). **Check the `supabase` CI job result
  first.** The browser's multipart `PUT` to a real signed upload URL and a live Google round-trip are also unverified.
- Docker image not built (registry rate limit); the start command was run natively.
- Per-user **rate limiting** is not implemented. Add before any public exposure.
- **Stale `pending_upload` sweep** (indexed, not scheduled): a worker task once real workflows exist.
- **Admin role + `/admin/metrics`**: not defined; observability queries in `docs/observability.md` stand in.
- `run.v1` has exactly 14 steps; a definition served through `/analysis` must have 14 nodes.
- `queued` is internal and presented as `running` with progress 0 (ADR 0008).
- Audit of completed operations is best-effort (ADR 0007); the audit row for a released signed URL is not.
- `ADVISORAI_DATA_MODE` accepts only `synthetic_only`; real data needs a migration + ADR (ADR 0004).
- Benchmark ground truth is bootstrapped from the prototype's fictional fixtures, not clinician-reviewed.

## Commands

```bash
# database + backend (real stack, where Docker works)
supabase start -x studio,imgproxy && supabase db reset && supabase test db
cd backend && uv sync --locked --extra dev && uv run --no-sync pytest
# without Docker: the labelled substitute
supabase/tests/native/run.sh up && supabase/tests/native/run.sh pgtap
# frontend
cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build
# repo guards + benchmark data
python scripts/repo_guards.py && (cd backend && uv run --no-sync python ../evals/validate.py)
```
