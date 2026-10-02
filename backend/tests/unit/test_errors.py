from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas import ErrorCode, ErrorEnvelope


@pytest.fixture
def probe_client(settings: Settings) -> Iterator[TestClient]:
    """An app with extra routes that fail on purpose."""
    app = create_app(settings)
    router = APIRouter(prefix="/api/v1/_probe")

    @router.get("/case-missing")
    async def case_missing() -> None:
        raise AppError(
            ErrorCode.CASE_NOT_FOUND, "Case could not be found.", status_code=404, details={"case_id": "c_1"}
        )

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @router.post("/echo")
    async def echo(payload: dict[str, int]) -> dict[str, int]:
        return payload

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def assert_envelope(body: dict[str, object], code: str) -> dict[str, object]:
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "request_id", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["request_id"], str) and error["request_id"]
    assert isinstance(error["details"], dict)
    return error


def test_domain_error_uses_the_envelope(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/_probe/case-missing", headers={"X-Request-ID": "req_123"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "CASE_NOT_FOUND",
            "message": "Case could not be found.",
            "request_id": "req_123",
            "details": {"case_id": "c_1"},
        }
    }


def test_unknown_route_is_a_404_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert_envelope(response.json(), "NOT_FOUND")


def test_validation_error_is_a_422_envelope_without_echoing_input(probe_client: TestClient) -> None:
    response = probe_client.post("/api/v1/_probe/echo", json={"age": "my chest hurts"})
    assert response.status_code == 422
    error = assert_envelope(response.json(), "VALIDATION_ERROR")
    details = error["details"]
    assert isinstance(details, dict) and details["errors"][0]["loc"] == ["body", "age"]
    assert "my chest hurts" not in response.text  # PHI must not be reflected back


def test_unhandled_exception_is_a_500_envelope_that_hides_internals(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/_probe/boom", headers={"X-Request-ID": "req_500"})
    assert response.status_code == 500
    error = assert_envelope(response.json(), "INTERNAL_ERROR")
    assert error["request_id"] == "req_500"
    assert response.headers["X-Request-ID"] == "req_500"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


def test_a_500_still_carries_cors_headers_so_the_browser_can_read_it(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/_probe/boom", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_the_envelope_model_round_trips_and_rejects_malformed_bodies() -> None:
    good = {"error": {"code": "CASE_NOT_FOUND", "message": "m", "request_id": "req_1", "details": {}}}
    assert ErrorEnvelope.model_validate(good).model_dump(mode="json") == good
    # details defaults to {}
    assert (
        ErrorEnvelope.model_validate(
            {"error": {"code": "NOT_FOUND", "message": "m", "request_id": "r"}}
        ).error.details
        == {}
    )
    for bad in (
        {},
        {"error": {"code": "NOT_A_CODE", "message": "m", "request_id": "r"}},
        {"error": {"code": "NOT_FOUND", "message": "m"}},
        {"error": {"code": "NOT_FOUND", "message": "m", "request_id": "r", "extra": 1}},
        {"error": {"code": "NOT_FOUND", "message": "m", "request_id": "r"}, "also": 1},
    ):
        with pytest.raises(ValidationError):
            ErrorEnvelope.model_validate(bad)


def test_every_error_code_is_screaming_snake_case() -> None:
    assert all(c.value == c.name and c.value.isupper() for c in ErrorCode)
