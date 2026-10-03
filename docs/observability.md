# Observability (cost-neutral, no raw medical content)

Blueprint p. 39: measure cost, latency and quality per step **without logging raw medical content**.

## What exists

| Signal | Where | Notes |
| --- | --- | --- |
| Request ID | `X-Request-ID` header, every log line, every error envelope | Caller-supplied IDs are sanitised; echoed on every response, including CORS preflights and 500s. |
| Request log | `advisorai.request`: `METHOD path -> status in N ms` | **Path only**: query strings and bodies can hold personal data and are never logged. |
| Log redaction | `RedactingFormatter` | JWTs, `Bearer` values, `token=` / `apikey=` pairs and connection-string passwords are redacted; `httpx` request logging is silenced. |
| Errors | `advisorai.errors` | Exception text and traceback are logged server-side and never sent to the client. |
| Audit | `public.audit_logs` (append-only) | Who did what to which id, when, from which request: ids and actions only (ADR 0006). |
| Run + step state | `workflow_runs`, `workflow_steps` | Status, attempts, `started_at` / `finished_at` (so per-step latency), short `error_code`, fixed notes. No content, no prompts (ADR 0008). |
| Worker | `advisorai.worker`, `advisorai.workflow` | Lease lost, takeover, node type unavailable, engine crash: all by id and type, never by message. |
| Liveness / readiness | `GET /health`, `GET /health/ready` | Readiness checks the database; neither returns connection details. |

## Useful queries (run as the database owner, e.g. in the Supabase SQL editor)

```sql
-- Step latency by node (seconds), last 7 days
select node, count(*) n, round(avg(extract(epoch from finished_at - started_at))::numeric, 2) avg_s,
       max(extract(epoch from finished_at - started_at))::numeric(10,2) max_s
from workflow_steps where finished_at > now() - interval '7 days' and status in ('done', 'warning')
group by node order by avg_s desc;

-- Failures and retries by node and machine code
select node, error_code, count(*) failures, sum(attempts - 1) retries
from workflow_steps where status = 'failed' group by node, error_code order by failures desc;

-- Run outcomes
select status, count(*), round(avg(extract(epoch from finished_at - started_at))::numeric, 1) avg_s
from workflow_runs where finished_at is not null group by status;

-- Runs stuck (lease expired, not finished)
select id, attempts, locked_until from workflow_runs where status = 'running' and locked_until < now();
```

## Deferred to the AI phase or later (and why)

- `model_usage` / `api_usage` tables (tokens, cost, latency per model call): they need the AI gateway.
- `GET /admin/metrics` and the internal ops page: they need an admin role, which is not defined yet. Until then the
  queries above are the dashboard.
- An error tracker (blueprint: a free-tier tool "configured to scrub request bodies"). When added it **must** scrub
  request bodies: here they can contain free text a person typed about their health.
- Alerting / uptime monitoring.
