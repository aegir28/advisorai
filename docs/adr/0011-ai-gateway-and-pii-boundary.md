# ADR 0011: The AI gateway, the PII boundary and the AI/workflow seams

- Status: accepted
- Date: 2026-10-10
- Scope: `backend/app/ai`, `backend/app/safety/deidentify.py`, `registry/`, migration `20261006000001_model_usage.sql`

## Context

ADR 0010 stopped at the AI boundary. This ADR builds everything on the near side of it that does not need an API
key or a clinical decision: the single door to a model provider, the privacy boundary in front of it, the ledger
behind it, and the interfaces that the clinical workflow, specialist agents, router and evidence code will plug
into. It deliberately designs **no** clinical workflow, routing rule, prompt or reasoning.

## Decisions

1. **One door.** `AIGateway.invoke` is the only way to reach a model: de-identify -> residual-PII check -> route
   tier to model -> budget -> call (timeout, bounded retries with backoff) -> parse and validate against the
   output schema (bounded re-asks) -> meter -> usage row + audit + metrics. Nothing else imports a provider.
2. **Provider abstraction.** A `Provider` protocol (`complete(ModelRequest) -> ModelResponse`). Two adapters: a
   deterministic `FakeProvider` (default; used by every test and the demo) and `OpenAIProvider`, written against
   the Responses API over plain `httpx` with `store: false` and JSON-Schema output. **No vendor SDK**, so there is
   no new dependency. The adapter is tested only against a mocked transport; the first live call is the smoke
   test in the handoff document. There is no silent fallback between providers.
3. **Configuration.** Provider and key come from `Settings` (`ADVISORAI_AI_PROVIDER`, `ADVISORAI_OPENAI_API_KEY`
   as `SecretStr`, backend environment only). The tier -> model map and prices live in `registry/models.yaml`.
   A route whose model is still a `REPLACE_ME` placeholder, or not `enabled`, is refused (`model_not_configured`):
   the gateway never guesses a model name. An unpriced model records its cost as unknown (NULL), never invented.
4. **PII boundary.** Free text (what a person typed, text read from a document) is de-identified before it reaches
   a prompt (`safety/deidentify.py`: rule-based, deterministic, best-effort; known identifiers are matched
   exactly). The final prompt is re-checked; anything identifying that remains blocks the call (`pii_blocked`).
   Identity fields never enter an AI context (`case.v1` already carries none). The prototype stays synthetic-only
   (ADR 0004); this module is a safety net, not a licence to use real data.
5. **Structured output only.** The gateway returns a validated pydantic object or raises. Raw model text is never
   returned, stored or logged. Truncated output is never trusted.
6. **Ledger and audit.** `public.model_usage`: one row per call (tokens, micro-USD cost or NULL, latency, attempts,
   outcome code, request/run/case/node ids) written on the **system path** with a new `SystemOperation`
   (`ai.usage_record`) and an `INSERT`-only grant to `app_system`. Composite foreign keys force (case, owner) and
   (run, case, owner) to be real and consistent; owners can `SELECT` their own rows; nobody can `UPDATE`/`DELETE`.
   The audit action `ai.call` carries ids, model, tier, attempts and an outcome code, never content. Logs carry
   codes and numbers only, and the log redactor now also masks `sk-...` keys.
7. **Budget.** A per-run spend cap (`ADVISORAI_AI_RUN_BUDGET_USD`, default 0.50, 0 disables) stops further calls
   in a run once spent.
8. **Workflow seam.** `workflow/ai_node.py::AINode` is a generic AI step: it describes a call, receives the
   validated output, and maps gateway failures onto the engine's own errors (retryable -> `RetryableError`; the
   rest -> `NodeError` with a fixed person-safe note). The engine passes the node id in `RunContext` so usage rows
   correlate to steps. Node types are registered in `workflow/nodes.py`, which is empty on purpose.
9. **Contracts, not decisions.** Specialty agents (`agents/`), the router (`router/`), evidence (`evidence/`) and
   document intelligence (`docintel/`) are interfaces, registries, deterministic checks and test doubles. The five
   specialists are registered **disabled** with placeholder prompts that the prompt store refuses to load. The
   router ships no rules and selects nobody. Retrieval is an interface with a keyword test double: no embedding
   model is chosen and no vector store exists.
10. **Guard.** `scripts/repo_guards.py` rule `ai-scope` became `ai-boundary`: no provider SDK anywhere, no bare
    provider key names, no provider endpoint outside the adapter/config/tests, no `pgvector` until embeddings are
    chosen.

## What is intentionally not decided here

The clinical workflow DAG, which specialties run and in what order, the specialist prompts, routing rules, which
claims are removed from a report, the embedding model and vector store, OCR/vision, and the real model names and
prices. Each has an obvious home (see `docs/handoff-ai-phase.md`).

## Consequences

The whole AI path is testable offline and deterministically. Turning on real calls is configuration (a key, two
model ids, prices) plus one smoke test. The remaining risks are the ones named above: the OpenAI adapter's field
names are unverified against the live API, and de-identification is rule-based.
