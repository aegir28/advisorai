from fastapi.testclient import TestClient

from app.schemas.common import WireModel


def test_health_reports_ok_under_api_v1(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "advisorai-backend",
        "version": "0.1.0",
        "environment": "test",
    }


def test_health_is_snake_case_and_carries_no_personal_data(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert all(k == k.lower() for k in body)
    assert set(body) == {"status", "service", "version", "environment"}


def test_health_is_not_served_outside_the_versioned_prefix(client: TestClient) -> None:
    assert client.get("/health").status_code == 404


def test_only_get_is_allowed(client: TestClient) -> None:
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_health_model_is_a_strict_wire_model() -> None:
    from app.api.health import HealthResponse

    assert issubclass(HealthResponse, WireModel)
