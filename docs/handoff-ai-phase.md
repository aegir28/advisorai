# Handoff: the AI infrastructure is built; plug in the design

Everything that can be built **before** an API key and a clinical workflow exist is built and tested. What is left
is the part that needs people: the keys, the model choices, the workflow, the prompts, and the clinical judgement.
Nothing here designs, decides or implements clinical reasoning. Read [ADR 0011](adr/0011-ai-gateway-and-pii-boundary.md)
for the why; this page is the how.

> Synthetic data only. No real patient data. No production medical claims. The prototype's data mode is locked
> to `synthetic_only` (ADR 0004) and de-identification here is a safety net, not a licence to use real data.

## 1. What is already implemented

| Area | What exists | Where |
| --- | --- | --- |
| **AI gateway** | The only door to a model: de-identify, residual-PII block, tier routing, per-run budget, timeout, bounded retries with backoff, structured-output validation with bounded re-asks, token and cost metering, usage row, audit, metrics, request/run/case/node correlation | `backend/app/ai/gateway.py` |
| Provider abstraction | `Provider` protocol; deterministic `FakeProvider` (default); `OpenAIProvider` over plain HTTPS (Responses API, `store: false`, JSON-Schema output), **no vendor SDK** | `app/ai/provider.py`, `app/ai/providers/` |
| Model config | Tier 1/2/3 to model per provider, enablement, prices, placeholders refused | `registry/models.yaml`, `app/ai/registry.py` |
| Usage ledger | `public.model_usage` (RLS forced, INSERT-only for the system role, owners read their own), audit action `ai.call`, log redaction of `sk-` keys | migration `20261006000001`, `app/ai/usage.py` |
| **PII boundary** | Rule-based de-identification of free text and a residual check that blocks a prompt that still contains an identifier | `app/safety/deidentify.py` |
| **Document intelligence** | Upload validation (existing), local text-layer extraction (pypdf, no OCR), page/document metadata (`needs_ocr` flag), classification / fact / entity extraction contracts, **provenance check** (a fact must quote text that really is on its page) | `app/docintel/` |
| **Workflow integration** | `AINode`: generic AI step that calls the gateway with full correlation and maps failures to the engine's retry / critical / partial handling. Node registration point (empty). | `app/workflow/ai_node.py`, `app/workflow/nodes.py` |
| **Specialty contracts** | Input (`specialty_input.v1` = de-identified `case.v1` + routing reason + allowed sources), output (the existing `specialist_report.v1`), metadata registry for the five specialties (all **disabled**), prompt store, deterministic report validator | `app/agents/`, `registry/agents.yaml` |
| **Router infrastructure** | Strategy pipeline (deterministic `RuleStrategy`, abstract `LLMAssistedStrategy`), registry filter, guardrails, **max-active-agents** cap. Ships **no rules**; with none plugged in it selects nobody and says why | `app/router/` |
| **Evidence / RAG contracts** | `EvidenceItem` (patient passage or external reference), retrieval query/result, `EvidenceRetriever` and `ClaimVerifier` interfaces, structural claim checks, a keyword test double. No embeddings, no vector store | `app/evidence/`, `app/schemas/evidence.py` |
| **Output contracts** | Backend models for synthesis, personalised questions, second-opinion comparison, evidence/claims, routing plan, cross-review, validated against the frontend's fixtures (so the UI can already render them) | `app/schemas/`, `backend/tests/contract/test_ai_output_shapes.py` |
| Tests | 100+ new deterministic tests, all on the fake provider; DB tests on real PostgreSQL | `backend/tests/`, `supabase/tests/database/05_model_usage.test.sql` |
| Operator tools | `python -m app.ai.demo`, `python -m app.ai.status`, `python -m app.ai.smoke` | `backend/app/ai/` |

Still true from before: Google sign-in is wired but disabled in `config.toml` (live round-trip unverified), the
workflow worker is **off**, no node type is registered, the frontend uses its mock by default, and
`POST /cases/{id}/analysis` does not exist yet.

## 2. Where to add the API key

**Backend environment only.** Never in `frontend/`, never `NEXT_PUBLIC_*`, never committed.

```bash
# backend/.env  (git-ignored; copy from backend/.env.example)
ADVISORAI_AI_PROVIDER=openai
ADVISORAI_OPENAI_API_KEY=sk-...        # your key
```

- Read once, in `Settings` (`app/core/config.py`) as a `SecretStr`; it never appears in `repr`, logs, errors or
  the frontend. `ADVISORAI_AI_PROVIDER=openai` **without** a key refuses to start. A key shorter than 20
  characters is rejected as obviously wrong.
- On Render: add `ADVISORAI_OPENAI_API_KEY` as an environment secret (see `docs/deployment.md`). The repo guard
  fails CI if a key-shaped string is committed.

## 3. Where provider / model configuration lives

| What | Where |
| --- | --- |
| Which provider is active | `ADVISORAI_AI_PROVIDER` (`fake` default, or `openai`) |
| Timeout, retries, re-asks, per-run budget | `ADVISORAI_AI_REQUEST_TIMEOUT_SECONDS` (60), `..._AI_MAX_ATTEMPTS` (3), `..._AI_SCHEMA_RETRIES` (1), `..._AI_RUN_BUDGET_USD` (0.50; 0 = off) |
| **Tier to model, enablement, prices** | **`registry/models.yaml`** |
| Base URL (proxy / Azure-style gateway) | `ADVISORAI_OPENAI_BASE_URL` |
| Per-agent tier and timeout | `registry/agents.yaml` |

Tiers: 1 cheap/fast, 2 reasoning workhorse, 3 highest quality (escalation). In `registry/models.yaml` the three
`openai` routes point at `REPLACE_ME_TIERn_MODEL_ID` placeholders on purpose: replace the **route** *and* the
matching **model entry** (same id), set `enabled: true`, enter the two per-million-token prices and `priced: true`.
A placeholder or disabled route is refused with `model_not_configured`; an unpriced model still works and records
its cost as unknown (NULL). Run `uv run python -m app.ai.status` to see what is still open.

## 4. Where the clinical workflow DAG goes

The workflow is data; the engine already exists. Add it in four steps (`workflows/README.md` has the same list):

1. **Write nodes.** For a model call subclass `AINode` (`app/workflow/ai_node.py`): `build_request` returns a
   `GatewayRequest` (output schema, system prompt, segments, tier) and `handle_output` receives the **validated**
   output. Free text goes in `PromptSegment(text, "free_text")` so it is de-identified; fixed developer text is
   `"template"`.
2. **Register them** in `app/workflow/nodes.py::register_nodes`, e.g. `registry.register("agent.cardiology", node)`.
3. **Define the DAG** in `workflows/case_analysis.v1.yaml`: node ids, types, `after:` dependencies, `retries`,
   `timeout_s`, `critical`. **Which specialty runs before or after another is yours to design**; the engine runs
   layers in parallel and refuses an unregistered type, a cycle, or more than 14 nodes.
4. **Start it**: add `POST /cases/{id}/analysis` (returns `202 + run_id`, calls the existing
   `WorkflowService.enqueue_analysis`), set `ADVISORAI_WORKER_ENABLED=true`, and point the frontend's
   `startAnalysis` at it. Note: a run has exactly 14 steps (`run.v1`), so a definition served through `/analysis`
   needs 14 nodes today.

What the engine already gives every node: step persistence, idempotent reuse (same inputs, same provider means no
repeat call), retry for `RetryableError`, timeout, critical vs non-critical (failed vs partial), lease-based
worker, audit of start/finish. What `AINode` adds: usage rows tied to the run and node, error mapping, fixed
person-safe step notes.

## 5. Where specialist-agent prompts go

`backend/app/agents/prompts/<specialty>/v1.md` (see that folder's README). Five placeholder files exist; the
prompt store refuses a placeholder (`prompt_not_written`), so an agent without a real prompt cannot run.

- Enable an agent in `registry/agents.yaml` (`enabled: true`), set `version` and `tier`.
- Implement the agent (a class with `spec` and `async run(payload: SpecialtyInput, context) -> SpecialistReport`),
  typically an `AINode`-style call that asks the gateway for `SpecialistReport` and then runs
  `validate_specialist_report(report, payload, spec)`. Attach it with `registry.attach(agent)`.
- `SpecialtyRegistry.readiness(PromptStore())` (and `python -m app.ai.status`) lists exactly what blocks each of
  the five: `disabled`, `prompt_not_written`, `no_implementation`.
- The router rules/strategies are also yours: plug a `RuleStrategy` or an `LLMAssistedStrategy` and guardrails
  into `Router(...)` (`app/router/`). `max_active_agents` caps concurrency.

## 6. Where real OpenAI calls are enabled

Nowhere in code. It is configuration plus one check:

1. Put the key in `backend/.env` (section 2) and set `ADVISORAI_AI_PROVIDER=openai`.
2. Fill the tier-1 route and model in `registry/models.yaml` (section 3).
3. `cd backend && uv run python -m app.ai.status` shows what is still open.
4. **Smoke test**: `uv run python -m app.ai.smoke 1` makes one tiny call with a fixed fictional sentence and prints
   provider, model, tokens, cost. **The OpenAI adapter has only ever run against a mocked transport**, so this is
   where a wrong field name or parameter would show up. If it fails, `FAILED: <code>` tells you which stage:
   `provider_auth_failed` (key), `provider_bad_request` (request shape or model id), `provider_bad_response`
   (response parsing in `OpenAIProvider._parse`), `model_not_configured` (registry).
5. Real calls are made by whatever node or router strategy you wire to the gateway; none exist until you add them.

## 7. Run the deterministic fake-provider demo

```bash
cd backend && uv sync --locked --extra dev
uv run python -m app.ai.demo     # de-identification, retry, schema validation, cost, PII block, agent readiness
uv run python -m app.ai.status   # the activation checklist
uv run python -m app.ai.smoke    # one call through the gateway (fake provider by default)
uv run --no-sync pytest          # the whole suite; add ADVISORAI_TEST_ADMIN_DATABASE_URL for the DB-backed tests
```

## 8. Tomorrow, in order

1. Decide the workflow with your mentor; write it as nodes + `workflows/case_analysis.v1.yaml` (section 4).
2. Write the five prompts (section 5) and the router rules; enable the agents.
3. Key + model ids + prices; run `status`, then `smoke` (sections 2, 3, 6).
4. Add `POST /cases/{id}/analysis`, enable the worker, run one **synthetic** case end to end and check
   `model_usage` and the audit log (queries in `docs/observability.md`).
5. Decide the embedding model / vector store **only if** you need retrieval; that needs a migration and relaxing
   the `ai-boundary` guard's pgvector rule in the same pull request.

## 9. Known gaps and unverified items (none hidden)

- **OpenAI adapter vs the live API: unverified** (mock transport only). `strict` JSON-Schema mode is off by default
  because pydantic schemas are not always strict-compatible; try `strict_schema=True` if you want it.
- **De-identification is rule-based and best-effort** (emails, phones, IDs, labelled names, titled names, labelled
  DOB, URLs, labelled addresses). It will miss unlabelled names. Do not use real data.
- Extraction is **text layer only**; there is no OCR and no vision. `DocumentMetadata.needs_ocr` reports the gap.
- Which claims are removed from a report, what counts as "supported", and the confidence rubric are yours to
  define: the contracts only check structure (`check_claim_structure`, `validate_specialist_report`).
- Persistence for facts, timeline and medications still has no write path (tables and RLS exist); each needs a
  system operation and grants, like `model_usage` did.
- Carried over: the real Supabase stack (`supabase start`, `db reset`, `db lint`, `test db`) and the two Storage
  integration tests were run in CI, not in the build environment here; the DB tests in this delivery ran on the
  native PostgreSQL substitute (`supabase/native/`). Per-user rate limiting, the stale-upload sweeper and an admin
  role are not built. The UX-polish PR (#11) merged into the Phase 2F branch **after** develop had taken that
  branch, so those frontend fixes are not in develop until that branch is merged again.

## 10. Commands

```bash
# database + backend (real stack, where Docker works)
supabase start -x studio,imgproxy && supabase db reset && supabase test db
cd backend && uv sync --locked --extra dev && uv run --no-sync pytest
# without Docker: the labelled substitute
supabase/native/run.sh up && supabase/native/run.sh pgtap
# frontend
cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build
# repo guards + benchmark data
python scripts/repo_guards.py && (cd backend && uv run --no-sync python ../evals/validate.py)
```
