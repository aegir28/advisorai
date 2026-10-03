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

**No real workflow is defined yet, on purpose.** The clinical workflow is designed by people. To add it:

1. write the nodes (`AINode` subclasses for model calls, see `backend/app/workflow/ai_node.py`);
2. register each under a node type in `backend/app/workflow/nodes.py` (`register_nodes`);
3. put the DAG in `workflows/<name>.v1.yaml` (this folder) using those node types;
4. add `POST /cases/{id}/analysis` (it calls `WorkflowService.enqueue_analysis`) and turn the worker on.

The engine refuses to start a run whose definition names an unregistered node type. A 14-node test fixture lives in
`backend/tests/fixtures/workflows/`.
