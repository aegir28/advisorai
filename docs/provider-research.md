# Model provider research (privacy, retention, cost)

**Checked on: 2026-10-03.** Method and limits, stated plainly: this environment cannot fetch the providers' own
pages (outbound access to those domains is blocked), so the findings below come from web-search excerpts of the
official pages plus third-party summaries. They are **not** a substitute for reading the official page and the
signed agreement. Nothing here is a claim of zero retention for this project: **no provider is `verified`**.
`registry/models.yaml` records each provider's state; the gateway refuses `unsuitable` providers and, under
`ADVISORAI_AI_PRIVACY_POLICY=require_verified`, refuses everything not `verified`.

The prototype is **synthetic-data-only**. `allow_unverified_synthetic` (the default) lets an unverified provider
run on synthetic data. Before any real patient data: obtain ZDR/equivalent in writing, set the provider to
`verified` with the evidence, switch the policy to `require_verified`.

| Provider | Retention / logging (as found) | Training on API data | ZDR | State in registry | Source |
|---|---|---|---|---|---|
| OpenAI API | Abuse-monitoring logs generated for all API use, kept up to 30 days by default | Not stated in the excerpt; read the page | Zero Data Retention / Modified Abuse Monitoring need OpenAI approval; ZDR forces `store=false` | `requestable` | https://developers.openai.com/api/docs/guides/your-data |
| Anthropic API | ZDR available under agreement for eligible API customers, subject to approval; safety-classifier results still retained; a 2026-06-09 policy requires 30-day retention for named "Covered Models" even under ZDR | Commercial terms: not used for training | By agreement, approval required | not enabled (no adapter) | https://platform.claude.com/docs/build-with-claude/api-and-data-retention |
| Google Gemini API / Vertex AI | Paid services: not used to improve products; prompts/responses logged for a limited period for abuse detection (length not stated in the excerpt) | Paid tier: not used | ZDR on request per project (Gemini API); Vertex has a ZDR option on certain endpoints | not enabled (no adapter) | https://discuss.ai.google.dev/t/how-to-request-zero-data-retention-zdr-for-a-gemini-developer-api-project/172806 |

## Not verified (do before real use)
- Per-provider current price tables, structured-output support and context limits: **not re-verified today**.
  `registry/models.yaml` keeps model rows `enabled: false`, `priced: false` with `REPLACE_ME_*` ids on purpose; the
  gateway refuses an unpriced model under the budget guard. Fill ids/prices from the official pricing page when a
  model is chosen.
- India usability (data residency, billing in INR, account availability): not verified.
- Anything about training use beyond the excerpts above.

## Cost design (₹5,000)
Budget in INR is converted with an explicit `ADVISORAI_AI_INR_PER_USD` (default 95; update it). The ledger-backed
guard (`LedgerBudgetGuard`) reserves each call's worst-case cost before the call, keeps a reserve fraction back,
alerts at 50/80/95 %, and stops at the cap. A rough per-run estimate cannot be given honestly until real model
prices are filled in; with the fake provider cost is simulated. Cheap tiers are used for extraction and
verification, tier 2 for specialists/review/report, tier 3 only on escalation (`registry/orchestration.yaml`).
More models do not mean more accuracy: the default chain per task is a single model; fallbacks exist for
availability, not for second opinions.
