# ADR 0010: The non-AI foundation is complete; the AI boundary and its guard

- Status: accepted
- Date: 2026-10-07
- Scope: repository-wide; `scripts/repo_guards.py`, `docs/handoff-ai-phase.md`

## Decision

The architecture blueprint's phases 1-5 (setup, database + auth, dashboard, case creation, upload) and the
non-AI part of phase 6 (workflow engine, job table, steps) plus phase 12-13's non-AI parts (security, RLS tests,
audit, key hygiene) are built. Everything in the blueprint that needs a model, a provider key, OCR/vision,
embeddings or clinical reasoning is **not** built and is the next phase's work: extraction (7), specialists (8),
evidence / RAG (9), questions (10), reviewer + report (11), PDF (12), benchmark scoring (14).

To keep that boundary from eroding by accident, CI runs `scripts/repo_guards.py`:

1. **naming**: the project is AdvisorAI; the old blueprint's working title is refused everywhere.
2. **secrets**: no private keys, service-role/secret keys, provider keys or committed `.env` files.
3. **ai-scope** (temporary, deliberate; **replaced by `ai-boundary` in [ADR 0011](0011-ai-gateway-and-pii-boundary.md)**): no AI provider SDK, provider key name, `pgvector`/`vector` column or
   gateway code. The AI phase removes or relaxes this rule **in its first pull request**, in the same change that
   adds the first provider dependency, so the relaxation is explicit and reviewable rather than a CI surprise.

## What the AI phase can build on without changing the core (blueprint p. 54: "stable core")

| Extension point | Where | Contract |
| --- | --- | --- |
| Node types | `NodeRegistry.register("ai.extract_facts", node)` | `async run(ctx: RunContext) -> StepResult`; raise `RetryableError` / `NodeError(code)` |
| Workflow definitions | `workflows/*.yaml` | versioned DAG, validated on load; 14 nodes for `run.v1` |
| Starting a run | `WorkflowService.enqueue_analysis` | ownership, ≥ 1 ready document, one active run per case |
| Run status | `GET /analysis/{run_id}` | `run.v1`; add `POST /cases/{id}/analysis` returning `202 + run_id` |
| System operations | `SystemOperation` enum + `app_system` grants | add one per new system write, with a migration and an ADR note |
| Reading uploaded files | `StorageGateway.read_object` | bounded read via the service key |
| Page text / facts | `document_pages`, `facts`, `timeline_events`, `medications`, `lab_results`, `diagnoses`, `procedures`, `medical_records` | tables and RLS exist; nothing writes them yet |
| Audit | `AuditAction` + `AuditWriter.record_completed` | add `ai.call`, `report.generate`, ... with their feature |
| Settings | `Settings` (`SecretStr`) | provider keys are backend-environment only |
| Benchmarks | `evals/` | `ground_truth.v1`, validator, bootstrap truth |

## Consequences

The prototype stays synthetic-only, the frontend keeps its mock as the default, and every AI-dependent endpoint is
absent from OpenAPI (a test asserts the analysis start and `/runs/*` routes do not exist) so nothing can appear to
work before it really does.
