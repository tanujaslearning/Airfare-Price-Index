"""Pytest configuration and fixtures for backend tests."""

import pytest
from typing import Generator
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Test client fixture for making requests to FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client
