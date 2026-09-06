"""End-to-end integration test verifying health check across the full application stack."""

from fastapi.testclient import TestClient
from backend.app.main import app


def test_system_health_integration():
    """Verify application boots and /api/health responds with 200 OK and expected structure."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "healthy"
        assert payload["environment"] == "development"
