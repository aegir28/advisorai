# ADR 0008: Workflow persistence, job queue and engine foundation (Phase 2D)

- Status: accepted
- Date: 2026-10-05
- Scope: `backend/app/workflow/`, `backend/app/services/workflows.py`, `backend/app/api/analysis.py`,
  `supabase/migrations/20261005000001_*`

Blueprint references: workflow engine (p. 46: step state machine, run lifecycle, idempotent steps), orchestration
choice (p. 9: a small custom Python engine, workflow defined as data), backend layout (p. 41: worker loop,
in-process for the prototype, every step persisted so a restart resumes), failure handling (p. 38), observability
(p. 39: `workflow_runs`, `workflow_steps`).

## What exists

| Piece | Where | Notes |
| --- | --- | --- |
| Definitions | `workflow/definitions.py` | Versioned YAML DAGs, validated on load (unique ids, known deps, no cycles, ≤ 14 nodes, ≤ 2 retries, a timeout per node). Old versions stay loadable. |
| Queue + steps | `workflow/repository.py` | System-path SQL. Lease-based: `claim_next` uses `FOR UPDATE SKIP LOCKED`; the worker renews the lease; every finishing write requires `locked_by = worker`. |
| Engine | `workflow/engine.py` | Layers run in parallel. Retry (max 2, exponential backoff) for `RetryableError` and timeouts; critical failure → run `failed`; non-critical failure or a `warning` result → run `partial`. Idempotent: a step whose input hash already succeeded for the case is reused; a resumed run skips finished steps. |
| Worker | `workflow/worker.py` | In-process loop, **off by default** (`ADVISORAI_WORKER_ENABLED`). Heartbeat; cancels the engine if the lease is lost; hands the run back on shutdown. |
| Start a run | `services/workflows.py` | `enqueue_analysis`: ownership under RLS, ≥ 1 `ready` document, no run already active, then enqueue on the system path and set the case `processing`. **Not exposed over HTTP.** |
| Status | `GET /api/v1/analysis/{run_id}` | `run.v1`, status and steps only, never content. Owner-only (RLS), else `404 RUN_NOT_FOUND`. |

## Decisions

1. **No node types are registered.** The node registry is empty; the engine is exercised with test nodes only.
   A run whose definition needs an unregistered type fails *before any step runs* (`node_type_unavailable`)
   with a person-safe explanation: all or nothing, never half-run, never silent. The AI phase registers real
   nodes; nothing else about the engine has to change.
2. **`POST /cases/{id}/analysis` and `/runs/*` are not built.** They need nodes that produce content. A test
   asserts they are absent from OpenAPI so they cannot appear by accident.
3. **System path, narrowly.** `app_system` now holds `SELECT, INSERT` on `workflow_runs` / `workflow_steps` and
   `UPDATE` on named columns only (status, progress, failure, warnings, attempts, lock columns, timestamps;
   step status, attempts, note, hash, error code). It cannot change `owner_user_id`, `case_id` or `definition`,
   read cases or documents, or delete anything; the composite FKs still force a run's (case, owner) pair to be
   real. Users keep `SELECT` only. A user session still cannot reach `app_system` (ADR 0005). The migration
   re-asserts all of this and fails if it is not true; pgTAP (`04_workflow_system`) covers each point. The new
   enumerated operations are `workflow.enqueue` and `workflow.run`.
4. **`queued` is internal; the API presents it as `running` with progress 0.** From the person's side the
   analysis has started. This resolves the question ADR 0004 deferred *without* changing `run.v1` (no new enum
   value, no v2): the UI already polls while `running`. The database keeps `queued` so the worker can find work.
5. **The machine failure code stays server-side.** `workflow_runs.failure` stores `{title, body, code}`; the wire
   contract carries `title` and `body` only. Step `error_code` is a short machine code, `note` a fixed string.
6. **Nothing sensitive is stored or logged by the engine.** An unexpected exception from a node is recorded as
   `internal_error` and logged by *type only*; its message could contain document content. A test proves it.
7. **Crash safety.** A run whose lease expires is taken over (attempt + 1). After `MAX_RUN_ATTEMPTS` (3) it is
   marked `failed` (`max_attempts_exceeded`), never left `running`. A worker that lost its lease can neither
   extend nor finish the run.
8. **Audit:** `workflow.start` and `workflow.finish` (status only) per run, written best-effort after the fact
   (ADR 0007, decision 10). Per-step audit rows are not written: the steps table is the per-step record.
9. **Why 14 steps.** `run.v1` always has exactly 14 steps; `enqueue` refuses any other count, and a definition
   served through this API must have 14 nodes. Other workflows (add document, delete case, …) get their own
   status contract when they are built.

## Out of scope here

Model usage / cost tables (`model_usage`, blueprint p. 43) belong with the AI gateway. Admin metrics
(`/admin/metrics`) need an admin role, which is not defined yet. The stale-`pending_upload` sweeper (ADR 0007)
can run as a worker task once real workflows exist.
