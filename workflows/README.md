# workflows

Versioned workflow definitions: YAML DAGs that name node **types** and their dependencies. The workflow is data;
the engine that runs it (`backend/app/workflow/`) is swappable. See [ADR 0008](../docs/adr/0008-workflow-persistence-and-worker.md).

```yaml
id: case_analysis
version: 1
nodes:
  - {id: classify, type: ai.classify_docs, retries: 2}
  - {id: extract,  type: ai.extract_facts, after: [classify], timeout_s: 120}
```

Rules (checked on load): unique snake_case ids, `after` names existing nodes, no cycles, 1-14 nodes (`run.v1`
shows at most 14 steps), at most 2 retries, `timeout_s` 1-600. Optional per node: `critical: false` (a failure
makes the run *partial* instead of *failed*) and `tier` (model tier, used by the later AI phase).

**No real workflow is defined yet.** The first one (case analysis) needs AI node types, which belong to the AI
phase. A 14-node test fixture lives in `backend/tests/fixtures/workflows/`.
