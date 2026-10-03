# Docs

- [`design-direction.md`](design-direction.md): visual directions explored, the one chosen and why.
- [`frontend-data-contract.md`](frontend-data-contract.md): what the frontend expects from the backend.
- [`deployment.md`](deployment.md): free-tier deployment foundations and the secrets map.
- [`observability.md`](observability.md): what is logged, measured and deliberately not.
- [`handoff-ai-phase.md`](handoff-ai-phase.md): **start here.** What is built, where the key / model config / workflow / prompts go, and how to turn real calls on.
- [`n8n.md`](n8n.md): n8n workflows, env vars, local/prod, activation.
- [`provider-research.md`](provider-research.md): provider retention/cost research (dated, with limits).
- [`architecture-audit.md`](architecture-audit.md): the Stage-1 audit and decisions.

The architecture blueprint (product scope, agentic workflow, verification, security and build plan)
is the source of truth for the product. It is maintained outside this repository for now.

## Architecture decision records

- [`adr/0001-wire-casing.md`](adr/0001-wire-casing.md): the wire format is snake_case; conversion is explicit at the frontend adapter.
- [`adr/0002-error-contract.md`](adr/0002-error-contract.md): the error envelope and request IDs.
- [`adr/0003-python-target-and-lockfile.md`](adr/0003-python-target-and-lockfile.md): Python 3.12+ and the committed `uv.lock`.
- [`adr/0004-phase-2b-supabase-foundation.md`](adr/0004-phase-2b-supabase-foundation.md): Phase 2B scope, approved decisions and corrections.
- [`adr/0005-database-user-context.md`](adr/0005-database-user-context.md): how a verified user becomes `auth.uid()` on a direct Postgres connection (and the residual risk).
- [`adr/0006-privacy-controls-audit-and-storage.md`](adr/0006-privacy-controls-audit-and-storage.md): identity separation, audit log, signed URLs, synthetic-only mode.
- [`adr/0007-case-and-document-lifecycle.md`](adr/0007-case-and-document-lifecycle.md): case and document endpoints, secure upload, validation without AI, purge order.
- [`adr/0008-workflow-persistence-and-worker.md`](adr/0008-workflow-persistence-and-worker.md): job queue, step persistence, engine and worker foundation (no AI nodes).
- [`adr/0009-google-auth-and-frontend-http-integration.md`](adr/0009-google-auth-and-frontend-http-integration.md): Google sign-in via Supabase Auth, the frontend HTTP API, request hardening.
- [`adr/0010-non-ai-foundation-boundary-and-ai-handoff.md`](adr/0010-non-ai-foundation-boundary-and-ai-handoff.md): the non-AI foundation is complete; the boundary guard and the extension points.
- [`adr/0011-ai-gateway-and-pii-boundary.md`](adr/0011-ai-gateway-and-pii-boundary.md): the AI gateway, de-identification boundary, usage ledger and the workflow/agent/router/evidence seams (no clinical decisions).
- [`adr/0012-n8n-orchestration.md`](adr/0012-n8n-orchestration.md): n8n sequences, the backend works; registry-driven specialists; honest failure.
