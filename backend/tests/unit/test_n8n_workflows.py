"""Structural and contract checks of the committed n8n workflow exports (`n8n/workflows/*.json`).

n8n itself is not run here (no n8n in the test environment), so these tests pin what CAN be checked offline:
the files are well-formed, wired consistently, call only the backend capability API that really exists, carry
no credential, provider endpoint or specialty name, and agree with `registry/orchestration.yaml`. The behaviour
the workflows trigger is covered by `drive()` in tests/orch_support.py, a Python reference of the master flow.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.agents.registry import SpecialtyRegistry
from app.orchestration.policy import OrchestrationPolicy
from app.orchestration.workflows import WorkflowRegistry

ROOT = Path(__file__).resolve().parents[3] / "n8n"
FILES = sorted((ROOT / "workflows").glob("*.json"))
FLOWS = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in FILES}
RAW = {p.name: p.read_text(encoding="utf-8") for p in FILES}
PROVIDER_MARKERS = (
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "generativelanguage",
    "googleapis",
    "mistral",
    "cohere",
    "groq",
    "together",
    "perplexity",
    "azure",
    "bedrock",
    "huggingface",
    "deepseek",
)


def test_the_expected_workflows_exist() -> None:
    assert [p.name for p in FILES] == [
        "advisorai-00-master.json",
        "advisorai-05-signed-call.json",
        "advisorai-10-run-stage.json",
        "advisorai-20-fanout-stage.json",
        "advisorai-90-error-recovery.json",
    ]


@pytest.mark.parametrize("name", list(FLOWS))
def test_each_workflow_is_well_formed_and_wired_consistently(name: str) -> None:
    flow = FLOWS[name]
    nodes = flow["nodes"]
    names = [n["name"] for n in nodes]
    assert len(set(names)) == len(names) and len({n["id"] for n in nodes}) == len(nodes)
    assert flow["active"] is False  # imported inactive; activated deliberately (docs/n8n.md)
    for source, outputs in flow["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in names
    for node in nodes:
        assert set(node) >= {"id", "name", "type", "typeVersion", "position", "parameters"}
    triggers = [n for n in nodes if n["type"].endswith(("Trigger", "webhook"))]
    assert len(triggers) == 1


def test_sub_workflow_references_resolve_and_the_error_workflow_exists() -> None:
    ids = {f["id"] for f in FLOWS.values()}
    for flow in FLOWS.values():
        for node in flow["nodes"]:
            if node["type"] == "n8n-nodes-base.executeWorkflow":
                assert node["parameters"]["workflowId"]["value"] in ids
        if "errorWorkflow" in flow["settings"]:
            assert flow["settings"]["errorWorkflow"] in ids


@pytest.mark.parametrize("name", list(FLOWS))
def test_no_credential_key_provider_endpoint_or_database_node_is_in_any_workflow(name: str) -> None:
    text, flow = RAW[name], FLOWS[name]
    low = text.lower()
    assert not any(marker in low for marker in PROVIDER_MARKERS)
    assert not re.search(r"sk-[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{20,}|service_role|bearer\s+[a-z0-9]", low)
    assert "credentials" not in text and "supabase" not in low and "postgres" not in low
    for node in flow["nodes"]:
        assert "langchain" not in node["type"] and "openai" not in node["type"].lower()
        assert node["type"] not in {"n8n-nodes-base.postgres", "n8n-nodes-base.supabase"}


@pytest.mark.parametrize("name", list(FLOWS))
def test_secrets_come_only_from_the_environment_and_urls_only_from_the_backend_base(name: str) -> None:
    flow = FLOWS[name]
    for node in flow["nodes"]:
        if node["type"] == "n8n-nodes-base.httpRequest":
            assert (
                node["parameters"]["url"] == "={{ $json.url }}"
            )  # built from ADVISORAI_API_BASE_URL in a Code node
    assert not re.search(r"https?://", RAW[name])
    for var in re.findall(r"\$env\.([A-Z0-9_]+)", RAW[name]):
        assert var in {
            "ADVISORAI_N8N_HMAC_SECRET",
            "ADVISORAI_API_BASE_URL",
            "ADVISORAI_N8N_MAX_CLOCK_SKEW_SECONDS",
        }


def test_no_workflow_names_a_specialty_a_stage_or_a_clinical_branch() -> None:
    registry = SpecialtyRegistry.from_file()
    workflows = WorkflowRegistry.from_file()
    stage_ids = {s for w in workflows.ids() for s in workflows.get(w).stage_ids}
    flags = {
        f
        for w in workflows.ids()
        for st in workflows.get(w).stages
        for f in (*st.flags, *([st.when] if st.when else []))
    }
    handlers = {st.handler for w in workflows.ids() for st in workflows.get(w).stages}
    names = {s.id for s in registry.specs()} | stage_ids | flags | handlers
    for name, text in RAW.items():
        quoted = [n for n in names if re.search(rf"['\"`\s.]{n}['\"`\s.:]", text)]
        assert not quoted, (name, quoted)


def test_the_master_decides_from_descriptor_metadata_not_from_a_stage_name() -> None:
    master = RAW["advisorai-00-master.json"]
    assert "specialist_fanout" not in master and "specialist" not in master.lower().replace("specialty", "")
    flow = FLOWS["advisorai-00-master.json"]
    fan_if = next(n for n in flow["nodes"] if n["name"] == "Fan-out stage?")
    assert fan_if["parameters"]["conditions"]["conditions"][0]["leftValue"] == "={{ $json.kind }}"
    assert fan_if["parameters"]["conditions"]["conditions"][0]["rightValue"] == "fanout"
    evaluate = next(n for n in flow["nodes"] if n["name"] == "Evaluate condition")["parameters"]["jsCode"]
    assert "s.when" in evaluate and "flags[s.when]" in evaluate  # the condition is data from `begin`
    # the three outcomes (run / skip / abort) each have their own branch; skip goes through the generic stage flow
    switch = next(n for n in flow["nodes"] if n["name"] == "Action")
    assert [r["outputKey"] for r in switch["parameters"]["rules"]["values"]] == ["run", "skip", "abort"]
    skip = next(n for n in flow["nodes"] if n["name"] == "Skip stage")
    assert skip["parameters"]["workflowId"]["value"] == "advisorai-run-stage"
    run_stage = next(n for n in FLOWS["advisorai-10-run-stage.json"]["nodes"] if n["name"] == "Build call")
    assert (
        "action === 'skip'" in run_stage["parameters"]["jsCode"]
        and "condition_not_met" in run_stage["parameters"]["jsCode"]
    )


def test_stage_retry_and_timeout_come_from_the_descriptors_not_from_constants() -> None:
    build = next(n for n in FLOWS["advisorai-10-run-stage.json"]["nodes"] if n["name"] == "Build call")[
        "parameters"
    ]["jsCode"]
    for field in ("timeout_seconds", "retries", "backoff_seconds"):
        assert field in build
    evaluate = next(
        n for n in FLOWS["advisorai-00-master.json"]["nodes"] if n["name"] == "Evaluate condition"
    )["parameters"]["jsCode"]
    for field in ("timeout_seconds", "retries", "backoff_seconds"):
        assert f"s.{field}" in evaluate
    signed = next(n for n in FLOWS["advisorai-05-signed-call.json"]["nodes"] if n["name"] == "Sign and call")[
        "parameters"
    ]["jsCode"]
    assert "max_tries" in signed and "backoff_ms" in signed and "timeout_ms" in signed


def test_every_backend_path_the_workflows_call_is_a_real_post_route() -> None:
    from app.api.internal_orchestrator import router

    patterns = [
        re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", route.path) + "$")  # type: ignore[attr-defined]
        for route in router.routes
        if "POST" in getattr(route, "methods", ())
    ]
    used: set[str] = set()
    for text in RAW.values():
        for match in re.findall(r"`(/internal/orchestrator/v1/[^`]+)`", text.replace("\\u0060", "`")):
            used.add(re.sub(r"\$\{[^}]+\}", "x", match))
    assert len(used) >= 5
    for path in used:
        assert any(p.match(path) for p in patterns), path


def test_fanout_item_retries_match_the_policy_defaults() -> None:
    policy = OrchestrationPolicy.from_file()
    fan = next(n for n in FLOWS["advisorai-20-fanout-stage.json"]["nodes"] if "parallel" in n["name"])
    assert fan["maxTries"] == policy.retry.stage_retries + 1
    assert fan["waitBetweenTries"] == policy.retry.backoff_seconds * 1000
    # concurrency comes from the backend's plan (policy.limits.max_parallel_agents), never a literal in JSON
    assert fan["parameters"]["options"]["batching"]["batch"]["batchSize"] == "={{ $json.max_parallel }}"


def test_the_requests_are_signed_the_way_the_backend_verifies_them() -> None:
    code = next(n for n in FLOWS["advisorai-05-signed-call.json"]["nodes"] if n["name"] == "Sign and call")
    js = code["parameters"]["jsCode"]
    assert (
        "`${ts}.POST.${path}.${hash}`" in js and "createHmac('sha256'" in js and "sha256').update(body)" in js
    )
    assert "status >= 400 && status < 500" in js  # a 4xx is a decision, never retried
    assert "X-Advisorai-Signature" in RAW["advisorai-05-signed-call.json"]
    master = RAW["advisorai-00-master.json"]
    assert "timingSafeEqual" in master and "orchestration_start.v1" in master  # inbound verification


def test_the_master_stops_on_failed_or_cancelled_stages_and_always_finishes() -> None:
    flow = FLOWS["advisorai-00-master.json"]
    decide = next(n for n in flow["nodes"] if n["name"] == "Update flags")["parameters"]["jsCode"]
    assert (
        "'failed'" in decide
        and "'cancelled'" in decide
        and "'unavailable'" not in decide.split("const stop")[1]
    )
    conns = flow["connections"]
    finish_sources = [
        s for s, o in conns.items() for b in o["main"] for t in b if t["node"] == "Build finish call"
    ]
    assert set(finish_sources) == {"Each stage", "Stopped?"}  # normal end and early stop both reach finish


def test_the_committed_json_is_exactly_what_the_generator_produces() -> None:
    spec = importlib.util.spec_from_file_location("gen", ROOT / "tools" / "generate_workflows.py")
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    produced = {
        "advisorai-00-master.json": gen.master(),
        "advisorai-05-signed-call.json": gen.signed_call(),
        "advisorai-10-run-stage.json": gen.run_stage(),
        "advisorai-20-fanout-stage.json": gen.fanout(),
        "advisorai-90-error-recovery.json": gen.error_recovery(),
    }
    for name, flow in produced.items():
        assert flow.export() == FLOWS[name], f"{name} is stale: run python3 n8n/tools/generate_workflows.py"
    policy = OrchestrationPolicy.from_file()
    assert (
        policy.retry.stage_retries + 1,
        policy.retry.backoff_seconds * 1000,
    ) == (gen.MAX_TRIES, gen.BACKOFF_MS)
