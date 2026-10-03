# ADR 0012: n8n orchestrates the clinical pipeline; the backend and AI gateway do the work

Status: accepted (prototype, synthetic data only)

## Context
The native worker/engine (ADR 0008) sequences fixed nodes in Python. The product needs a dynamic set of
specialties, conditional branches, parallel fan-out/in and a visual, operable orchestrator. Boundary:
Frontend → FastAPI → n8n → (backend capability API) → AI Gateway → providers → Supabase.

## Decision
* **n8n sequences; the backend works.** n8n calls HMAC-signed endpoints under `/internal/orchestrator/v1`
  (begin, stage, plan, agent, finish, execution-fail). It receives only ids, statuses and counts. It holds no
  database login (the system path `app_system` stays in the backend, column-limited, active-run-only), no
  provider key and no case content. It cannot reach a provider: no provider node/URL exists in any workflow
  (guard + test). RLS is untouched: owners read their own `analysis_artifacts`; nothing is exposed to n8n.
* **Registry-driven.** Specialists/sub-specialists/capabilities are entries in `registry/agents.yaml` (v2) with
  triggers over deterministic case signals; no workflow or code names a specialty. The wire id is an open
  pattern, not a closed enum.
* **Fourteen fixed stages** (`run.v1` shows 14 steps); questions precede the report. Branch conditions are
  computed by the backend from `registry/orchestration.yaml` and returned as booleans.
* **Idempotency everywhere.** Run per (case, Idempotency-Key); stage and agent results are append-only
  artifacts per (run, kind, key); retries and resume return stored results (no recompute, no re-bill).
* **Honest failure.** A specialist that fails/times out/produces invalid or unsafe output is stored as
  `unavailable` and the run continues; a critical stage failure fails the run; nothing is fabricated.
* **Safety by construction.** Deterministic output lint, readability gate, evidence verification (removed
  claims never reach the report), cross-review that preserves disagreement (no voting), reviewer fallback.
* **The native engine stays** for non-clinical use; it is not extended for clinical orchestration.

## Consequences / gaps
n8n JSON cannot be executed in this repo's CI (structure and contract tests only; `drive()` is a Python
reference of the master flow). Second-opinion run lifecycle is designed (contracts, comparison builder,
prompt) but has no stage service/workflow yet. No OCR, no embeddings/RAG (stages say `skipped`). The person's
display name cannot be read on the system path, so known-identifier scrubbing is rule-based only.
