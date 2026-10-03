"""A compact snapshot of the HTTP surface: every path+method and the property names / required-ness of the
request and response models. The frontend's wire schemas are tested against this same file
(`frontend/src/__tests__/contracts/wire-parity.test.ts`), so an endpoint or field added, renamed or made
optional on one side fails a test on the other.

Regenerate after an intended change:   UPDATE_API_SURFACE=1 uv run pytest tests/contract/test_api_surface.py
"""

import json
import os
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.main import create_app

SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "api-surface.json"
# The endpoint models the frontend's `resources.ts` / `me.ts` mirror by hand.
MODELS = [
    "CaseSummary",
    "NewCaseInput",
    "DocumentItem",
    "UploadUrlRequest",
    "UploadUrlResponse",
    "SafetyCheckRequest",
    "SafetyCheckResult",
    "MeResponse",
    "ConsentInput",
    "AnalysisRun",
]


def current_surface() -> dict[str, Any]:
    spec = create_app(Settings(environment="test", _env_file=None)).openapi()
    paths = {
        path: sorted(m for m in item if m in {"get", "post", "put", "patch", "delete"})
        for path, item in sorted(spec["paths"].items())
    }
    schemas = spec["components"]["schemas"]
    models = {
        name: {
            "properties": sorted(schemas[name]["properties"]),
            "required": sorted(schemas[name].get("required", [])),
        }
        for name in MODELS
    }
    return {"paths": paths, "models": models}


def test_the_api_surface_matches_the_committed_snapshot() -> None:
    surface = current_surface()
    if os.environ.get("UPDATE_API_SURFACE"):
        SNAPSHOT.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
    assert json.loads(SNAPSHOT.read_text()) == surface, (
        "the API surface changed: update the frontend wire schemas, then regenerate with UPDATE_API_SURFACE=1"
    )
