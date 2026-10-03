# Docs

- [`design-direction.md`](design-direction.md): visual directions explored, the one chosen and why.
- [`frontend-data-contract.md`](frontend-data-contract.md): what the frontend expects from the backend.

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
