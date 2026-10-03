"""Generates the n8n workflow JSON files in ../workflows. The JSON is the committed artefact (import it into n8n);
this script exists so the six workflows stay consistent with each other. Re-run after editing, then commit both:

    python3 n8n/tools/generate_workflows.py

Rules the generator enforces by construction (and backend/tests/unit/test_n8n_workflows.py re-checks on the
output): n8n only ever calls the backend's /internal/orchestrator/v1 API, signed with HMAC; there is no model
provider node, no provider URL, no key and no credential in any file. Secrets come from n8n environment
variables at run time and never appear in the JSON.
"""

import json
import uuid
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent.parent / "workflows"
NS = uuid.UUID("5b1c1e3e-0f3a-4c53-9a3f-2b7f1a5d9c01")
API = "/internal/orchestrator/v1"
# Fan-out ITEM calls use the HTTP node's static retry settings (n8n cannot make them dynamic); they mirror the
# policy defaults in registry/orchestration.yaml and a test fails if they drift. Everything else (timeouts,
# retries, backoff of a stage) comes from the stage descriptors the backend returns from `begin`.
MAX_TRIES, BACKOFF_MS = 3, 5_000

IDS = {
    "master": "advisorai-master",
    "signed": "advisorai-signed-call",
    "stage": "advisorai-run-stage",
    "fanout": "advisorai-fanout-stage",
    "error": "advisorai-error-recovery",
}


class Flow:
    def __init__(self, key: str, name: str, description: str) -> None:
        self.key, self.name, self.description = key, name, description
        self.nodes: list[dict[str, Any]] = []
        self.conns: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}
        self.settings: dict[str, Any] = {"executionOrder": "v1", "saveDataSuccessExecution": "none",
                                          "saveManualExecutions": False}

    def add(self, name: str, type_: str, params: dict[str, Any], pos: tuple[int, int], tv: float = 1,
            **extra: Any) -> str:
        self.nodes.append({
            "parameters": params, "id": str(uuid.uuid5(NS, f"{self.key}/{name}")), "name": name,
            "type": type_, "typeVersion": tv, "position": list(pos), **extra,
        })
        return name

    def link(self, a: str, b: str, out: int = 0) -> None:
        outs = self.conns.setdefault(a, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": b, "type": "main", "index": 0})

    def export(self) -> dict[str, Any]:
        return {
            "id": IDS[self.key], "name": self.name, "active": False, "nodes": self.nodes,
            "connections": self.conns, "settings": self.settings, "pinData": {},
            "meta": {"description": self.description, "templateCredsSetupCompleted": True},
            "tags": [{"name": "advisorai"}],
        }


def sub_trigger(f: Flow) -> str:
    # Passthrough: the caller's item arrives as is, so no per-workflow field list is needed.
    return f.add("When called", "n8n-nodes-base.executeWorkflowTrigger", {"inputSource": "passthrough"}, (0, 0), 1.1)


def call_sub(f: Flow, name: str, flow_key: str, pos: tuple[int, int], mode: str = "once") -> str:
    return f.add(name, "n8n-nodes-base.executeWorkflow", {
        "source": "database",
        "workflowId": {"__rl": True, "value": IDS[flow_key], "mode": "id"},
        "mode": mode, "options": {"waitForSubWorkflow": True},
    }, pos, 1.1)


# ═══ 1. signed call: the only place a request to the backend is built, signed and retried ═══════
def signed_call() -> Flow:
    f = Flow("signed", "AdvisorAI · 05 Signed backend call",
             "Reusable. One HMAC-signed POST to the backend capability API with the caller's retry/backoff/timeout "
             "(from the stage descriptor). Returns {ok, result} or {ok:false, code, retryable}. 4xx is never retried. "
             "Holds no credential in the file.")
    t = sub_trigger(f)
    call = f.add("Sign and call", "n8n-nodes-base.code", {"jsCode": (
        "const crypto = require('crypto');\n"
        "const secret = $env.ADVISORAI_N8N_HMAC_SECRET;\n"
        "const base = String($env.ADVISORAI_API_BASE_URL || '').replace(/\\/$/, '');\n"
        "if (!secret || !base) throw new Error('advisorai_env_missing');\n"
        "const { path } = $json; const body = $json.body || '';\n"
        "if (!String(path).startsWith('" + API + "/')) throw new Error('path_not_allowed');\n"
        "const tries = Math.max(1, Number($json.max_tries) || 1);\n"
        "const backoff = Math.max(0, Number($json.backoff_ms) || 0);\n"
        "const timeout = Math.max(1000, Number($json.timeout_ms) || 60000);\n"
        "for (let attempt = 1; attempt <= tries; attempt++) {\n"
        "  const ts = String(Math.floor(Date.now() / 1000));\n"
        "  const hash = crypto.createHash('sha256').update(body).digest('hex');\n"
        "  const sig = crypto.createHmac('sha256', secret).update(`${ts}.POST.${path}.${hash}`).digest('hex');\n"
        "  try {\n"
        "    const res = await this.helpers.httpRequest({\n"
        "      method: 'POST', url: base + path, timeout,\n"
        "      headers: { 'Content-Type': 'application/json', 'X-Advisorai-Timestamp': ts, 'X-Advisorai-Signature': sig },\n"
        "      ...(body ? { body } : {}),\n"
        "    });\n"
        "    const parsed = typeof res === 'string' ? JSON.parse(res) : res;\n"
        "    return [{ json: { ok: true, result: parsed } }];\n"
        "  } catch (e) {\n"
        "    const status = Number(e.httpCode || (e.response && e.response.status) || 0);\n"
        "    if (status >= 400 && status < 500) return [{ json: { ok: false, code: `orchestrator_http_${status}`, retryable: false } }];\n"
        "    if (attempt < tries && backoff) await new Promise((r) => setTimeout(r, backoff));\n"
        "  }\n"
        "}\n"
        "return [{ json: { ok: false, code: 'orchestrator_http_error', retryable: true } }];\n"
    )}, (240, 0), 2)
    f.link(t, call)
    return f


# ═══ 2. run (or skip) one stage ═════════════════════════════════════════════════════════════════
def run_stage() -> Flow:
    f = Flow("stage", "AdvisorAI · 10 Run stage",
             "Reusable. Runs, or skips, ONE stage of whatever workflow the backend described. It does not know what "
             "the stage does: the backend resolves the handler and is idempotent per stage, so a retry never re-bills. "
             "Input: run_id, stage_id, action (run|skip), timeout_seconds, retries, backoff_seconds.")
    t = sub_trigger(f)
    build = f.add("Build call", "n8n-nodes-base.code", {"jsCode": (
        "const { run_id, stage_id, action, timeout_seconds, retries, backoff_seconds } = $json;\n"
        f"const skip = action === 'skip';\n"
        f"const path = `{API}/runs/${{run_id}}/stages/${{stage_id}}` + (skip ? '/skip' : '');\n"
        "const body = skip ? JSON.stringify({ schema_version: 'skip_request.v1', reason: 'condition_not_met' }) : '';\n"
        "return [{ json: { run_id, stage_id, path, body, timeout_ms: Number(timeout_seconds) * 1000,\n"
        "  max_tries: Number(retries) + 1, backoff_ms: Number(backoff_seconds) * 1000 } }];\n"
    )}, (240, 0), 2)
    call = call_sub(f, "Signed call", "signed", (480, 0))
    shape = f.add("Shape result", "n8n-nodes-base.code", {"jsCode": (
        "const r = $input.first().json;\n"
        "const meta = $('Build call').first().json;\n"
        "if (!r.ok) return [{ json: { run_id: meta.run_id, stage: meta.stage_id, status: 'failed', "
        "code: r.code || 'orchestrator_http_error', retryable: !!r.retryable, counts: {}, flags: {} } }];\n"
        "return [{ json: r.result }];\n"
    )}, (720, 0), 2)
    f.link(t, build); f.link(build, call); f.link(call, shape)
    return f


# ═══ 3. a fan-out stage: plan items, run them in parallel batches, fan in ═══════════════════════
def fanout() -> Flow:
    f = Flow("fanout", "AdvisorAI · 20 Fan-out stage",
             "Reusable. For any stage of kind=fanout: runs the stage, asks the backend for its work items (for example "
             "the specialists chosen from the REGISTRY; never named here), runs them in parallel batches of "
             "max_parallel and fans in. An item failing never fails the run: the backend records it as unavailable.")
    t = sub_trigger(f)
    stage_in = f.add("Stage input", "n8n-nodes-base.code", {"jsCode": (
        "return [{ json: { ...$json, action: 'run' } }];\n"
    )}, (240, 0), 2)
    stage = call_sub(f, "Run fan-out stage", "stage", (480, 0))
    ok = f.add("Stage ok?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.status }}", "rightValue": "failed",
                        "operator": {"type": "string", "operation": "notEquals"}}], "combinator": "and"}},
        (720, 0), 2.2)
    plan_build = f.add("Build plan call", "n8n-nodes-base.code", {"jsCode": (
        "const input = $('Stage input').first().json;\n"
        f"const path = `{API}/runs/${{input.run_id}}/stages/${{input.stage_id}}/plan`;\n"
        "return [{ json: { path, body: '', timeout_ms: Number(input.timeout_seconds) * 1000,\n"
        "  max_tries: Number(input.retries) + 1, backoff_ms: Number(input.backoff_seconds) * 1000 } }];\n"
    )}, (960, -120), 2)
    plan = call_sub(f, "Plan", "signed", (1200, -120))
    items = f.add("One item per work item", "n8n-nodes-base.code", {"jsCode": (
        "const r = $input.first().json;\n"
        "const input = $('Stage input').first().json;\n"
        "if (!r.ok) return [{ json: { plan_failed: true, code: r.code } }];\n"
        "const plan = r.result;\n"
        "if (!plan.items.length) return [{ json: { empty: true } }];\n"
        "const crypto = require('crypto');\n"
        "const secret = $env.ADVISORAI_N8N_HMAC_SECRET;\n"
        "const base = String($env.ADVISORAI_API_BASE_URL || '').replace(/\\/$/, '');\n"
        "return plan.items.map((it) => {\n"
        f"  const path = `{API}/runs/${{input.run_id}}/stages/${{input.stage_id}}/items/${{it.id}}`;\n"
        "  const ts = String(Math.floor(Date.now() / 1000));\n"
        "  const hash = crypto.createHash('sha256').update('').digest('hex');\n"
        "  const sig = crypto.createHmac('sha256', secret).update(`${ts}.POST.${path}.${hash}`).digest('hex');\n"
        "  return { json: { item_id: it.id, url: base + path, ts, sig, max_parallel: plan.max_parallel, "
        "timeout: Math.max(Number(it.timeout_s) * 1000, 10000) } };\n"
        "});\n"
    )}, (1440, -120), 2)
    runnable = f.add("Anything to run?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.url }}", "rightValue": "",
                        "operator": {"type": "string", "operation": "notEmpty"}}], "combinator": "and"}},
        (1680, -120), 2.2)
    run_items = f.add("Run items (parallel batches)", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "={{ $json.url }}", "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-Advisorai-Timestamp", "value": "={{ $json.ts }}"},
            {"name": "X-Advisorai-Signature", "value": "={{ $json.sig }}"},
        ]},
        "options": {
            "timeout": "={{ $json.timeout }}",
            "batching": {"batch": {"batchSize": "={{ $json.max_parallel }}", "batchInterval": 0}},
        },
    }, (1920, -200), 4.2, retryOnFail=True, maxTries=MAX_TRIES, waitBetweenTries=BACKOFF_MS,
        onError="continueRegularOutput")
    fan_in = f.add("Fan in", "n8n-nodes-base.code", {"jsCode": (
        "// Every outcome is data. A failed or timed-out item is counted, never thrown: the backend already stored it\n"
        "// as 'unavailable' (or will, at collection); the run continues.\n"
        "const stage = $('Run fan-out stage').first().json;\n"
        "const results = $input.all().map((i) => i.json);\n"
        "const bad = results.filter((j) => j.error || j.status !== 'ok').length;\n"
        "return [{ json: { ...stage, status: 'ok', counts: { ...(stage.counts || {}), unavailable_items: bad } } }];\n"
    )}, (2160, -200), 2)
    nothing = f.add("Nothing to run", "n8n-nodes-base.code", {"jsCode": (
        "// An empty plan is a valid outcome (for example no optional items). Pass the stage result through.\n"
        "const stage = $('Run fan-out stage').first().json;\n"
        "const failed = !!$('One item per work item').first().json.plan_failed;\n"
        "return [{ json: failed ? { ...stage, status: 'failed', code: 'plan_failed', retryable: false } : stage }];\n"
    )}, (1920, 40), 2)
    failed = f.add("Stage failed", "n8n-nodes-base.noOp", {}, (960, 160))
    f.link(t, stage_in); f.link(stage_in, stage); f.link(stage, ok)
    f.link(ok, plan_build, 0); f.link(ok, failed, 1)
    f.link(plan_build, plan); f.link(plan, items); f.link(items, runnable)
    f.link(runnable, run_items, 0); f.link(runnable, nothing, 1)
    f.link(run_items, fan_in)
    return f


# ═══ 4. error recovery ═════════════════════════════════════════════════════════════════════════
def error_recovery() -> Flow:
    f = Flow("error", "AdvisorAI · 90 Error recovery",
             "Set as the master's error workflow. If the master execution crashes, the backend fails the run it "
             "was driving with a person-safe reason (idempotent, content-free), so no run is left 'running'.")
    t = f.add("On workflow error", "n8n-nodes-base.errorTrigger", {}, (0, 0), 1)
    build = f.add("Build call", "n8n-nodes-base.code", {"jsCode": (
        "const id = String($json.execution.id).replace(/[^A-Za-z0-9_.:-]/g, '');\n"
        f"return [{{ json: {{ path: `{API}/executions/${{id}}/fail`, body: '', timeout_ms: 30000, max_tries: 3, backoff_ms: 5000 }} }}];\n"
    )}, (240, 0), 2)
    call = call_sub(f, "Signed call", "signed", (480, 0))
    f.link(t, build); f.link(build, call)
    return f


# ═══ 5. master: generic. It runs whatever stage list `begin` returns. ═══════════════════════════
def master() -> Flow:
    f = Flow("master", "AdvisorAI · 00 Master orchestration",
             "Entry point. Verifies the signed start, asks the backend to begin the run (which selects the workflow "
             "definition and returns its stage descriptors), then executes each stage generically: kind decides the "
             "call pattern, `when` is evaluated against the flags seen so far, and the stage's own retry/timeout "
             "values are applied. It names no specialty, no stage and no clinical branch, and holds no case content, key or database login.")
    f.settings["errorWorkflow"] = IDS["error"]
    f.settings["executionTimeout"] = 3600
    wh = f.add("Start webhook", "n8n-nodes-base.webhook", {
        "httpMethod": "POST", "path": "advisorai-case-analysis", "responseMode": "responseNode", "options": {}},
        (0, 0), 2, webhookId=str(uuid.uuid5(NS, "master/webhook")))
    verify = f.add("Verify signature", "n8n-nodes-base.code", {"jsCode": (
        "const crypto = require('crypto');\n"
        "const secret = $env.ADVISORAI_N8N_HMAC_SECRET;\n"
        "const skew = Number($env.ADVISORAI_N8N_MAX_CLOCK_SKEW_SECONDS || 300);\n"
        "const h = $json.headers || {};\n"
        "const body = JSON.stringify($json.body || {});\n"
        "const ts = String(h['x-advisorai-timestamp'] || '');\n"
        "const got = String(h['x-advisorai-signature'] || '');\n"
        "const path = '/webhook/advisorai-case-analysis';\n"
        "const hash = crypto.createHash('sha256').update(body).digest('hex');\n"
        "const want = crypto.createHmac('sha256', secret || '').update(`${ts}.POST.${path}.${hash}`).digest('hex');\n"
        "const fresh = /^[0-9]+$/.test(ts) && Math.abs(Date.now() / 1000 - Number(ts)) <= skew;\n"
        "const same = got.length === want.length && crypto.timingSafeEqual(Buffer.from(got), Buffer.from(want));\n"
        "const b = $json.body || {};\n"
        "const valid = !!secret && fresh && same && b.schema_version === 'orchestration_start.v1';\n"
        "return [{ json: { valid, run_id: b.run_id, resume: b.resume === true } }];\n"
    )}, (240, 0), 2)
    gate = f.add("Signature valid?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.valid }}", "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true"}}], "combinator": "and"}},
        (480, 0), 2.2)
    deny = f.add("Respond 401", "n8n-nodes-base.respondToWebhook", {
        "respondWith": "json", "responseBody": "={{ { accepted: false } }}",
        "options": {"responseCode": 401}}, (720, 200), 1.1)
    accept = f.add("Respond 202", "n8n-nodes-base.respondToWebhook", {
        "respondWith": "json", "responseBody": "={{ { accepted: true } }}",
        "options": {"responseCode": 202}}, (720, -80), 1.1)
    begin_build = f.add("Build begin call", "n8n-nodes-base.code", {"jsCode": (
        "const run_id = $('Verify signature').first().json.run_id;\n"
        "const body = JSON.stringify({ schema_version: 'begin_request.v1', execution_id: String($execution.id) });\n"
        f"return [{{ json: {{ run_id, path: `{API}/runs/${{run_id}}/begin`, body, timeout_ms: 30000, max_tries: 3, backoff_ms: 5000 }} }}];\n"
    )}, (960, -80), 2)
    begin = call_sub(f, "Begin run", "signed", (1200, -80))
    stages = f.add("Stages still to run", "n8n-nodes-base.code", {"jsCode": (
        "// One item per stage the backend described (minus those a resumed run already finished).\n"
        "const r = $input.first().json;\n"
        "const run_id = $('Verify signature').first().json.run_id;\n"
        "if (!r.ok) return [{ json: { run_id, abort: true, code: r.code, id: 'begin', kind: 'single', flags: {} } }];\n"
        "const done = new Set(r.result.completed_stages);\n"
        "return r.result.stages.filter((s) => !done.has(s.id)).map((s) => ({ json: { run_id, ...s, flags: r.result.flags } }));\n"
    )}, (1440, -80), 2)
    loop = f.add("Each stage", "n8n-nodes-base.splitInBatches", {"batchSize": 1, "options": {}}, (1680, -80), 3)
    evaluate = f.add("Evaluate condition", "n8n-nodes-base.code", {"jsCode": (
        "// Flags seen so far = those from `begin` plus what each finished stage reported. `when` is the stage's\n"
        "// condition (a flag name from the workflow definition); the backend re-checks any skip we ask for.\n"
        "const s = $json;\n"
        "const flags = $('Update flags').isExecuted ? $('Update flags').last().json.flags : (s.flags || {});\n"
        "const action = s.abort ? 'abort' : (s.when && !flags[s.when] ? 'skip' : 'run');\n"
        "return [{ json: { run_id: s.run_id, stage_id: s.id, kind: s.kind, action, flags,\n"
        "  timeout_seconds: s.timeout_seconds, retries: s.retries, backoff_seconds: s.backoff_seconds, code: s.code || null } }];\n"
    )}, (1920, -80), 2)
    route = f.add("Action", "n8n-nodes-base.switch", {"rules": {"values": [
        {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "conditions": [
            {"id": f"r{i}", "leftValue": "={{ $json.action }}", "rightValue": a,
             "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": a}
        for i, a in enumerate(("run", "skip", "abort"))]}, "options": {}}, (2160, -80), 3.2)
    is_fan = f.add("Fan-out stage?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.kind }}", "rightValue": "fanout",
                        "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
        (2400, -200), 2.2)
    fan = call_sub(f, "Run fan-out stage", "fanout", (2640, -300))
    one = call_sub(f, "Run stage", "stage", (2640, -120))
    skip = call_sub(f, "Skip stage", "stage", (2640, 60))
    abort = f.add("Abort", "n8n-nodes-base.code", {"jsCode": (
        "// begin failed: there is nothing to run. Report it as a failed stage so the run is finished honestly.\n"
        "return [{ json: { run_id: $json.run_id, stage: 'begin', status: 'failed', code: $json.code || 'begin_failed', "
        "retryable: false, counts: {}, flags: {} } }];\n"
    )}, (2640, 240), 2)
    decide = f.add("Update flags", "n8n-nodes-base.code", {"jsCode": (
        "// Accumulate the flags a stage set and decide whether to go on. Only a failed or cancelled stage stops the\n"
        "// loop; the backend decides what is critical (non-critical failures come back as 'unavailable').\n"
        "const r = $input.first().json;\n"
        "const flags = { ...($('Evaluate condition').first().json.flags || {}), ...(r.flags || {}) };\n"
        "const stop = r.status === 'failed' || r.status === 'cancelled';\n"
        "return [{ json: { flags, stop, stage: r.stage || null, status: r.status || null, condition: r.condition || null } }];\n"
    )}, (2880, -80), 2)
    cont = f.add("Stopped?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.stop }}", "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true"}}], "combinator": "and"}},
        (3120, -80), 2.2)
    fin_build = f.add("Build finish call", "n8n-nodes-base.code", {"jsCode": (
        "const run_id = $('Verify signature').first().json.run_id;\n"
        f"return [{{ json: {{ run_id, path: `{API}/runs/${{run_id}}/finish`, body: '', timeout_ms: 30000, max_tries: 3, backoff_ms: 5000 }} }}];\n"
    )}, (3360, 100), 2)
    fin = call_sub(f, "Finish run", "signed", (3600, 100))
    f.link(wh, verify); f.link(verify, gate)
    f.link(gate, accept, 0); f.link(gate, deny, 1)
    f.link(accept, begin_build); f.link(begin_build, begin); f.link(begin, stages); f.link(stages, loop)
    f.link(loop, fin_build, 0)          # done: every stage ran
    f.link(loop, evaluate, 1)           # loop body
    f.link(evaluate, route)
    f.link(route, is_fan, 0); f.link(route, skip, 1); f.link(route, abort, 2)
    f.link(is_fan, fan, 0); f.link(is_fan, one, 1)
    for n in (fan, one, skip, abort):
        f.link(n, decide)
    f.link(decide, cont)
    f.link(cont, fin_build, 0)          # stop early: still finish (the backend computes failed/partial)
    f.link(cont, loop, 1)               # carry on
    f.link(fin_build, fin)
    return f


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    files = {
        "advisorai-00-master.json": master(), "advisorai-05-signed-call.json": signed_call(),
        "advisorai-10-run-stage.json": run_stage(), "advisorai-20-fanout-stage.json": fanout(),
        "advisorai-90-error-recovery.json": error_recovery(),
    }
    for name, flow in files.items():
        (OUT / name).write_text(json.dumps(flow.export(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(flow.nodes)} nodes")


if __name__ == "__main__":
    main()
