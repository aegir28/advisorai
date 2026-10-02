# Frontend data contract

The frontend talks to "the backend" only through the `AdvisorApi` interface in
[`frontend/src/lib/api/types.ts`](../frontend/src/lib/api/types.ts). Phase 1 implements it with an
in-browser mock ([`frontend/src/mocks/mock-api.ts`](../frontend/src/mocks/mock-api.ts)). The future
FastAPI backend must return the same shapes (typed in
[`frontend/src/domain/types.ts`](../frontend/src/domain/types.ts)) so no screen has to change.

To swap in the real backend, write an `httpApi` that implements `AdvisorApi` and select it in
`frontend/src/lib/api/index.ts`.

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

`skipToResults` and the `simulate` option are prototype-only and are ignored by the real backend.

## Data the UI needs

- **Case**: pseudonymous `code`, age, sex, concern, proposed treatment, status. Names never appear
  on case screens.
- **Run**: `status` (`running | complete | partial | failed`) and 14 steps, each
  `pending | running | done | warning | failed | skipped` with an optional plain-language note.
  A critical failure must come with `failure.title/body`; gaps with `warnings[]`.
- **Facts** carry provenance: `source = { docId, page, section, snippet }`.
- **Report**: 19 fixed sections; each non-template item has a stable `id` and `evidenceIds`.
  `kind` is `patient_fact | interpretation | external_evidence | template`.
- **Trace**: for any item ID (report sentence, finding, claim, fact, timeline event, question,
  comparison row) a tree from the statement down to the document page and reference source.
- **Verification**: `supported | partially_supported | unclear | contradicted | insufficient_evidence`,
  plus removed claims (kept visible, with a reason).
- **Cross-review**: matrix rows with a stance per specialist and a relationship.
  No scores, no winner.
- **Questions**: priority 1-3, audience, trigger text, linked item IDs and tracking
  status (`not_asked | partially_answered | answered`) with an optional note.
- **Comparison**: rows with both opinions, evidence for each and a relationship
  (`agreement | differs | new_info | changed | unresolved`). Never a verdict.

## Invariants the backend must keep

1. Every patient-facing sentence has an item ID that resolves in `getTrace`, except fixed template text.
2. Uncertainty, missing information and disagreement are returned, not dropped.
3. Failed or incomplete agents are reported (`status`, `statusNote`), never silently omitted.
4. No directive or verdict language in any returned text (see the blueprint's safety lint).
