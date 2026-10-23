from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def settings() -> Settings:
    # Explicit test settings isolated from the developer's local .env (_env_file=None);
    # no DB password → DB reported as not configured.
    return Settings(env="test", db_password=None, _env_file=None)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
