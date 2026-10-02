import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.core.request_id import REQUEST_ID_HEADER, get_request_id

GENERATED = re.compile(r"^req_[0-9a-f]{32}$")


def test_generates_a_request_id_when_none_is_supplied(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert GENERATED.match(response.headers[REQUEST_ID_HEADER])


def test_each_request_gets_a_different_id(client: TestClient) -> None:
    ids = {client.get("/api/v1/health").headers[REQUEST_ID_HEADER] for _ in range(5)}
    assert len(ids) == 5


def test_propagates_a_supplied_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "req_123"})
    assert response.headers[REQUEST_ID_HEADER] == "req_123"


@pytest.mark.parametrize("bad", ["has space", "semi;colon", "x" * 129, "line\tbreak", "<script>"])
def test_replaces_an_unsafe_request_id(client: TestClient, bad: str) -> None:
    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: bad})
    assert GENERATED.match(response.headers[REQUEST_ID_HEADER])


def test_the_same_id_appears_in_the_header_and_the_error_body(client: TestClient) -> None:
    response = client.get("/api/v1/missing", headers={REQUEST_ID_HEADER: "req_abc-1.2"})
    assert response.headers[REQUEST_ID_HEADER] == "req_abc-1.2"
    assert response.json()["error"]["request_id"] == "req_abc-1.2"


def test_error_responses_without_a_supplied_id_still_have_one(client: TestClient) -> None:
    response = client.get("/api/v1/missing")
    assert response.json()["error"]["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert GENERATED.match(response.headers[REQUEST_ID_HEADER])


def test_preflight_requests_carry_a_request_id(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert GENERATED.match(response.headers[REQUEST_ID_HEADER])


def test_the_request_id_is_logged_and_the_query_string_is_not(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="advisorai.request"):
        client.get("/api/v1/health?patient=secret", headers={REQUEST_ID_HEADER: "req_log1"})
    line = caplog.records[-1]
    assert "GET /api/v1/health -> 200" in line.getMessage()
    assert "secret" not in line.getMessage()


def test_outside_a_request_a_fresh_id_is_returned() -> None:
    assert GENERATED.match(get_request_id())
