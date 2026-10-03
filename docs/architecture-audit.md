# Architecture audit (Stage 1) and what changed

Audited the whole repository before changing it. Findings → decision.

1. **Workflow orchestration**: native Python engine, fixed linear nodes, none clinical. → n8n orchestrates (ADR 0012); engine kept.
2. **Agent model**: 5 specialists hard-coded in a closed `Literal` on both wire sides, `REQUIRED_SPECIALTIES`, placeholder prompts. → registry v2, open id pattern, shared prompt + focus, hierarchy, triggers.
3. **Routing**: rule/LLM strategy interfaces only. → `RegistryRuleStrategy` over `signals.yaml`, content-free trace.
4. **AI gateway**: solid (de-id, residual-PII block, retries, schema validation, usage ledger) but single route and per-run budget only. → task→chain fallback, privacy gate, cumulative INR budget guard.
5. **Cost control**: per-run USD cap. → ledger-backed reservation, alerts, unpriced models refused.
6. **Privacy/retention**: undocumented. → provider states, `docs/provider-research.md`; no provider verified.
7. **DB boundary**: RLS, `app_backend`/`app_system` split, append-only audit: **kept unchanged**; added column-limited active-run reads and append-only `analysis_artifacts`.
8. **Document intelligence**: text extraction + provenance check existed, unwired. → wired into stages 2–4; OCR still absent.
9. **Evidence**: contracts + keyword retriever, no verification. → deterministic claim verification, removal of unsupported claims.
10. **Cross-review/synthesis**: schemas only. → deterministic cross-review (no vote), reviewer with preservation + fallback.
11. **Medication safety**: absent. → `medication_review.v1` + validator, never an instruction.
12. **Output safety**: none. → lint (stop/start/dose/"doctor is wrong"/certainty/invented citations), readability gate, report lint.
13. **Report/questions/comparison**: wire contracts, no producer. → producers + floor questions; comparison builder (no winner).
14. **Reliability**: idempotent runs/stages/agents, retries, timeouts, cancel, resume, crash recovery. 
15. **Observability**: usage rows carry run/case/node/purpose/cost; prompt ids are hashes; no raw prompts stored.
16. **Security**: HMAC both ways with skew window; no keys in n8n; guards for n8n files.
17. **Frontend**: mock↔HTTP; not yet wired to artifacts/report read API (gap).
18. **CI**: backend path trigger for `n8n/`; repo guard for n8n.
19. **Already correct and preserved**: naming, RLS, signed URLs, synthetic-only controls, audit log, strict wire models.
