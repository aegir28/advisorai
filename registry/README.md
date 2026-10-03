# registry

Configuration, not code. Everything that shapes the analysis pipeline lives here.

- `models.yaml`: model tiers per provider, enablement, prices, per-provider privacy state and per-task fallback
  chains. Loaded by `backend/app/ai/registry.py`.
- `agents.yaml` (v2): the specialist registry. A specialty, sub-specialty or capability is an entry (focus,
  parent, triggers, tier, timeout). Adding one needs no code and no workflow change. Everything ships disabled.
- `signals.yaml`: deterministic case signals that agent triggers match against.
- `workflows.yaml`: **the stage graph.** One definition per workflow (`case_analysis`, `second_opinion`). A stage
  has an id, `kind` (single | fanout), `handler`, `critical`, optional `when` flag, declared `flags`,
  `depends_on`, optional `retries` / `backoff_seconds` / `timeout_seconds`, and `params`. The order of the list
  is the order of execution and the step number users see. To add a stage, reorder, split a fan-out into two
  (`params: {priority: mandatory}` / `optional`), or make a stage conditional, edit this file; the loader refuses
  a malformed graph (duplicate ids, a dependency that is not earlier, a `when` flag no earlier stage declares, an
  unknown handler, a handler that cannot do the stage's kind) at startup. A new *capability* (a handler) is code;
  once it exists it can be used by any workflow. Start a run of a workflow with `workflow` = its id.
- `orchestration.yaml`: policy defaults (limits, escalation thresholds, retry, timeouts) the stage graph inherits.

Prompts live in `backend/app/orchestration/prompts/` (shared) and `backend/app/agents/prompts/`.
