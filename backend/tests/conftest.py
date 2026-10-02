import json
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

with warnings.catch_warnings():
    # Starlette's TestClient currently prefers `httpx2`; the httpx path still works.
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", cors_origins=["http://localhost:3000"], _env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def scenario_names() -> list[str]:
    return sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())


def load_fixture(scenario: str, name: str) -> Any:
    return json.loads((FIXTURES / scenario / name).read_text(encoding="utf-8"))
