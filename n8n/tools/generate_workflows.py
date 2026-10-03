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
# Mirrors registry/orchestration.yaml (a test fails if these drift apart).
STAGE_TIMEOUT_MS, AGENT_TIMEOUT_MS, MAX_TRIES, BACKOFF_MS = 180_000, 120_000, 3, 5_000

IDS = {
    "master": "advisorai-master",
    "signed": "advisorai-signed-call",
    "stage": "advisorai-run-stage",
    "fanout": "advisorai-specialist-fanout",
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


def sub_trigger(f: Flow, fields: list[str]) -> str:
    return f.add("When called", "n8n-nodes-base.executeWorkflowTrigger", {
        "inputSource": "workflowInputs",
        "workflowInputs": {"values": [{"name": n} for n in fields]},
    }, (0, 0), 1.1)


def call_sub(f: Flow, name: str, flow_key: str, pos: tuple[int, int], mode: str = "once") -> str:
    return f.add(name, "n8n-nodes-base.executeWorkflow", {
        "source": "database",
        "workflowId": {"__rl": True, "value": IDS[flow_key], "mode": "id"},
        "mode": mode, "options": {"waitForSubWorkflow": True},
    }, pos, 1.1)


# ═══ 1. signed call: the only place a request to the backend is built ═══════════════════════════
def signed_call() -> Flow:
    f = Flow("signed", "AdvisorAI · 05 Signed backend call",
             "Reusable. Sends one HMAC-signed POST to the backend capability API and returns {ok, result|code}. "
             "Retries transient failures (policy: registry/orchestration.yaml). Holds no credential in the file.")
    t = sub_trigger(f, ["path", "body", "timeout_ms"])
    sign = f.add("Sign request", "n8n-nodes-base.code", {"jsCode": (
        "const crypto = require('crypto');\n"
        "const secret = $env.ADVISORAI_N8N_HMAC_SECRET;\n"
        "const base = String($env.ADVISORAI_API_BASE_URL || '').replace(/\\/$/, '');\n"
        "if (!secret || !base) throw new Error('advisorai_env_missing');\n"
        "const { path } = $json; const body = $json.body || '';\n"
        "if (!String(path).startsWith('" + API + "/')) throw new Error('path_not_allowed');\n"
        "const ts = String(Math.floor(Date.now() / 1000));\n"
        "const hash = crypto.createHash('sha256').update(body).digest('hex');\n"
        "const sig = crypto.createHmac('sha256', secret).update(`${ts}.POST.${path}.${hash}`).digest('hex');\n"
        "return [{ json: { url: base + path, body, ts, sig, timeout: Number($json.timeout_ms) || 60000 } }];\n"
    )}, (240, 0), 2)
    http = f.add("POST to backend", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "={{ $json.url }}",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-Advisorai-Timestamp", "value": "={{ $json.ts }}"},
            {"name": "X-Advisorai-Signature", "value": "={{ $json.sig }}"},
        ]},
        "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": "={{ $json.body }}",
        "options": {"timeout": "={{ $json.timeout }}"},
    }, (480, 0), 4.2, retryOnFail=True, maxTries=MAX_TRIES, waitBetweenTries=BACKOFF_MS,
        onError="continueRegularOutput")
    norm = f.add("Normalize", "n8n-nodes-base.code", {"jsCode": (
        "const j = $input.first().json;\n"
        "if (j.error || !j.schema_version) {\n"
        "  return [{ json: { ok: false, code: 'orchestrator_http_error', retryable: true } }];\n"
        "}\n"
        "return [{ json: { ok: true, result: j } }];\n"
    )}, (720, 0), 2)
    f.link(t, sign); f.link(sign, http); f.link(http, norm)
    return f


# ═══ 2. run one stage (intake/safety, document intelligence, context, verification, review, report ...) ═
def run_stage() -> Flow:
    f = Flow("stage", "AdvisorAI · 10 Run stage",
             "Reusable. Runs ONE backend stage by id (safety/intake, document intelligence, context assembly, "
             "routing, evidence verification, cross-agent review, interim reviewer, questions, final report). "
             "The backend does the work and is idempotent per stage, so a retry never re-bills.")
    t = sub_trigger(f, ["run_id", "stage_id"])
    build = f.add("Build call", "n8n-nodes-base.code", {"jsCode": (
        "const { run_id, stage_id } = $json;\n"
        f"return [{{ json: {{ run_id, stage_id, path: `{API}/runs/${{run_id}}/stages/${{stage_id}}`, "
        f"body: '', timeout_ms: {STAGE_TIMEOUT_MS} }} }}];\n"
    )}, (240, 0), 2)
    call = call_sub(f, "Signed call", "signed", (480, 0))
    shape = f.add("Shape result", "n8n-nodes-base.code", {"jsCode": (
        "const r = $input.first().json;\n"
        "const meta = $('Build call').first().json;\n"
        "if (!r.ok) return [{ json: { run_id: meta.run_id, stage: meta.stage_id, status: 'failed', "
        "code: r.code || 'orchestrator_http_error', retryable: true, counts: {}, flags: {} } }];\n"
        "return [{ json: r.result }];\n"
    )}, (720, 0), 2)
    f.link(t, build); f.link(build, call); f.link(call, shape)
    return f


# ═══ 3. specialist fan-out / fan-in ═════════════════════════════════════════════════════════════
def fanout() -> Flow:
    f = Flow("fanout", "AdvisorAI · 20 Specialist fan-out",
             "Reusable. Asks the backend for the run plan (the specialists chosen from the REGISTRY, never "
             "named here), runs them in parallel batches of plan.max_parallel, and fans in. One specialist "
             "failing never fails the run: the backend records it as unavailable and the run continues.")
    t = sub_trigger(f, ["run_id"])
    stage_in = f.add("Stage input", "n8n-nodes-base.set", {"assignments": {"assignments": [
        {"id": "a1", "name": "run_id", "value": "={{ $json.run_id }}", "type": "string"},
        {"id": "a2", "name": "stage_id", "value": "specialist_fanout", "type": "string"},
    ]}, "options": {}}, (240, 0), 3.4)
    stage = call_sub(f, "Run fan-out stage", "stage", (480, 0))
    ok = f.add("Stage ok?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.status }}", "rightValue": "failed",
                        "operator": {"type": "string", "operation": "notEquals"}}], "combinator": "and"}},
        (720, 0), 2.2)
    plan_build = f.add("Build plan call", "n8n-nodes-base.code", {"jsCode": (
        "const run_id = $('Stage input').first().json.run_id;\n"
        f"return [{{ json: {{ run_id, path: `{API}/runs/${{run_id}}/plan`, body: '', timeout_ms: {STAGE_TIMEOUT_MS} }} }}];\n"
    )}, (960, -120), 2)
    plan = call_sub(f, "Plan", "signed", (1200, -120))
    agents = f.add("One item per specialist", "n8n-nodes-base.code", {"jsCode": (
        "const r = $input.first().json;\n"
        "const run_id = $('Stage input').first().json.run_id;\n"
        "if (!r.ok) return [];\n"
        "const plan = r.result;\n"
        "const crypto = require('crypto');\n"
        "const secret = $env.ADVISORAI_N8N_HMAC_SECRET;\n"
        "const base = String($env.ADVISORAI_API_BASE_URL || '').replace(/\\/$/, '');\n"
        "return plan.agents.map((a) => {\n"
        f"  const path = `{API}/runs/${{run_id}}/agents/${{a.id}}`;\n"
        "  const ts = String(Math.floor(Date.now() / 1000));\n"
        "  const hash = crypto.createHash('sha256').update('').digest('hex');\n"
        "  const sig = crypto.createHmac('sha256', secret).update(`${ts}.POST.${path}.${hash}`).digest('hex');\n"
        "  return { json: { agent_id: a.id, url: base + path, ts, sig, max_parallel: plan.max_parallel, "
        "timeout: Math.max(Number(a.timeout_s) * 1000, 10000) } };\n"
        "});\n"
    )}, (1440, -120), 2)
    run_agents = f.add("Run specialists (parallel batches)", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "={{ $json.url }}", "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-Advisorai-Timestamp", "value": "={{ $json.ts }}"},
            {"name": "X-Advisorai-Signature", "value": "={{ $json.sig }}"},
        ]},
        "options": {
            "timeout": "={{ $json.timeout }}",
            "batching": {"batch": {"batchSize": "={{ $json.max_parallel }}", "batchInterval": 0}},
        },
    }, (1680, -120), 4.2, retryOnFail=True, maxTries=MAX_TRIES, waitBetweenTries=BACKOFF_MS,
        onError="continueRegularOutput")
    fan_in = f.add("Fan in", "n8n-nodes-base.code", {"jsCode": (
        "// Every outcome is data. A failed or timed-out specialist is counted, never thrown: the backend already\n"
        "// stored it as 'unavailable' (or will, at collection, as 'not_run'); the run continues.\n"
        "const items = $input.all().map((i) => i.json);\n"
        "const bad = items.filter((j) => j.error || j.status !== 'ok').length;\n"
        "return [{ json: { status: 'ok', agents: items.length, unavailable: bad } }];\n"
    )}, (1920, -120), 2)
    failed = f.add("Fan-out failed", "n8n-nodes-base.noOp", {}, (960, 120))
    f.link(t, stage_in); f.link(stage_in, stage); f.link(stage, ok)
    f.link(ok, plan_build, 0); f.link(ok, failed, 1)
    f.link(plan_build, plan); f.link(plan, agents); f.link(agents, run_agents); f.link(run_agents, fan_in)
    return f


# ═══ 4. error recovery ═════════════════════════════════════════════════════════════════════════
def error_recovery() -> Flow:
    f = Flow("error", "AdvisorAI · 90 Error recovery",
             "Set as the master's error workflow. If the master execution crashes, the backend fails the run it "
             "was driving with a person-safe reason (idempotent, content-free), so no run is left 'running'.")
    t = f.add("On workflow error", "n8n-nodes-base.errorTrigger", {}, (0, 0), 1)
    build = f.add("Build call", "n8n-nodes-base.code", {"jsCode": (
        "const id = String($json.execution.id).replace(/[^A-Za-z0-9_.:-]/g, '');\n"
        f"return [{{ json: {{ path: `{API}/executions/${{id}}/fail`, body: '', timeout_ms: 30000 }} }}];\n"
    )}, (240, 0), 2)
    call = call_sub(f, "Signed call", "signed", (480, 0))
    f.link(t, build); f.link(build, call)
    return f


# ═══ 5. master ═════════════════════════════════════════════════════════════════════════════════
def master() -> Flow:
    f = Flow("master", "AdvisorAI · 00 Master case analysis",
             "Entry point. Verifies the signed start request, then sequences the run's stages by calling the "
             "backend. It names no specialty and holds no case content, key or database login.")
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
        "options": {"responseCode": 401}}, (720, 160), 1.1)
    accept = f.add("Respond 202", "n8n-nodes-base.respondToWebhook", {
        "respondWith": "json", "responseBody": "={{ { accepted: true } }}",
        "options": {"responseCode": 202}}, (720, -80), 1.1)
    begin_build = f.add("Build begin call", "n8n-nodes-base.code", {"jsCode": (
        "const run_id = $('Verify signature').first().json.run_id;\n"
        "const body = JSON.stringify({ schema_version: 'begin_request.v1', execution_id: String($execution.id) });\n"
        f"return [{{ json: {{ run_id, path: `{API}/runs/${{run_id}}/begin`, body, timeout_ms: 30000 }} }}];\n"
    )}, (960, -80), 2)
    begin = call_sub(f, "Begin run", "signed", (1200, -80))
    stages = f.add("Stages still to run", "n8n-nodes-base.code", {"jsCode": (
        "const r = $input.first().json;\n"
        "const run_id = $('Verify signature').first().json.run_id;\n"
        "if (!r.ok) return [{ json: { run_id, stage_id: '__abort__' } }];\n"
        "const done = new Set(r.result.completed_stages);\n"
        "return r.result.stages.filter((s) => !done.has(s)).map((s) => ({ json: { run_id, stage_id: s } }));\n"
    )}, (1440, -80), 2)
    loop = f.add("Each stage", "n8n-nodes-base.splitInBatches", {"batchSize": 1, "options": {}}, (1680, -80), 3)
    is_fan = f.add("Specialist stage?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.stage_id }}", "rightValue": "specialist_fanout",
                        "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
        (1920, -160), 2.2)
    fan = call_sub(f, "Fan-out specialists", "fanout", (2160, -260))
    one = call_sub(f, "Run stage", "stage", (2160, -60))
    decide = f.add("Continue?", "n8n-nodes-base.code", {"jsCode": (
        "// Stop the loop on a failed (critical) or cancelled stage; everything else, including 'unavailable' and\n"
        "// 'skipped', continues. The backend decides what is critical; n8n only reads the status.\n"
        "const s = $input.first().json;\n"
        "const stop = s.stage_id === '__abort__' || s.status === 'failed' || s.status === 'cancelled';\n"
        "return [{ json: { stop, stage: s.stage || null, status: s.status || null } }];\n"
    )}, (2400, -160), 2)
    cont = f.add("Stopped?", "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose"},
        "conditions": [{"id": "c1", "leftValue": "={{ $json.stop }}", "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true"}}], "combinator": "and"}},
        (2640, -160), 2.2)
    fin_build = f.add("Build finish call", "n8n-nodes-base.code", {"jsCode": (
        "const run_id = $('Verify signature').first().json.run_id;\n"
        f"return [{{ json: {{ run_id, path: `{API}/runs/${{run_id}}/finish`, body: '', timeout_ms: 30000 }} }}];\n"
    )}, (2880, 40), 2)
    fin = call_sub(f, "Finish run", "signed", (3120, 40))
    f.link(wh, verify); f.link(verify, gate)
    f.link(gate, accept, 0); f.link(gate, deny, 1)
    f.link(accept, begin_build); f.link(begin_build, begin); f.link(begin, stages); f.link(stages, loop)
    f.link(loop, fin_build, 0)          # done: all stages ran
    f.link(loop, is_fan, 1)             # loop body
    f.link(is_fan, fan, 0); f.link(is_fan, one, 1)
    f.link(fan, decide); f.link(one, decide); f.link(decide, cont)
    f.link(cont, fin_build, 0)          # stop early: still finish (the backend computes failed/partial)
    f.link(cont, loop, 1)               # carry on
    f.link(fin_build, fin)
    return f


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "advisorai-00-master.json": master(), "advisorai-05-signed-call.json": signed_call(),
        "advisorai-10-run-stage.json": run_stage(), "advisorai-20-specialist-fanout.json": fanout(),
        "advisorai-90-error-recovery.json": error_recovery(),
    }
    for name, flow in files.items():
        (OUT / name).write_text(json.dumps(flow.export(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(flow.nodes)} nodes")


if __name__ == "__main__":
    main()
