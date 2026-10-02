import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas import CONTRACTS


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_defaults() -> None:
    s = make()
    assert s.environment == "local"
    assert s.cors_origins == ["http://localhost:3000"]
    assert s.docs_enabled is True


def test_reads_advisorai_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVISORAI_ENVIRONMENT", "test")
    monkeypatch.setenv("ADVISORAI_CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("ADVISORAI_DOCS_ENABLED", "false")
    s = make()
    assert s.environment == "test"
    assert s.cors_origins == ["https://a.example", "https://b.example"]
    assert s.docs_enabled is False


def test_rejects_a_wildcard_origin_and_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        make(cors_origins=["*"])
    with pytest.raises(ValidationError):
        make(environment="staging")


def test_cors_allows_the_configured_origin_only(client: TestClient) -> None:
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-request-id" in ok.headers["access-control-expose-headers"].lower()
    other = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_is_served_under_the_versioned_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/openapi.json").status_code == 200
    assert client.get("/api/v1/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 404


def test_docs_can_be_disabled() -> None:
    c = TestClient(create_app(make(docs_enabled=False)))
    assert c.get("/api/v1/docs").status_code == 404
    assert c.get("/api/v1/openapi.json").status_code == 404


def test_openapi_documents_the_health_route_the_error_envelope_and_the_five_contracts(
    client: TestClient,
) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/health" in spec["paths"]
    assert spec["info"]["x-contract-versions"] == sorted(CONTRACTS)
    schemas = spec["components"]["schemas"]
    for name in ("CaseV1", "SpecialistReport", "PatientReport", "Trace", "AnalysisRun", "ErrorEnvelope"):
        assert name in schemas, name
    # Recursive trace nodes resolve inside the components section.
    assert schemas["TraceNode"]["properties"]["children"]["items"]["$ref"] == "#/components/schemas/TraceNode"
    # Errors are documented on the route.
    assert spec["paths"]["/api/v1/health"]["get"]["responses"]["500"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/ErrorEnvelope")


def test_every_contract_pins_its_schema_version_in_the_json_schema() -> None:
    for version, model in CONTRACTS.items():
        props = model.model_json_schema()["properties"]
        assert props["schema_version"]["const"] == version
