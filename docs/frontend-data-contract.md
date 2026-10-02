# Frontend data contract

The frontend talks to "the backend" only through the `AdvisorApi` interface in
[`frontend/src/lib/api/types.ts`](../frontend/src/lib/api/types.ts). Phase 1 implements it with an
in-browser mock ([`frontend/src/mocks/mock-api.ts`](../frontend/src/mocks/mock-api.ts)). The future
FastAPI backend must return the same shapes so no screen has to change.

To swap in the real backend, write an `httpApi` that implements `AdvisorApi` and select it in
`frontend/src/lib/api/index.ts` (for example when `NEXT_PUBLIC_API_MODE=http`).

## One source of truth: the schemas

Every shape is declared **once**, as a Zod schema, in
[`frontend/src/domain/schemas.ts`](../frontend/src/domain/schemas.ts). The TypeScript types in
`frontend/src/domain/types.ts` are **inferred** from those schemas, so a type and its runtime
validator cannot drift apart.

Every `AdvisorApi` response is parsed against its schema by
[`frontend/src/lib/api/validate.ts`](../frontend/src/lib/api/validate.ts) before it reaches a
screen. Malformed data (from the mock or from the backend) throws a `ContractError`, which the data
hooks surface as the normal error state. One table (`RESPONSE_SCHEMAS`) maps each method to its
schema; a test fails if a method is missing from it.

## Versioned contracts

| Contract | `schema_version` | Where |
| --- | --- | --- |
| Canonical structured case | `case.v1` | `CaseV1Schema` (the backend stores it; agents read pseudonymous slices of it) |
| Specialist report | `specialist_report.v1` | each item of `getPerspectives().reports` |
| Patient report | `report.v1` | `getReport()` |
| Trace | `trace.v1` | `getTrace()` |
| Analysis run | `run.v1` | `getRun()` |

There is no `v2`. A change that is not backward compatible needs an ADR first.

### Casing

The **wire** format is snake_case throughout ([ADR 0001](adr/0001-wire-casing.md)); the backend
does not use an alias generator. This file's schemas describe the frontend **domain** model, which
keeps the camelCase names Phase 1 already used (`factRefs`, `routingReason`, `evidenceIds`, `caseId`
on the report and run, ...) next to its snake_case envelope fields. The explicit adapter
[`frontend/src/lib/api/http/casing.ts`](../frontend/src/lib/api/http/casing.ts) converts at the API
boundary: `backend wire -> Pydantic -> httpApi adapter -> domain model -> UI`.

### `specialist_report.v1`

`schema_version`, `run_id`, `case_id`, specialty identity (`specialist`, `name`, `version`,
`tier`, `priority`), `findings`, `uncertainties`, `missing_info`, `contradictions`,
`considerations`, `questions`, `evidence_refs`, `confidence`, `limitations`, optional
`extensions`, plus the Phase 1 fields `routingReason`, `status`, `statusNote`.

### Contract rules enforced by the schemas

- A report has exactly the 19 blueprint sections, numbered 1..19 in order.
- Every non-template report sentence has an `id` and at least one `evidenceIds` entry. Only fixed
  template text (disclaimers, "nothing found" notes) may be untraced.
- A run has exactly the 14 workflow steps, numbered 1..14. A `failed` run must carry `failure`.
- `case.v1` contains no identity fields: names, phone and email never appear in it.

## Backend (Phase 2A to 2E)

[`backend/`](../backend/README.md) is a FastAPI service on a Supabase Postgres foundation (RLS, private storage,
audit log; [ADR 0004](adr/0004-phase-2b-supabase-foundation.md)). So far it serves `GET /api/v1/health`,
`GET /api/v1/health/ready`, `GET /api/v1/me` (Bearer token; the caller's own profile, never an ID from the client),
OpenAPI at `/api/v1/docs`, the error contract and request IDs, and carries Pydantic v2 models for the
five versioned contracts (`backend/app/schemas/`). Served since Phase 2C-2E: cases (create, list, get, delete), the
red-flag check, documents (secure upload, library, remove) and run status (`GET /analysis/{run_id}`); see
[ADR 0007](adr/0007-case-and-document-lifecycle.md), [ADR 0008](adr/0008-workflow-persistence-and-worker.md) and
[ADR 0009](adr/0009-google-auth-and-frontend-http-integration.md). Everything that needs the AI pipeline (start an
analysis, timeline, perspectives, report, questions, trace, second opinion, comparison) is **not built**: the
frontend's `httpApi` answers "no results" or `ApiNotAvailableError`, never fake data. The red-flag check is
`POST /cases/safety-check` (no case id: it runs before a case exists).

### Optional means absent, never null

`.optional()` accepts a missing key and rejects `null`; the Pydantic models behave identically
([ADR 0001](adr/0001-wire-casing.md)). Send or omit, never `null`.

### Error contract

Every error is `{"error": {"code", "message", "request_id", "details"}}`
([ADR 0002](adr/0002-error-contract.md)). The frontend turns it into an `ApiError`
(`code`, `message`, `requestId`, `details`). Send `X-Request-ID` to correlate; it is echoed on every
response.

### Fixtures shared by both sides

`npm run export:fixtures` (in `frontend/`) writes the three synthetic scenarios, in wire form, to
`backend/tests/fixtures/contracts/`. Backend tests validate them with Pydantic; a frontend test
fails if they drift from the scenarios.

## Endpoint mapping (`/api/v1`)

| `AdvisorApi` method | HTTP |
| --- | --- |
| `listCases`, `getCase`, `getCaseOverview` | `GET /cases`, `GET /cases/{id}` |
| `createCase`, `deleteCase` | `POST /cases`, `DELETE /cases/{id}` |
| `safetyCheck` | `POST /cases/{id}/safety-check` (must run **before** a case or analysis exists in the UI flow) |
| `getDocuments`, `uploadDocument`, `removeDocument` | `GET /cases/{id}/documents`, signed upload URL + complete |
| `startAnalysis` | `POST /cases/{id}/analysis` returns `202` + `run_id` |
| `getRun` | `GET /analysis/{run_id}` (status and steps only, never content) |
| `getTimeline` | `GET /cases/{id}/timeline` |
| `getPerspectives`, `getEvidence`, `getCrossReview`, `getSynthesis` | `GET /runs/{run_id}/...` |
| `getReport` | `GET /runs/{run_id}/report` |
| `getQuestions`, `updateQuestion` | `GET /runs/{run_id}/questions`, `PATCH` for tracking status and notes |
| `getTrace` | `GET /runs/{run_id}/trace/{item_id}` |
| `submitSecondOpinion`, `getSecondOpinion`, `getComparison` | `POST /cases/{id}/second-opinions`, `GET /cases/{id}/comparison` |

`AdvisorApi` is the **production** contract: it contains nothing that is specific to the mock.

## Prototype-only controls

Picking a fictional sample case, forcing a partial or failed run, and skipping the simulated wait
are demo features. They are **not** part of `AdvisorApi`. They live in a separate
`PrototypeControls` object (`frontend/src/lib/prototype.ts`) that is `null` when
`NEXT_PUBLIC_API_MODE=http`, so these affordances vanish in production without screen changes.
`CaseSummary.scenario` is likewise optional and prototype-only.

## Data the UI needs

- **Case**: pseudonymous `code`, optional short `title`, age, sex, concern, proposed treatment,
  status. Names never appear on case screens.
- **Run**: `status` (`running | complete | partial | failed`) and 14 steps, each
  `pending | running | done | warning | failed | skipped` with an optional plain-language note.
  The UI groups the 14 steps into five patient-facing stages
  (`frontend/src/lib/analysis-groups.ts`); the step list itself must stay stable.
- **Facts** carry provenance: `source = { docId, page, section, snippet }`.
- **Trace**: for any item ID (report sentence, finding, claim, fact, timeline event, question,
  comparison row) a tree from the statement down to the document page and reference source.
- **Verification**: `supported | partially_supported | unclear | contradicted | insufficient_evidence`,
  plus removed claims (kept visible, with a reason).
- **Cross-review**: matrix rows with a stance per specialist and a relationship. No scores, no winner.
- **Questions**: priority 1-3, audience, trigger text, linked item IDs and tracking status
  (`not_asked | partially_answered | answered`) with an optional note.
- **Comparison**: rows with both opinions, evidence for each and a relationship
  (`agreement | differs | new_info | changed | unresolved`). Never a verdict.

## Invariants the backend must keep

1. Every patient-facing sentence has an item ID that resolves in `getTrace`, except fixed template text.
2. Uncertainty, missing information and disagreement are returned, not dropped.
3. Failed or incomplete agents are reported (`status`, `statusNote`), never silently omitted.
4. No directive or verdict language in any returned text (see the blueprint's safety lint).

## Tests

`npm test` (Vitest) also covers the HTTP boundary (`src/__tests__/http/`) and the fixture export
(`src/__tests__/fixtures/`); the backend has its own suite (`pytest`, see `backend/README.md`).
Before that, `npm test` proves the three synthetic scenarios conform to every contract, that every ID
resolves, that malformed data is rejected, and that `AdvisorApi` has no mock-only members. See
`frontend/src/__tests__/contracts/`.
