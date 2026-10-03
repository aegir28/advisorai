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
* **The stage graph is configuration** (`registry/workflows.yaml`, amended after review). A workflow is a list of
  stages: `kind` (single | fanout), `handler` (a backend capability), `critical`, optional `when` (a flag),
  declared `flags`, `depends_on`, and optional retry/timeout overrides. The backend creates a run's steps from
  the selected definition (`workflow_runs.definition`), `begin` returns stage descriptors, and the n8n master runs
  whatever it is given: `kind` picks the call pattern, `when` is evaluated against the flags seen so far (skip is
  preserved with the reason `condition_not_met`; the backend re-checks every skip and refuses a mismatch), and the
  stage's own retries/timeouts are applied. A fan-out stage has a generic protocol (plan items, run items), so a
  second fan-out stage is config. `case_analysis` has 14 stages today only because its config lists 14;
  `second_opinion` (a skeleton) has 6 on the same machinery. `run.v1` and the `workflow_steps` check were widened
  from "exactly 14" to "1..N, N <= 64" for this. Questions still precede the report in `case_analysis`.
* **Idempotency everywhere.** Run per (case, Idempotency-Key); stage and agent results are append-only
  artifacts per (run, kind, key); retries and resume return stored results (no recompute, no re-bill).
* **Honest failure.** A specialist that fails/times out/produces invalid or unsafe output is stored as
  `unavailable` and the run continues; a critical stage failure fails the run; nothing is fabricated.
* **Safety by construction.** Deterministic output lint, readability gate, evidence verification (removed
  claims never reach the report), cross-review that preserves disagreement (no voting), reviewer fallback.
* **The native engine stays** for non-clinical use; it is not extended for clinical orchestration.

## Consequences / gaps
A genuinely new capability (a new kind of model step) still needs a handler in the backend; once it exists it is
usable in any workflow. n8n JSON cannot be executed in this repo's CI (structure and contract tests only; `drive()` is a Python
reference of the master flow). Second-opinion run lifecycle is designed (contracts, comparison builder,
prompt) but has no stage service/workflow yet. No OCR, no embeddings/RAG (stages say `skipped`). The person's
display name cannot be read on the system path, so known-identifier scrubbing is rule-based only.
