"""OpenAPI documentation.

FastAPI only documents models that a route uses. The five versioned contracts have no route yet
(Phase 2A), so they are added to `components.schemas` explicitly: the API docs are the published
form of the wire contract from day one.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.schemas import CONTRACTS, ErrorEnvelope
from app.schemas.common import WireModel

DESCRIPTION = """\
AdvisorAI helps a person prepare for a second opinion: it organises their records, shows what is
known, uncertain and missing, and suggests questions to ask their doctor.

**Decision support, not medical advice.** It does not diagnose, prescribe, or say a doctor is
right or wrong.

* Wire format: every key is `snake_case` (see ADR 0001).
* Errors: every error response is `{"error": {"code", "message", "request_id", "details"}}`
  (see ADR 0002). Send `X-Request-ID` to correlate; it is echoed on every response.
* Versioned contracts: `case.v1`, `specialist_report.v1`, `report.v1`, `trace.v1`, `run.v1`.
"""


def _contract_models() -> list[type[WireModel]]:
    return [*CONTRACTS.values(), ErrorEnvelope]


def install_openapi(app: FastAPI) -> None:
    def build() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["info"]["x-contract-versions"] = sorted(CONTRACTS)
        components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})

        for model in _contract_models():
            json_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, definition in json_schema.pop("$defs", {}).items():
                components.setdefault(name, definition)
            components.setdefault(model.__name__, json_schema)

        app.openapi_schema = schema
        return schema

    app.openapi = build  # type: ignore[method-assign]
